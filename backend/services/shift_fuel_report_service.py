from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from backend.models.engine import EngineEvent
from backend.models.equipment import Equipment
from backend.models.fuel import FuelTransaction, FuelTransactionType
from backend.models.production import ProductionRecord
from backend.models.shift import Shift
from backend.models.transfer import FuelTransfer
from backend.models.vessel import Vessel
from backend.services.fuel_service import FuelService


ZERO = Decimal("0")
TRANSFER_REFERENCE_TYPES = {"TRANSFER", "BALANCE_NEUTRAL_TRANSFER"}


class ShiftFuelReportService:
    @staticmethod
    def _time_text(value: datetime | None) -> str | None:
        return value.strftime("%H:%M:%S") if value is not None else None

    @staticmethod
    def _event_hours(event: EngineEvent) -> Decimal:
        if event.hours_run is not None:
            return Decimal(str(event.hours_run))
        if event.stop_time is None:
            return ZERO
        try:
            return Decimal(str((event.stop_time - event.start_time).total_seconds())) / Decimal("3600")
        except TypeError:
            return ZERO

    @staticmethod
    def get_rows(
        db: Session,
        *,
        from_date: date,
        to_date: date,
        vessel_id: int | None = None,
    ) -> list[dict]:
        if from_date > to_date:
            raise ValueError("From date cannot be later than to date.")

        statement = (
            select(Shift, Vessel.name)
            .join(Vessel, Vessel.id == Shift.vessel_id)
            .where(Shift.shift_date >= from_date, Shift.shift_date <= to_date)
            .order_by(
                Shift.shift_date.asc(),
                Vessel.name.asc(),
                case(
                    (Shift.shift_name == "MORNING", 0),
                    (Shift.shift_name == "EVENING", 1),
                    else_=2,
                ),
                Shift.id.asc(),
            )
        )
        if vessel_id is not None:
            statement = statement.where(Shift.vessel_id == vessel_id)

        shift_rows = db.execute(statement).all()
        if not shift_rows:
            return []

        shifts = [shift for shift, _ in shift_rows]
        shift_ids = [shift.id for shift in shifts]
        transactions_by_shift: dict[int, list[FuelTransaction]] = defaultdict(list)
        transactions = db.scalars(
            select(FuelTransaction).where(FuelTransaction.shift_id.in_(shift_ids))
        ).all()
        for transaction in transactions:
            transactions_by_shift[transaction.shift_id].append(transaction)

        events_by_shift: dict[int, list[tuple[EngineEvent, str | None]]] = defaultdict(list)
        event_rows = db.execute(
            select(EngineEvent, Equipment.equipment_type)
            .join(Equipment, Equipment.id == EngineEvent.equipment_id)
            .where(EngineEvent.shift_id.in_(shift_ids))
        ).all()
        for event, equipment_type in event_rows:
            events_by_shift[event.shift_id].append((event, equipment_type))

        remarks_by_shift: dict[int, list[str]] = defaultdict(list)
        production_records = db.scalars(
            select(ProductionRecord).where(ProductionRecord.shift_id.in_(shift_ids))
        ).all()
        for record in production_records:
            if record.remarks:
                remarks_by_shift[record.shift_id].append(record.remarks.strip())

        transfer_reference_ids = {
            transaction.reference_id
            for transaction in transactions
            if transaction.reference_id is not None
            and transaction.reference_type in TRANSFER_REFERENCE_TYPES
        }
        transfers_by_id = {
            transfer.id: transfer
            for transfer in db.scalars(
                select(FuelTransfer).where(FuelTransfer.id.in_(transfer_reference_ids))
            ).all()
        } if transfer_reference_ids else {}

        transfer_vessel_ids = {
            vessel_id
            for transfer in transfers_by_id.values()
            for vessel_id in (transfer.from_vessel_id, transfer.to_vessel_id)
        }
        transfer_vessel_ids.update(
            transaction.source_vessel_id
            for transaction in transactions
            if transaction.source_vessel_id is not None
        )
        vessel_names = {
            vessel.id: vessel.name
            for vessel in db.scalars(
                select(Vessel).where(Vessel.id.in_(transfer_vessel_ids))
            ).all()
        } if transfer_vessel_ids else {}

        report_rows: list[dict] = []
        for shift, vessel_name in shift_rows:
            balance = FuelService.calculate_shift_balance(db, shift.id, lock=False)
            engine_groups: dict[str, list[EngineEvent]] = {
                "ME": [],
                "AUX": [],
                "DG": [],
            }
            remarks = remarks_by_shift[shift.id]

            for event, equipment_type in events_by_shift[shift.id]:
                normalized_type = str(equipment_type or event.engine_type or "").upper()
                if normalized_type in engine_groups:
                    engine_groups[normalized_type].append(event)
                if event.remarks:
                    remarks.append(event.remarks.strip())

            receipts: list[FuelTransaction] = []
            transfer_out = ZERO
            transfer_in = ZERO
            outgoing_vessels: list[str] = []
            incoming_vessels: list[str] = []

            for transaction in transactions_by_shift[shift.id]:
                if transaction.transaction_type == FuelTransactionType.RECEIPT.value:
                    receipts.append(transaction)
                    if transaction.remarks:
                        remarks.append(transaction.remarks.strip())
                elif transaction.transaction_type == FuelTransactionType.TRANSFER_OUT.value:
                    transfer_out += Decimal(str(transaction.quantity))
                    transfer = transfers_by_id.get(transaction.reference_id)
                    if transfer is not None:
                        name = vessel_names.get(transfer.to_vessel_id)
                        if name:
                            outgoing_vessels.append(name)
                elif transaction.transaction_type == FuelTransactionType.TRANSFER_IN.value:
                    transfer_in += Decimal(str(transaction.quantity))
                    transfer = transfers_by_id.get(transaction.reference_id)
                    other_vessel_id = (
                        transfer.from_vessel_id
                        if transfer is not None
                        else transaction.source_vessel_id
                    )
                    name = vessel_names.get(other_vessel_id) if other_vessel_id else None
                    if name:
                        incoming_vessels.append(name)
                elif transaction.remarks and transaction.transaction_type != FuelTransactionType.ENGINE_CONSUMPTION.value:
                    remarks.append(transaction.remarks.strip())

            receipt_sources: list[str] = []
            for receipt in receipts:
                source = (
                    vessel_names.get(receipt.source_vessel_id)
                    if receipt.source_vessel_id is not None
                    else receipt.fuel_source
                )
                if source and source.strip():
                    receipt_sources.append(source.strip())

            engine_values: dict[str, dict] = {}
            for engine_type, events in engine_groups.items():
                start_times = [event.start_time for event in events if event.start_time is not None]
                stop_times = [event.stop_time for event in events if event.stop_time is not None]
                engine_values[engine_type] = {
                    "start_time": ShiftFuelReportService._time_text(min(start_times)) if start_times else None,
                    "close_time": ShiftFuelReportService._time_text(max(stop_times)) if stop_times else None,
                    "running_hours": sum(
                        (ShiftFuelReportService._event_hours(event) for event in events),
                        ZERO,
                    ),
                    "consumption": sum(
                        (Decimal(str(event.consumption or 0)) for event in events),
                        ZERO,
                    ),
                }

            for transfer in transfers_by_id.values():
                if shift.id in {transfer.from_shift_id, transfer.to_shift_id}:
                    if transfer.notes:
                        remarks.append(transfer.notes.strip())
                    if transfer.manager_remark:
                        remarks.append(transfer.manager_remark.strip())

            unique_remarks = list(dict.fromkeys(item for item in remarks if item))
            report_rows.append(
                {
                    "vessel_name": vessel_name,
                    "shift_date": shift.shift_date,
                    "shift_name": shift.shift_name,
                    "fuel_received_quantity": sum(
                        (Decimal(str(receipt.quantity)) for receipt in receipts),
                        ZERO,
                    ),
                    "fuel_received_from": ", ".join(dict.fromkeys(receipt_sources)) or None,
                    "main_engine_start_time": engine_values["ME"]["start_time"],
                    "main_engine_close_time": engine_values["ME"]["close_time"],
                    "main_engine_running_hours": engine_values["ME"]["running_hours"],
                    "main_engine_consumption": engine_values["ME"]["consumption"],
                    "aux_engine_start_time": engine_values["AUX"]["start_time"],
                    "aux_engine_close_time": engine_values["AUX"]["close_time"],
                    "aux_engine_running_hours": engine_values["AUX"]["running_hours"],
                    "aux_engine_consumption": engine_values["AUX"]["consumption"],
                    "dg_start_time": engine_values["DG"]["start_time"],
                    "dg_close_time": engine_values["DG"]["close_time"],
                    "dg_running_hours": engine_values["DG"]["running_hours"],
                    "dg_consumption": engine_values["DG"]["consumption"],
                    "total_vessel_fo_consumption": Decimal(str(balance["engine_consumption"])),
                    "transfer_out_quantity": transfer_out,
                    "transfer_out_vessels": ", ".join(dict.fromkeys(outgoing_vessels)) or None,
                    "transfer_in_quantity": transfer_in,
                    "transfer_in_vessels": ", ".join(dict.fromkeys(incoming_vessels)) or None,
                    "opening_fuel": Decimal(str(balance["opening_fuel"])),
                    "closing_fuel": Decimal(str(balance["closing_fuel"])),
                    "advancement_m": shift.advancement_m,
                    "dredging_hours": shift.dredging_hours,
                    # Soundings are currently photo attachments only; no numeric
                    # fuel-level reading is stored to report in litres.
                    "sounding_fuel_level_litres": None,
                    "remarks": "; ".join(unique_remarks) or None,
                }
            )

        return report_rows
