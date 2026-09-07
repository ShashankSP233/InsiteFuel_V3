from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.engine import EngineEvent
from backend.models.equipment import Equipment
from backend.models.shift import Shift
from backend.models.vessel import Vessel
from backend.services.fuel_service import FuelService
from backend.models.production import ProductionRecord
from backend.models.project import Project
from backend.services.sounding_service import SoundingService


ZERO = Decimal("0")


class DashboardService:

    @staticmethod
    def get_fuel_dashboard(
        db: Session,
        from_date: date,
        to_date: date,
        vessel_id: int | None = None,
        shift_name: str | None = None,
    ) -> list[dict]:
        """
        Return one dashboard row per vessel shift.

        All fuel figures are derived from the existing V3 fuel ledger
        and FuelService balance calculation.
        """

        if from_date > to_date:
            raise ValueError(
                "from_date cannot be later than to_date."
            )

        query = (
            select(Shift)
            .join(Vessel, Vessel.id == Shift.vessel_id)
            .where(
                Shift.shift_date >= from_date,
                Shift.shift_date <= to_date,
                Vessel.is_active.is_(True),
            )
            .order_by(
                Shift.shift_date.desc(),
                Vessel.name.asc(),
                Shift.id.desc(),
            )
        )

        if vessel_id is not None:
            query = query.where(
                Shift.vessel_id == vessel_id
            )

        if shift_name is not None:
            normalized_shift = shift_name.strip().upper()

            if normalized_shift not in {
                "MORNING",
                "EVENING",
            }:
                raise ValueError(
                    "shift_name must be MORNING or EVENING."
                )

            query = query.where(
                Shift.shift_name == normalized_shift
            )

        shifts = db.scalars(query).all()

        results: list[dict] = []

        for shift in shifts:
            vessel = db.get(
                Vessel,
                shift.vessel_id,
            )

            if vessel is None:
                continue

            balance = FuelService.calculate_shift_balance(
                db,
                shift.id,
            )

            engine_data = (
                DashboardService._get_engine_data(
                    db,
                    shift.id,
                )
            )

            closing_fuel = Decimal(
                str(balance["closing_fuel"])
            )

            threshold = Decimal(
                str(
                    vessel.fuel_threshold_litres
                    or 0
                )
            )

            flags = (
                DashboardService._get_flags(
                    closing_fuel=closing_fuel,
                    threshold=threshold,
                )
            )

            results.append(
                {
                    "shift_id": shift.id,
                    "vessel_id": vessel.id,
                    "vessel_name": vessel.name,
                    "project_id": vessel.project_id,

                    "shift_date": shift.shift_date,
                    "shift_name": shift.shift_name,
                    "status": shift.status,

                    "opening_fuel": Decimal(
                        str(balance["opening_fuel"])
                    ),
                    "received_fuel": Decimal(
                        str(balance["received_fuel"])
                    ),
                    "transfer_in": Decimal(
                        str(balance["transfer_in"])
                    ),

                    "me_consumption": engine_data[
                        "me_consumption"
                    ],
                    "me_hours": engine_data[
                        "me_hours"
                    ],

                    "aux_consumption": engine_data[
                        "aux_consumption"
                    ],
                    "aux_hours": engine_data[
                        "aux_hours"
                    ],

                    "dg_consumption": engine_data[
                        "dg_consumption"
                    ],
                    "dg_hours": engine_data[
                        "dg_hours"
                    ],

                    "total_engine_consumption": Decimal(
                        str(balance["engine_consumption"])
                    ),

                    "transfer_out": Decimal(
                        str(balance["transfer_out"])
                    ),

                    "adjustment_in": Decimal(
                        str(balance["adjustment_in"])
                    ),
                    "adjustment_out": Decimal(
                        str(balance["adjustment_out"])
                    ),

                    "closing_fuel": closing_fuel,

                    "fuel_threshold_litres": threshold,

                    "flags": flags,
                }
            )

        return results

    @staticmethod
    def _get_engine_data(
        db: Session,
        shift_id: int,
    ) -> dict:
        """
        Calculate engine hours and consumption by
        ME / AUX / DG for a shift.
        """

        events = db.scalars(
            select(EngineEvent)
            .where(
                EngineEvent.shift_id == shift_id
            )
        ).all()

        result = {
            "me_consumption": ZERO,
            "me_hours": ZERO,

            "aux_consumption": ZERO,
            "aux_hours": ZERO,

            "dg_consumption": ZERO,
            "dg_hours": ZERO,
        }

        for event in events:
            equipment = db.get(
                Equipment,
                event.equipment_id,
            )

            if equipment is None:
                continue

            equipment_type = str(
                equipment.equipment_type
            ).upper()

            consumption = Decimal(
                str(event.consumption or 0)
            )

            hours = Decimal(
                str(event.hours_run or 0)
            )

            if equipment_type == "ME":
                result["me_consumption"] += consumption
                result["me_hours"] += hours

            elif equipment_type == "AUX":
                result["aux_consumption"] += consumption
                result["aux_hours"] += hours

            elif equipment_type == "DG":
                result["dg_consumption"] += consumption
                result["dg_hours"] += hours

        return result

    @staticmethod
    def _get_flags(
        closing_fuel: Decimal,
        threshold: Decimal,
    ) -> list[str]:
        """
        Calculate dashboard warning flags.

        NEGATIVE_BALANCE:
            Closing fuel is below zero.

        LOW_FUEL:
            Threshold is enabled and closing fuel is at or
            below the configured vessel threshold.
        """

        flags: list[str] = []

        if closing_fuel < ZERO:
            flags.append("NEGATIVE_BALANCE")

        if (
            threshold > ZERO
            and closing_fuel <= threshold
        ):
            flags.append("LOW_FUEL")

        return flags

    @staticmethod
    def get_latest_closing_by_vessel(
        db: Session,
        vessel_ids: list[int] | None = None,
    ) -> dict[int, Decimal]:
        """
        Return the latest available closing fuel for each
        active vessel.

        This is used for dashboard-level current fuel totals.

        It deliberately does NOT sum every historical shift
        closing balance.
        """

        query = (
            select(Shift)
            .join(Vessel, Vessel.id == Shift.vessel_id)
            .where(
                Vessel.is_active.is_(True),
                Shift.calculated_closing_fuel.is_not(None),
            )
            .order_by(
                Shift.vessel_id.asc(),
                Shift.shift_date.desc(),
                Shift.id.desc(),
            )
        )

        if vessel_ids:
            query = query.where(
                Shift.vessel_id.in_(vessel_ids)
            )

        shifts = db.scalars(query).all()

        latest: dict[int, Decimal] = {}

        for shift in shifts:
            if shift.vessel_id in latest:
                continue

            latest[shift.vessel_id] = Decimal(
                str(
                    shift.calculated_closing_fuel
                )
            )

        return latest

    @staticmethod
    def get_vessel_balances(
        db: Session,
        from_date: date,
        to_date: date,
        vessel_id: int | None = None,
    ) -> list[dict]:
        if from_date > to_date:
            raise ValueError("from_date cannot be later than to_date.")

        query = (
            select(Vessel)
            .where(Vessel.is_active.is_(True))
            .order_by(Vessel.name.asc())
        )

        if vessel_id is not None:
            query = query.where(Vessel.id == vessel_id)

        vessels = db.scalars(query).all()

        latest_closing = DashboardService.get_latest_closing_by_vessel(
            db=db,
            vessel_ids=[v.id for v in vessels],
        )

        shifts_query = (
            select(Shift)
            .where(
                Shift.shift_date >= from_date,
                Shift.shift_date <= to_date,
            )
        )

        if vessel_id is not None:
            shifts_query = shifts_query.where(
                Shift.vessel_id == vessel_id
            )

        shifts = db.scalars(shifts_query).all()

        consumption_by_vessel: dict[int, Decimal] = {}

        for shift in shifts:
            balance = FuelService.calculate_shift_balance(
                db,
                shift.id,
            )

            consumption = Decimal(
                str(balance["engine_consumption"] or 0)
            )

            consumption_by_vessel[shift.vessel_id] = (
                consumption_by_vessel.get(
                    shift.vessel_id,
                    ZERO,
                )
                + consumption
            )

        number_of_days = (to_date - from_date).days + 1

        results = []

        for vessel in vessels:
            current_fuel = latest_closing.get(
                vessel.id,
                ZERO,
            )

            recent_consumption = consumption_by_vessel.get(
                vessel.id,
                ZERO,
            )

            average_daily_consumption = (
                recent_consumption / Decimal(number_of_days)
                if number_of_days > 0
                else ZERO
            )

            if average_daily_consumption > ZERO:
                estimated_days_remaining = (
                    current_fuel / average_daily_consumption
                )
            else:
                estimated_days_remaining = None

            threshold = Decimal(
                str(vessel.fuel_threshold_litres or 0)
            )

            flags = DashboardService._get_flags(
                closing_fuel=current_fuel,
                threshold=threshold,
            )

            results.append(
                {
                    "vessel_id": vessel.id,
                    "vessel_name": vessel.name,
                    "project_id": vessel.project_id,
                    "current_fuel": current_fuel,
                    "fuel_threshold_litres": threshold,
                    "recent_consumption": recent_consumption,
                    "average_daily_consumption": average_daily_consumption,
                    "estimated_days_remaining": estimated_days_remaining,
                    "flags": flags,
                }
            )

        return results

    @staticmethod
    def get_consumption_trend(
        db: Session,
        from_date: date,
        to_date: date,
        vessel_id: int | None = None,
    ) -> list[dict]:
        if from_date > to_date:
            raise ValueError("from_date cannot be later than to_date.")

        query = (
            select(Shift)
            .where(
                Shift.shift_date >= from_date,
                Shift.shift_date <= to_date,
            )
            .order_by(Shift.shift_date.asc(), Shift.id.asc())
        )

        if vessel_id is not None:
            query = query.where(
                Shift.vessel_id == vessel_id
            )

        shifts = db.scalars(query).all()

        consumption_by_date: dict[date, Decimal] = {}

        for shift in shifts:
            balance = FuelService.calculate_shift_balance(
                db,
                shift.id,
            )

            consumption = Decimal(
                str(balance["engine_consumption"] or 0)
            )

            consumption_by_date[shift.shift_date] = (
                consumption_by_date.get(
                    shift.shift_date,
                    ZERO,
                )
                + consumption
            )

        results = []

        current_date = from_date

        while current_date <= to_date:
            results.append(
                {
                    "date": current_date,
                    "consumption": consumption_by_date.get(
                        current_date,
                        ZERO,
                    ),
                }
            )

            current_date += timedelta(days=1)

        return results


    @staticmethod
    def get_fuel_efficiency(
        db: Session,
        from_date: date,
        to_date: date,
        vessel_id: int | None = None,
    ) -> dict:
        if from_date > to_date:
            raise ValueError("from_date cannot be later than to_date.")

        shift_query = select(Shift).where(
            Shift.shift_date >= from_date,
            Shift.shift_date <= to_date,
        )

        if vessel_id is not None:
            shift_query = shift_query.where(
                Shift.vessel_id == vessel_id
            )

        shifts = db.scalars(shift_query).all()

        total_consumption = ZERO

        for shift in shifts:
            balance = FuelService.calculate_shift_balance(
                db,
                shift.id,
            )

            total_consumption += Decimal(
                str(balance["engine_consumption"] or 0)
            )

        production_query = select(ProductionRecord).where(
            ProductionRecord.production_date >= from_date,
            ProductionRecord.production_date <= to_date,
        )

        if vessel_id is not None:
            production_query = production_query.where(
                ProductionRecord.vessel_id == vessel_id
            )

        production_records = db.scalars(
            production_query
        ).all()

        total_production = sum(
            (
                Decimal(str(record.true_qty or 0))
                for record in production_records
            ),
            ZERO,
        )

        consumption_per_unit = None

        if total_production > ZERO:
            consumption_per_unit = (
                total_consumption / total_production
            )

        return {
            "total_consumption": total_consumption,
            "total_production": total_production,
            "consumption_per_unit": consumption_per_unit,
        }


    @staticmethod
    def get_dashboard_comparison(
        db: Session,
        from_date: date,
        to_date: date,
        vessel_ids: list[int] | None = None,
        shift_name: str | None = None,
        project_id: int | None = None,
    ) -> list[dict]:
        if from_date > to_date:
            raise ValueError(
                "from_date cannot be later than to_date."
            )

        query = (
            select(Shift, Vessel, Project)
            .join(Vessel, Vessel.id == Shift.vessel_id)
            .join(Project, Project.id == Vessel.project_id)
            .where(
                Shift.shift_date >= from_date,
                Shift.shift_date <= to_date,
                Vessel.is_active.is_(True),
            )
            .order_by(
                Project.name.asc(),
                Vessel.name.asc(),
                Shift.shift_date.desc(),
                Shift.id.desc(),
            )
        )

        if vessel_ids:
            query = query.where(
                Shift.vessel_id.in_(vessel_ids)
            )

        if project_id is not None:
            query = query.where(
                Vessel.project_id == project_id
            )

        if shift_name is not None:
            normalized_shift = shift_name.strip().upper()

            if normalized_shift not in {
                "MORNING",
                "EVENING",
            }:
                raise ValueError(
                    "shift_name must be MORNING or EVENING."
                )

            query = query.where(
                Shift.shift_name == normalized_shift
            )

        records = db.execute(query).all()

        grouped: dict[tuple, dict] = {}

        for shift, vessel, project in records:
            key = (
                project.id,
                vessel.id,
                shift.shift_name,
            )

            if key not in grouped:
                grouped[key] = {
                    "project_id": project.id,
                    "project_name": project.name,
                    "vessel_id": vessel.id,
                    "vessel_name": vessel.name,
                    "shift_name": shift.shift_name,
                    "record_count": 0,
                    "me_litres": ZERO,
                    "aux_litres": ZERO,
                    "dg_litres": ZERO,
                    "transfer_out": ZERO,
                    "me_hours": ZERO,
                    "aux_hours": ZERO,
                    "dg_hours": ZERO,
                }

            item = grouped[key]

            item["record_count"] += 1

            engine_data = DashboardService._get_engine_data(
                db,
                shift.id,
            )

            item["me_litres"] += engine_data["me_consumption"]
            item["aux_litres"] += engine_data["aux_consumption"]
            item["dg_litres"] += engine_data["dg_consumption"]

            item["me_hours"] += engine_data["me_hours"]
            item["aux_hours"] += engine_data["aux_hours"]
            item["dg_hours"] += engine_data["dg_hours"]

            balance = FuelService.calculate_shift_balance(
                db,
                shift.id,
            )

            item["transfer_out"] += Decimal(
                str(balance["transfer_out"] or 0)
            )

        results = []

        for item in grouped.values():
            me_litres = item["me_litres"]
            aux_litres = item["aux_litres"]
            dg_litres = item["dg_litres"]

            me_hours = item["me_hours"]
            aux_hours = item["aux_hours"]
            dg_hours = item["dg_hours"]

            total_litres = (
                me_litres
                + aux_litres
                + dg_litres
            )

            me_lph = (
                me_litres / me_hours
                if me_hours > ZERO
                else None
            )

            aux_lph = (
                aux_litres / aux_hours
                if aux_hours > ZERO
                else None
            )

            dg_lph = (
                dg_litres / dg_hours
                if dg_hours > ZERO
                else None
            )

            results.append(
                {
                    "project_id": item["project_id"],
                    "project_name": item["project_name"],
                    "vessel_id": item["vessel_id"],
                    "vessel_name": item["vessel_name"],
                    "shift_name": item["shift_name"],
                    "record_count": item["record_count"],
                    "me_litres": me_litres,
                    "aux_litres": aux_litres,
                    "dg_litres": dg_litres,
                    "total_litres": total_litres,
                    "me_lph": me_lph,
                    "aux_lph": aux_lph,
                    "dg_lph": dg_lph,
                    "transfer_out": item["transfer_out"],
                }
            )

        results.sort(
            key=lambda item: (
                item["project_name"] or "",
                item["vessel_name"],
                item["shift_name"] or "",
            )
        )

        return results


    @staticmethod
    def get_management_summary(
        db: Session,
        from_date: date,
        to_date: date,
        vessel_ids: list[int] | None = None,
    ) -> dict:
        if from_date > to_date:
            raise ValueError(
                "from_date cannot be later than to_date."
            )

        vessel_query = (
            select(Vessel, Project)
            .join(Project, Project.id == Vessel.project_id)
            .where(Vessel.is_active.is_(True))
            .order_by(
                Project.name.asc(),
                Vessel.name.asc(),
            )
        )

        if vessel_ids:
            vessel_query = vessel_query.where(
                Vessel.id.in_(vessel_ids)
            )

        vessel_records = db.execute(vessel_query).all()

        latest_closing = DashboardService.get_latest_closing_by_vessel(
            db=db,
            vessel_ids=[vessel.id for vessel, _ in vessel_records],
        )

        vessel_totals = []
        project_data: dict[int, dict] = {}

        total_fuel = ZERO
        total_consumption = ZERO
        total_transfer_out = ZERO

        total_me_consumption = ZERO
        total_aux_consumption = ZERO
        total_dg_consumption = ZERO

        total_me_hours = ZERO
        total_aux_hours = ZERO
        total_dg_hours = ZERO

        for vessel, project in vessel_records:
            shifts_query = select(Shift).where(
                Shift.vessel_id == vessel.id,
                Shift.shift_date >= from_date,
                Shift.shift_date <= to_date,
            )

            shifts = db.scalars(shifts_query).all()

            me_consumption = ZERO
            aux_consumption = ZERO
            dg_consumption = ZERO

            me_hours = ZERO
            aux_hours = ZERO
            dg_hours = ZERO

            transfer_out = ZERO

            for shift in shifts:
                engine_data = DashboardService._get_engine_data(
                    db,
                    shift.id,
                )

                me_consumption += engine_data["me_consumption"]
                aux_consumption += engine_data["aux_consumption"]
                dg_consumption += engine_data["dg_consumption"]

                me_hours += engine_data["me_hours"]
                aux_hours += engine_data["aux_hours"]
                dg_hours += engine_data["dg_hours"]

                balance = FuelService.calculate_shift_balance(
                    db,
                    shift.id,
                )

                transfer_out += Decimal(
                    str(balance["transfer_out"] or 0)
                )

            total_vessel_consumption = (
                me_consumption
                + aux_consumption
                + dg_consumption
            )

            current_fuel = latest_closing.get(
                vessel.id,
                ZERO,
            )

            threshold = Decimal(
                str(vessel.fuel_threshold_litres or 0)
            )

            low_fuel = (
                threshold > ZERO
                and current_fuel <= threshold
            )

            negative_balance = current_fuel < ZERO

            me_lph = (
                me_consumption / me_hours
                if me_hours > ZERO
                else None
            )

            aux_lph = (
                aux_consumption / aux_hours
                if aux_hours > ZERO
                else None
            )

            dg_lph = (
                dg_consumption / dg_hours
                if dg_hours > ZERO
                else None
            )

            vessel_totals.append(
                {
                    "project_id": project.id,
                    "project_name": project.name,
                    "vessel_id": vessel.id,
                    "vessel_name": vessel.name,
                    "current_fuel": current_fuel,
                    "fuel_threshold_litres": threshold,
                    "low_fuel": low_fuel,
                    "negative_balance": negative_balance,
                    "me_consumption": me_consumption,
                    "aux_consumption": aux_consumption,
                    "dg_consumption": dg_consumption,
                    "total_consumption": total_vessel_consumption,
                    "me_hours": me_hours,
                    "aux_hours": aux_hours,
                    "dg_hours": dg_hours,
                    "total_hours": (
                        me_hours
                        + aux_hours
                        + dg_hours
                    ),
                    "me_lph": me_lph,
                    "aux_lph": aux_lph,
                    "dg_lph": dg_lph,
                }
            )

            if project.id not in project_data:
                project_data[project.id] = {
                    "project_id": project.id,
                    "project_name": project.name,
                    "vessel_count": 0,
                    "current_fuel": ZERO,
                    "total_consumption": ZERO,
                    "me_consumption": ZERO,
                    "aux_consumption": ZERO,
                    "dg_consumption": ZERO,
                    "me_hours": ZERO,
                    "aux_hours": ZERO,
                    "dg_hours": ZERO,
                    "transfer_out": ZERO,
                }

            project_item = project_data[project.id]

            project_item["vessel_count"] += 1
            project_item["current_fuel"] += current_fuel
            project_item["total_consumption"] += total_vessel_consumption

            project_item["me_consumption"] += me_consumption
            project_item["aux_consumption"] += aux_consumption
            project_item["dg_consumption"] += dg_consumption

            project_item["me_hours"] += me_hours
            project_item["aux_hours"] += aux_hours
            project_item["dg_hours"] += dg_hours

            project_item["transfer_out"] += transfer_out

            total_fuel += current_fuel
            total_consumption += total_vessel_consumption
            total_transfer_out += transfer_out

            total_me_consumption += me_consumption
            total_aux_consumption += aux_consumption
            total_dg_consumption += dg_consumption

            total_me_hours += me_hours
            total_aux_hours += aux_hours
            total_dg_hours += dg_hours

        project_totals = list(project_data.values())

        total_me_lph = (
            total_me_consumption / total_me_hours
            if total_me_hours > ZERO
            else None
        )

        total_aux_lph = (
            total_aux_consumption / total_aux_hours
            if total_aux_hours > ZERO
            else None
        )

        total_dg_lph = (
            total_dg_consumption / total_dg_hours
            if total_dg_hours > ZERO
            else None
        )

        sounding_statuses = SoundingService.get_all_vessel_statuses(
            db=db,
            report_date=to_date,
        )

        if vessel_ids:
            selected_vessels = set(vessel_ids)

            sounding_statuses = [
                item
                for item in sounding_statuses
                if item["vessel_id"] in selected_vessels
            ]

        sounding_expected = len(sounding_statuses)

        sounding_submitted = sum(
            1
            for item in sounding_statuses
            if item["status"] == "SUBMITTED"
        )

        sounding_late = sum(
            1
            for item in sounding_statuses
            if item["status"] == "LATE"
        )

        sounding_missing = sum(
            1
            for item in sounding_statuses
            if item["status"] == "MISSING"
        )

        sounding_due = sum(
            1
            for item in sounding_statuses
            if item["status"] == "DUE"
        )

        completed_soundings = (
            sounding_submitted
            + sounding_late
        )

        sounding_compliance_percentage = (
            (completed_soundings / sounding_expected) * 100
            if sounding_expected > 0
            else 100.0
        )

        return {
            "from_date": from_date,
            "to_date": to_date,
            "project_totals": project_totals,
            "vessel_totals": vessel_totals,
            "total_fuel": total_fuel,
            "total_consumption": total_consumption,
            "total_transfer_out": total_transfer_out,
            "me_consumption": total_me_consumption,
            "aux_consumption": total_aux_consumption,
            "dg_consumption": total_dg_consumption,
            "me_hours": total_me_hours,
            "aux_hours": total_aux_hours,
            "dg_hours": total_dg_hours,
            "total_hours": (
                total_me_hours
                + total_aux_hours
                + total_dg_hours
            ),
            "me_lph": total_me_lph,
            "aux_lph": total_aux_lph,
            "dg_lph": total_dg_lph,
            "sounding_expected": sounding_expected,
            "sounding_submitted": sounding_submitted,
            "sounding_late": sounding_late,
            "sounding_missing": sounding_missing,
            "sounding_due": sounding_due,
            "sounding_compliance_percentage": round(
                sounding_compliance_percentage,
                2,
            ),
        }




    @staticmethod
    def get_dashboard_charts(
        db: Session,
        from_date: date,
        to_date: date,
        vessel_ids: list[int] | None = None,
    ) -> dict:
        if from_date > to_date:
            raise ValueError(
                "from_date cannot be later than to_date."
            )

        shift_query = (
            select(Shift, Vessel)
            .join(Vessel, Vessel.id == Shift.vessel_id)
            .where(
                Shift.shift_date >= from_date,
                Shift.shift_date <= to_date,
                Vessel.is_active.is_(True),
            )
            .order_by(
                Shift.shift_date.asc(),
                Shift.id.asc(),
            )
        )

        if vessel_ids:
            shift_query = shift_query.where(
                Shift.vessel_id.in_(vessel_ids)
            )

        shift_records = db.execute(shift_query).all()

        daily_data: dict[date, dict] = {}
        vessel_data: dict[int, dict] = {}
        closing_data: dict[tuple[int, date], dict] = {}

        for shift, vessel in shift_records:
            if shift.shift_date not in daily_data:
                daily_data[shift.shift_date] = {
                    "me_litres": ZERO,
                    "aux_litres": ZERO,
                    "dg_litres": ZERO,
                    "me_hours": ZERO,
                    "aux_hours": ZERO,
                    "dg_hours": ZERO,
                }

            daily = daily_data[shift.shift_date]

            engine_data = DashboardService._get_engine_data(
                db,
                shift.id,
            )

            daily["me_litres"] += engine_data["me_consumption"]
            daily["aux_litres"] += engine_data["aux_consumption"]
            daily["dg_litres"] += engine_data["dg_consumption"]

            daily["me_hours"] += engine_data["me_hours"]
            daily["aux_hours"] += engine_data["aux_hours"]
            daily["dg_hours"] += engine_data["dg_hours"]

            if vessel.id not in vessel_data:
                vessel_data[vessel.id] = {
                    "vessel_id": vessel.id,
                    "vessel_name": vessel.name,
                    "consumption": ZERO,
                }

            vessel_data[vessel.id]["consumption"] += (
                engine_data["me_consumption"]
                + engine_data["aux_consumption"]
                + engine_data["dg_consumption"]
            )

            balance = FuelService.calculate_shift_balance(
                db,
                shift.id,
            )

            closing_fuel = Decimal(
                str(balance["closing_fuel"] or 0)
            )

            closing_key = (
                vessel.id,
                shift.shift_date,
            )

            # The last shift of the day is the daily closing.
            existing = closing_data.get(closing_key)

            if (
                existing is None
                or shift.id > existing["shift_id"]
            ):
                closing_data[closing_key] = {
                    "shift_id": shift.id,
                    "vessel_id": vessel.id,
                    "vessel_name": vessel.name,
                    "date": shift.shift_date,
                    "closing_fuel": closing_fuel,
                }

        daily_fuel_consumption = []
        engine_consumption = []
        engine_lph = []

        current_date = from_date

        while current_date <= to_date:
            daily = daily_data.get(
                current_date,
                {
                    "me_litres": ZERO,
                    "aux_litres": ZERO,
                    "dg_litres": ZERO,
                    "me_hours": ZERO,
                    "aux_hours": ZERO,
                    "dg_hours": ZERO,
                },
            )

            total_litres = (
                daily["me_litres"]
                + daily["aux_litres"]
                + daily["dg_litres"]
            )

            daily_fuel_consumption.append(
                {
                    "date": current_date,
                    "consumption": total_litres,
                }
            )

            engine_consumption.append(
                {
                    "date": current_date,
                    "me_litres": daily["me_litres"],
                    "aux_litres": daily["aux_litres"],
                    "dg_litres": daily["dg_litres"],
                    "total_litres": total_litres,
                }
            )

            engine_lph.append(
                {
                    "date": current_date,
                    "me_lph": (
                        daily["me_litres"]
                        / daily["me_hours"]
                        if daily["me_hours"] > ZERO
                        else None
                    ),
                    "aux_lph": (
                        daily["aux_litres"]
                        / daily["aux_hours"]
                        if daily["aux_hours"] > ZERO
                        else None
                    ),
                    "dg_lph": (
                        daily["dg_litres"]
                        / daily["dg_hours"]
                        if daily["dg_hours"] > ZERO
                        else None
                    ),
                }
            )

            current_date += timedelta(days=1)

        closing_balance = sorted(
            closing_data.values(),
            key=lambda item: (
                item["date"],
                item["vessel_name"],
            ),
        )

        total_me = sum(
            (
                item["me_litres"]
                for item in daily_data.values()
            ),
            ZERO,
        )

        total_aux = sum(
            (
                item["aux_litres"]
                for item in daily_data.values()
            ),
            ZERO,
        )

        total_dg = sum(
            (
                item["dg_litres"]
                for item in daily_data.values()
            ),
            ZERO,
        )

        total_engine = (
            total_me
            + total_aux
            + total_dg
        )

        vessel_comparison = sorted(
            vessel_data.values(),
            key=lambda item: item["vessel_name"],
        )

        return {
            "daily_fuel_consumption": daily_fuel_consumption,
            "engine_consumption": engine_consumption,
            "engine_lph": engine_lph,
            "closing_balance": closing_balance,
            "engine_split": {
                "me_litres": total_me,
                "aux_litres": total_aux,
                "dg_litres": total_dg,
                "total_litres": total_engine,
            },
            "vessel_comparison": vessel_comparison,
        }



    @staticmethod
    def get_efficiency_report(
        db: Session,
        from_date: date,
        to_date: date,
    ) -> list[dict]:
        if from_date > to_date:
            raise ValueError(
                "from_date cannot be later than to_date."
            )

        query = (
            select(Vessel, Project)
            .join(Project, Project.id == Vessel.project_id)
            .where(
                Vessel.is_active.is_(True),
            )
            .order_by(
                Project.name.asc(),
                Vessel.name.asc(),
            )
        )

        vessels = db.execute(query).all()

        days = (to_date - from_date).days + 1

        results = []

        for vessel, project in vessels:
            shifts_query = select(Shift).where(
                Shift.vessel_id == vessel.id,
                Shift.shift_date >= from_date,
                Shift.shift_date <= to_date,
            )

            shifts = db.scalars(shifts_query).all()

            me_litres = ZERO
            me_hours = ZERO

            aux_litres = ZERO
            aux_hours = ZERO

            dg_litres = ZERO
            dg_hours = ZERO

            for shift in shifts:
                engine_data = DashboardService._get_engine_data(
                    db,
                    shift.id,
                )

                me_litres += engine_data["me_consumption"]
                me_hours += engine_data["me_hours"]

                aux_litres += engine_data["aux_consumption"]
                aux_hours += engine_data["aux_hours"]

                dg_litres += engine_data["dg_consumption"]
                dg_hours += engine_data["dg_hours"]

            total_litres = (
                me_litres
                + aux_litres
                + dg_litres
            )

            total_hours = (
                me_hours
                + aux_hours
                + dg_hours
            )

            me_lph = (
                me_litres / me_hours
                if me_hours > ZERO
                else None
            )

            aux_lph = (
                aux_litres / aux_hours
                if aux_hours > ZERO
                else None
            )

            dg_lph = (
                dg_litres / dg_hours
                if dg_hours > ZERO
                else None
            )

            results.append(
                {
                    "project_id": project.id,
                    "project_name": project.name,
                    "vessel_id": vessel.id,
                    "vessel_name": vessel.name,
                    "days": days,
                    "me_litres": me_litres,
                    "me_hours": me_hours,
                    "me_lph": me_lph,
                    "aux_litres": aux_litres,
                    "aux_hours": aux_hours,
                    "aux_lph": aux_lph,
                    "dg_litres": dg_litres,
                    "dg_hours": dg_hours,
                    "dg_lph": dg_lph,
                    "total_litres": total_litres,
                    "total_hours": total_hours,
                }
            )

        return results



    