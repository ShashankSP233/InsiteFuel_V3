from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.services.audit_service import AuditService
from backend.services.engine_service import EngineService
from backend.services.fuel_service import FuelService


def test_create_engine_event_preserves_submitted_consumption():
    db = Mock()
    db.get.side_effect = [
        SimpleNamespace(
            is_active=True,
            vessel_id=1,
            equipment_type="MAIN_ENGINE",
        ),
        SimpleNamespace(
            vessel_id=1,
            shift_date=datetime(2026, 10, 12).date(),
            shift_name="MORNING",
        ),
    ]
    start_time = datetime(2026, 10, 12, 0, 0)

    with (
        patch.object(FuelService, "record_engine_consumption") as record_consumption,
        patch.object(AuditService, "log"),
    ):
        event = EngineService.create_engine_event(
            db=db,
            equipment_id=1,
            shift_id=1,
            start_time=start_time,
            stop_time=start_time + timedelta(hours=7),
            lph_rate=Decimal("72.714"),
            created_by_user_id=1,
            consumption=Decimal("509"),
        )

    assert event.consumption == Decimal("509.000")
    assert record_consumption.call_args.kwargs["quantity"] == Decimal("509.000")