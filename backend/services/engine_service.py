from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.models.engine import EngineEvent
from backend.models.equipment import Equipment
from backend.models.shift import Shift
from backend.services.fuel_service import FuelService
from backend.services.audit_service import AuditService

class EngineService:

    @staticmethod
    def calculate_hours_run(
        start_time: datetime,
        stop_time: datetime,
    ) -> Decimal:
        if stop_time <= start_time:
            raise ValueError("stop_time must be after start_time")

        duration = stop_time - start_time

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

        # Calculate fuel consumption
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