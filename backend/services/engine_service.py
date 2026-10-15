from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.models.engine import EngineEvent
from backend.models.equipment import Equipment
from backend.models.fuel import FuelTransaction, FuelTransactionType
from backend.models.shift import Shift
from backend.services.fuel_service import FuelService
from backend.services.audit_service import AuditService

class EngineService:

    @staticmethod
    def calculate_hours_run(
        start_time: datetime,
        stop_time: datetime,
    ) -> Decimal:
        try:
            if stop_time <= start_time:
                raise ValueError("stop_time must be after start_time")
            duration = stop_time - start_time
        except TypeError as exc:
            raise ValueError(
                "start_time and stop_time must use compatible time zones"
            ) from exc

        hours = Decimal(str(duration.total_seconds())) / Decimal("3600")

        return hours.quantize(Decimal("0.001"))

    @staticmethod
    def create_engine_event(
        db: Session,
        equipment_id: int,
        shift_id: int,
        start_time: datetime,
        stop_time: datetime,
        lph_rate: Decimal,
        created_by_user_id: int,
        consumption: Decimal | None = None,
        remarks: str | None = None,
    ) -> EngineEvent:

        if lph_rate < 0:
            raise ValueError("lph_rate cannot be negative")

        # Get equipment
        equipment = db.get(Equipment, equipment_id)

        if not equipment:
            raise ValueError("Equipment not found")

        if not equipment.is_active:
            raise ValueError("Equipment is inactive")

        # Get shift
        shift = db.get(Shift, shift_id)

        if not shift:
            raise ValueError("Shift not found")

        if shift.status != "OPEN":
            raise ValueError("Engine events can only be added to an OPEN shift")

        if FuelService.has_later_shift(db, shift):
            raise ValueError(
                "This event would change fuel available to subsequent shifts; "
                "downstream reconciliation is required first."
            )

        # Engine must belong to the same vessel as the shift
        if equipment.vessel_id != shift.vessel_id:
            raise ValueError(
                "Equipment does not belong to the selected shift's vessel"
            )

        # Calculate runtime
        hours_run = EngineService.calculate_hours_run(
            start_time,
            stop_time,
        )

        if consumption is not None:
            if consumption < 0:
                raise ValueError("consumption cannot be negative")
            consumption = consumption.quantize(Decimal("0.001"))
        else:
            consumption = (
                hours_run * lph_rate
            ).quantize(Decimal("0.001"))

        event = EngineEvent(
            shift_id=shift_id,
            equipment_id=equipment_id,
            engine_type=equipment.equipment_type,
            start_time=start_time,
            stop_time=stop_time,
            hours_run=hours_run,
            consumption=consumption,
            lph_rate=lph_rate,
            active=False,
            remarks=remarks,
            created_by_user_id=created_by_user_id,
        )

        db.add(event)
        db.flush()

        # Record engine consumption in the fuel ledger
        FuelService.record_engine_consumption(
            db=db,
            vessel_id=shift.vessel_id,
            shift_date=shift.shift_date,
            shift_name=shift.shift_name,
            quantity=consumption,
            engine_event_id=event.id,
            created_by_user_id=created_by_user_id,
            remarks=f"Engine event #{event.id}",
        )

        AuditService.log(
            db=db,
            user_id=created_by_user_id,
            action="CREATE_ENGINE_EVENT",
            entity="engine_events",
            entity_id=event.id,
            old_values=None,
            new_values={
                "shift_id": event.shift_id,
                "equipment_id": event.equipment_id,
                "engine_type": event.engine_type,
                "start_time": event.start_time.isoformat(),
                "stop_time": event.stop_time.isoformat(),
                "hours_run": str(event.hours_run),
                "consumption": str(event.consumption),
                "lph_rate": str(event.lph_rate),
                "active": event.active,
                "remarks": event.remarks,
            },
            details="Engine event created and linked engine consumption recorded.",
        )
        return event

    @staticmethod
    def _require_open_shift(db: Session, shift_id: int) -> Shift:
        shift = db.get(Shift, shift_id)
        if shift is None:
            raise ValueError("Shift not found")
        if shift.status != "OPEN":
            raise ValueError("Engine events can only be changed on an OPEN shift")
        return shift

    @staticmethod
    def _get_linked_fuel_transaction(
        db: Session,
        event: EngineEvent,
    ) -> FuelTransaction:
        transactions = list(
            db.scalars(
                select(FuelTransaction).where(
                    FuelTransaction.reference_type == "ENGINE_EVENT",
                    FuelTransaction.reference_id == event.id,
                )
            ).all()
        )
        if len(transactions) != 1:
            raise ValueError(
                "Engine event must have exactly one linked fuel transaction."
            )

        transaction = transactions[0]
        shift = db.get(Shift, event.shift_id)
        if shift is None:
            raise ValueError("Engine event shift was not found.")
        if (
            transaction.shift_id != event.shift_id
            or transaction.vessel_id != shift.vessel_id
            or transaction.transaction_type
            != FuelTransactionType.ENGINE_CONSUMPTION.value
            or Decimal(str(transaction.quantity))
            != Decimal(str(event.consumption))
        ):
            raise ValueError(
                "Linked fuel transaction does not match the engine event's shift, vessel, type, or quantity."
            )
        return transaction

    @staticmethod
    def _event_values(event: EngineEvent) -> dict:
        return {
            "shift_id": event.shift_id,
            "equipment_id": event.equipment_id,
            "engine_type": event.engine_type,
            "start_time": event.start_time.isoformat(),
            "stop_time": event.stop_time.isoformat(),
            "hours_run": str(event.hours_run),
            "consumption": str(event.consumption),
            "lph_rate": str(event.lph_rate),
            "active": event.active,
            "remarks": event.remarks,
        }

    @staticmethod
    def update_engine_event(
        db: Session,
        *,
        event_id: int,
        shift_id: int,
        equipment_id: int,
        start_time: datetime,
        stop_time: datetime,
        lph_rate: Decimal,
        corrected_by_user_id: int,
        reason: str,
        consumption: Decimal | None = None,
        remarks: str | None = None,
    ) -> EngineEvent:
        event = db.get(EngineEvent, event_id)
        if event is None:
            raise ValueError("Engine event not found")
        if event.shift_id != shift_id:
            raise ValueError("Engine event does not belong to the selected shift")

        shift = EngineService._require_open_shift(db, shift_id)
        reason = reason.strip() if reason else ""
        if not reason:
            raise ValueError("Correction reason is required")
        if lph_rate < 0:
            raise ValueError("lph_rate cannot be negative")

        equipment = db.get(Equipment, equipment_id)
        if equipment is None:
            raise ValueError("Equipment not found")
        if not equipment.is_active:
            raise ValueError("Equipment is inactive")
        if equipment.vessel_id != shift.vessel_id:
            raise ValueError(
                "Equipment does not belong to the selected shift's vessel"
            )

        hours_run = EngineService.calculate_hours_run(start_time, stop_time)
        if consumption is None:
            consumption = (hours_run * lph_rate).quantize(Decimal("0.001"))
        else:
            consumption = consumption.quantize(Decimal("0.001"))
        if consumption <= 0:
            raise ValueError("Engine consumption must be greater than zero")

        transaction = EngineService._get_linked_fuel_transaction(db, event)
        if (
            Decimal(str(transaction.quantity)) != consumption
            and FuelService.has_later_shift(db, shift)
        ):
            raise ValueError(
                "This correction would change fuel available to subsequent shifts; "
                "downstream reconciliation is required first."
            )
        old_values = EngineService._event_values(event)
        old_values["fuel_transaction"] = {
            "id": transaction.id,
            "quantity": str(transaction.quantity),
        }

        event.equipment_id = equipment.id
        event.engine_type = equipment.equipment_type
        event.start_time = start_time
        event.stop_time = stop_time
        event.hours_run = hours_run
        event.consumption = consumption
        event.lph_rate = lph_rate
        event.remarks = remarks
        transaction.quantity = consumption

        db.flush()
        FuelService.recalculate_shift(db, shift_id)
        AuditService.log(
            db=db,
            user_id=corrected_by_user_id,
            action="UPDATE_ENGINE_EVENT",
            entity="engine_events",
            entity_id=event.id,
            old_values=old_values,
            new_values={
                **EngineService._event_values(event),
                "fuel_transaction": {
                    "id": transaction.id,
                    "quantity": str(transaction.quantity),
                },
            },
            reason=reason,
            details="Engine event and its linked fuel transaction were corrected.",
        )
        return event

    @staticmethod
    def delete_engine_event(
        db: Session,
        *,
        event_id: int,
        shift_id: int,
        deleted_by_user_id: int,
        reason: str,
    ) -> None:
        event = db.get(EngineEvent, event_id)
        if event is None:
            raise ValueError("Engine event not found")
        if event.shift_id != shift_id:
            raise ValueError("Engine event does not belong to the selected shift")

        shift = EngineService._require_open_shift(db, shift_id)
        reason = reason.strip() if reason else ""
        if not reason:
            raise ValueError("Correction reason is required")

        transaction = EngineService._get_linked_fuel_transaction(db, event)
        if FuelService.has_later_shift(db, shift):
            raise ValueError(
                "This deletion would change fuel available to subsequent shifts; "
                "downstream reconciliation is required first."
            )
        old_values = EngineService._event_values(event)
        old_values["fuel_transaction"] = {
            "id": transaction.id,
            "quantity": str(transaction.quantity),
            "transaction_type": transaction.transaction_type,
        }
        event_id = event.id

        db.delete(transaction)
        db.delete(event)
        db.flush()
        FuelService.recalculate_shift(db, shift_id)
        AuditService.log(
            db=db,
            user_id=deleted_by_user_id,
            action="DELETE_ENGINE_EVENT",
            entity="engine_events",
            entity_id=event_id,
            old_values=old_values,
            new_values=None,
            reason=reason,
            details="Engine event and its linked fuel transaction were deleted.",
        )
    
    @staticmethod
    def get_engine_event(
        db: Session,
        event_id: int,
    ) -> EngineEvent:
        event = db.get(EngineEvent, event_id)

        if not event:
            raise ValueError("Engine event not found")

        return event

    @staticmethod
    def get_engine_events(
        db: Session,
        shift_id: int | None = None,
        equipment_id: int | None = None,
    ) -> list[EngineEvent]:

        query = select(EngineEvent).order_by(
            EngineEvent.start_time.desc(),
            EngineEvent.id.desc(),
        )

        if shift_id is not None:
            query = query.where(
                EngineEvent.shift_id == shift_id
            )

        if equipment_id is not None:
            query = query.where(
                EngineEvent.equipment_id == equipment_id
            )

        return list(db.scalars(query).all())