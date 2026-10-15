import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from inspect import signature
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from backend.models.audit_log import AuditLog
from backend.models.engine import EngineEvent
from backend.models.equipment import Equipment
from backend.models.fuel import FuelTransactionType
from backend.models.shift import Shift
from backend.models.user import UserRole
from backend.dependencies import get_current_user
from backend.routes.engine import (
    admin_create_engine_event,
    admin_delete_engine_event,
    admin_update_engine_event,
    create_engine_event,
)
from backend.schemas.engine import EngineEventAdminUpdate, EngineEventCreate
from backend.services.engine_service import EngineService
from backend.services.fuel_service import FuelService


class FakeSession:
    def __init__(self, *, shift, equipment, event=None, transactions=None):
        self.entities = {
            (Shift, shift.id): shift,
            (Equipment, equipment.id): equipment,
        }
        if event is not None:
            self.entities[(EngineEvent, event.id)] = event
        self.transactions = list(transactions or [])
        self.added = []
        self.deleted = []

    def get(self, model, entity_id):
        return self.entities.get((model, entity_id))

    def add(self, entity):
        if isinstance(entity, EngineEvent) and entity.id is None:
            entity.id = 101
            self.entities[(EngineEvent, entity.id)] = entity
        self.added.append(entity)

    def scalars(self, statement):
        return SimpleNamespace(all=lambda: list(self.transactions))

    def scalar(self, statement):
        return None

    def flush(self):
        pass

    def delete(self, entity):
        self.deleted.append(entity)
        if entity in self.transactions:
            self.transactions.remove(entity)
        self.entities.pop((EngineEvent, getattr(entity, "id", None)), None)


class EngineEventAdminTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 13, 8, tzinfo=timezone.utc)
        self.stop = self.start + timedelta(hours=2)
        self.shift = SimpleNamespace(
            id=8,
            vessel_id=3,
            status="OPEN",
            shift_date=self.start.date(),
            shift_name="MORNING",
        )
        self.equipment = SimpleNamespace(
            id=4,
            vessel_id=3,
            is_active=True,
            equipment_type="MAIN_ENGINE",
        )
        self.event = SimpleNamespace(
            id=55,
            shift_id=8,
            equipment_id=4,
            engine_type="MAIN_ENGINE",
            start_time=self.start,
            stop_time=self.stop,
            hours_run=Decimal("2.000"),
            consumption=Decimal("20.000"),
            lph_rate=Decimal("10.000"),
            active=True,
            remarks="before",
        )
        self.linked = SimpleNamespace(
            id=91,
            shift_id=8,
            vessel_id=3,
            transaction_type=FuelTransactionType.ENGINE_CONSUMPTION.value,
            reference_type="ENGINE_EVENT",
            reference_id=55,
            quantity=Decimal("20.000"),
        )
        self.unrelated_transaction = SimpleNamespace(
            id=92, quantity=Decimal("15.000"), transaction_type="RECEIPT"
        )
        self.approved_transfer = SimpleNamespace(
            id=24, status="APPROVED", initiated_quantity=Decimal("12.000")
        )
        self.db = FakeSession(
            shift=self.shift,
            equipment=self.equipment,
            event=self.event,
            transactions=[self.linked],
        )

    def test_all_admin_routes_reject_non_admin_and_allow_admin(self):
        operator = SimpleNamespace(id=2, role=UserRole.OPERATOR.value)
        admin = SimpleNamespace(id=1, role=UserRole.ADMIN.value)
        for endpoint in (
            admin_create_engine_event,
            admin_update_engine_event,
            admin_delete_engine_event,
        ):
            dependency = signature(endpoint).parameters["current_user"].default.dependency
            with self.subTest(endpoint=endpoint.__name__):
                with self.assertRaises(HTTPException) as error:
                    dependency(current_user=operator)
                self.assertEqual(error.exception.status_code, 403)
                self.assertIs(dependency(current_user=admin), admin)

    def test_existing_operator_create_route_keeps_its_auth_and_service_flow(self):
        dependency = signature(create_engine_event).parameters["current_user"].default.dependency
        self.assertIs(dependency, get_current_user)
        operator = SimpleNamespace(id=12, role=UserRole.OPERATOR.value)
        payload = EngineEventCreate(
            equipment_id=4,
            shift_id=8,
            start_time=self.start,
            stop_time=self.stop,
            lph_rate=Decimal("10"),
            consumption=Decimal("20"),
            remarks="operator event",
        )
        with patch(
            "backend.routes.engine.EngineService.create_engine_event",
            return_value=self.event,
        ) as create:
            response = create_engine_event(payload, db=Mock(), current_user=operator)

        self.assertIs(response, self.event)
        self.assertEqual(create.call_args.kwargs["created_by_user_id"], operator.id)
        self.assertEqual(create.call_args.kwargs["shift_id"], self.shift.id)

    def test_admin_create_uses_existing_engine_and_ledger_service(self):
        payload = EngineEventCreate(
            equipment_id=4,
            shift_id=8,
            start_time=self.start,
            stop_time=self.stop,
            lph_rate=Decimal("10"),
            consumption=Decimal("20"),
            remarks="new event",
        )
        with patch.object(
            EngineService,
            "calculate_hours_run",
            return_value=Decimal("2.000"),
        ), patch("backend.services.engine_service.FuelService.record_engine_consumption") as record:
            event = EngineService.create_engine_event(
                db=self.db,
                equipment_id=payload.equipment_id,
                shift_id=payload.shift_id,
                start_time=payload.start_time,
                stop_time=payload.stop_time,
                lph_rate=payload.lph_rate,
                consumption=payload.consumption,
                remarks=payload.remarks,
                created_by_user_id=1,
            )

        self.assertEqual(event.shift_id, self.shift.id)
        self.assertEqual(event.created_by_user_id, 1)
        record.assert_called_once()
        self.assertEqual(record.call_args.kwargs["engine_event_id"], event.id)
        self.assertEqual(self.shift.status, "OPEN")
        self.assertTrue(any(isinstance(item, AuditLog) for item in self.db.added))

    def test_create_rejects_closed_shift_and_equipment_for_another_vessel(self):
        self.shift.status = "CLOSED"
        with self.assertRaisesRegex(ValueError, "OPEN shift"):
            EngineService.create_engine_event(
                self.db,
                4,
                8,
                self.start,
                self.stop,
                Decimal("10"),
                1,
                Decimal("20"),
            )
        self.assertEqual(self.shift.status, "CLOSED")

        self.shift.status = "OPEN"
        self.equipment.vessel_id = 99
        with self.assertRaisesRegex(ValueError, "does not belong"):
            EngineService.create_engine_event(
                self.db,
                4,
                8,
                self.start,
                self.stop,
                Decimal("10"),
                1,
                Decimal("20"),
            )

    def test_update_syncs_only_linked_transaction_and_audits_old_new_values(self):
        data = EngineEventAdminUpdate(
            equipment_id=4,
            start_time=self.start + timedelta(minutes=15),
            stop_time=self.stop,
            lph_rate=Decimal("15"),
            consumption=Decimal("30"),
            remarks="corrected",
            reason="Corrected log",
        )
        with patch("backend.services.engine_service.FuelService.recalculate_shift") as recalculate:
            event = EngineService.update_engine_event(
                self.db,
                event_id=55,
                shift_id=8,
                equipment_id=data.equipment_id,
                start_time=data.start_time,
                stop_time=data.stop_time,
                lph_rate=data.lph_rate,
                consumption=data.consumption,
                remarks=data.remarks,
                corrected_by_user_id=1,
                reason=data.reason,
            )

        self.assertEqual(event.consumption, Decimal("30.000"))
        self.assertEqual(self.linked.quantity, Decimal("30.000"))
        recalculate.assert_called_once_with(self.db, self.shift.id)
        audit = next(item for item in self.db.added if isinstance(item, AuditLog))
        self.assertEqual(audit.user_id, 1)
        self.assertEqual(audit.reason, "Corrected log")
        self.assertEqual(audit.old_values["consumption"], "20.000")
        self.assertEqual(audit.old_values["fuel_transaction"]["quantity"], "20.000")
        self.assertEqual(audit.new_values["consumption"], "30.000")
        self.assertEqual(audit.new_values["fuel_transaction"]["quantity"], "30.000")
        self.assertEqual(self.unrelated_transaction.quantity, Decimal("15.000"))
        self.assertEqual(self.approved_transfer.status, "APPROVED")
        self.assertEqual(self.shift.status, "OPEN")

    def test_delete_removes_only_linked_records_and_audits_previous_values(self):
        with patch("backend.services.engine_service.FuelService.recalculate_shift") as recalculate:
            EngineService.delete_engine_event(
                self.db,
                event_id=55,
                shift_id=8,
                deleted_by_user_id=1,
                reason="Incorrect entry",
            )

        self.assertEqual(self.db.deleted, [self.linked, self.event])
        recalculate.assert_called_once_with(self.db, self.shift.id)
        audit = next(item for item in self.db.added if isinstance(item, AuditLog))
        self.assertEqual(audit.action, "DELETE_ENGINE_EVENT")
        self.assertEqual(audit.user_id, 1)
        self.assertEqual(audit.reason, "Incorrect entry")
        self.assertEqual(audit.old_values["consumption"], "20.000")
        self.assertEqual(audit.old_values["fuel_transaction"]["id"], 91)
        self.assertIsNone(audit.new_values)
        self.assertEqual(self.unrelated_transaction.quantity, Decimal("15.000"))
        self.assertEqual(self.approved_transfer.status, "APPROVED")

    def test_other_shift_event_cannot_be_edited_or_deleted(self):
        with self.assertRaisesRegex(ValueError, "does not belong"):
            EngineService.update_engine_event(
                self.db,
                event_id=55,
                shift_id=77,
                equipment_id=4,
                start_time=self.start,
                stop_time=self.stop,
                lph_rate=Decimal("10"),
                consumption=Decimal("20"),
                corrected_by_user_id=1,
                reason="Correction",
            )
        with self.assertRaisesRegex(ValueError, "does not belong"):
            EngineService.delete_engine_event(
                self.db,
                event_id=55,
                shift_id=77,
                deleted_by_user_id=1,
                reason="Correction",
            )
        self.assertEqual(self.db.deleted, [])
        self.assertEqual(self.linked.quantity, Decimal("20.000"))

    def test_event_ledger_correction_is_blocked_when_successor_shift_exists(self):
        with patch.object(FuelService, "has_later_shift", return_value=True):
            with self.assertRaisesRegex(ValueError, "subsequent shifts"):
                EngineService.update_engine_event(
                    self.db,
                    event_id=55,
                    shift_id=8,
                    equipment_id=4,
                    start_time=self.start,
                    stop_time=self.stop,
                    lph_rate=Decimal("15"),
                    consumption=Decimal("30"),
                    corrected_by_user_id=1,
                    reason="Correction",
                )
            with self.assertRaisesRegex(ValueError, "subsequent shifts"):
                EngineService.delete_engine_event(
                    self.db,
                    event_id=55,
                    shift_id=8,
                    deleted_by_user_id=1,
                    reason="Correction",
                )

        self.assertEqual(self.event.consumption, Decimal("20.000"))
        self.assertEqual(self.linked.quantity, Decimal("20.000"))
        self.assertEqual(self.db.deleted, [])

    def test_missing_duplicate_or_inconsistent_linked_transaction_is_rejected(self):
        update_args = {
            "event_id": 55,
            "shift_id": 8,
            "equipment_id": 4,
            "start_time": self.start,
            "stop_time": self.stop,
            "lph_rate": Decimal("15"),
            "consumption": Decimal("30"),
            "corrected_by_user_id": 1,
            "reason": "Correction",
        }
        for transactions in (
            [],
            [self.linked, SimpleNamespace(**self.linked.__dict__)],
        ):
            db = FakeSession(
                shift=self.shift,
                equipment=self.equipment,
                event=self.event,
                transactions=transactions,
            )
            with self.subTest(count=len(transactions)):
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    EngineService.update_engine_event(db, **update_args)

        self.linked.quantity = Decimal("19.000")
        with self.assertRaisesRegex(ValueError, "does not match"):
            EngineService.update_engine_event(self.db, **update_args)
        self.assertEqual(self.event.consumption, Decimal("20.000"))
        self.assertEqual(self.linked.quantity, Decimal("19.000"))

    def test_closed_shift_and_blank_reasons_are_rejected(self):
        self.shift.status = "CLOSED"
        with self.assertRaisesRegex(ValueError, "OPEN shift"):
            EngineService.update_engine_event(
                self.db,
                event_id=55,
                shift_id=8,
                equipment_id=4,
                start_time=self.start,
                stop_time=self.stop,
                lph_rate=Decimal("10"),
                corrected_by_user_id=1,
                reason="Correction",
            )
        with self.assertRaisesRegex(ValueError, "OPEN shift"):
            EngineService.delete_engine_event(
                self.db,
                event_id=55,
                shift_id=8,
                deleted_by_user_id=1,
                reason="Correction",
            )
        self.assertEqual(self.shift.status, "CLOSED")
        self.shift.status = "OPEN"
        with self.assertRaisesRegex(ValueError, "Correction reason is required"):
            EngineService.update_engine_event(
                self.db,
                event_id=55,
                shift_id=8,
                equipment_id=4,
                start_time=self.start,
                stop_time=self.stop,
                lph_rate=Decimal("10"),
                corrected_by_user_id=1,
                reason="  ",
            )
        with self.assertRaisesRegex(ValueError, "Correction reason is required"):
            EngineService.delete_engine_event(
                self.db,
                event_id=55,
                shift_id=8,
                deleted_by_user_id=1,
                reason="  ",
            )
        self.assertEqual(self.event.consumption, Decimal("20.000"))

    def test_invalid_timestamps_and_consumption_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "after start_time"):
            EngineService.calculate_hours_run(self.stop, self.start)
        with self.assertRaisesRegex(ValueError, "compatible time zones"):
            EngineService.calculate_hours_run(
                self.start.replace(tzinfo=None),
                self.stop,
            )
        with self.assertRaises(ValidationError):
            EngineEventCreate(
                equipment_id=4,
                shift_id=8,
                start_time=self.start,
                stop_time=self.stop,
                lph_rate=Decimal("10"),
                consumption=Decimal("-1"),
            )
        with self.assertRaises(ValidationError):
            EngineEventAdminUpdate(
                equipment_id=4,
                start_time=self.start,
                stop_time=self.stop,
                lph_rate=Decimal("10"),
                consumption=Decimal("0"),
                reason="Correction",
            )
        with self.assertRaises(ValidationError):
            EngineEventAdminUpdate(
                equipment_id=4,
                start_time=self.start,
                stop_time=self.stop,
                lph_rate=Decimal("10"),
                consumption=Decimal("20"),
            )
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            EngineService.update_engine_event(
                self.db,
                event_id=55,
                shift_id=8,
                equipment_id=4,
                start_time=self.start,
                stop_time=self.stop,
                lph_rate=Decimal("0"),
                consumption=Decimal("0"),
                corrected_by_user_id=1,
                reason="Correction",
            )


if __name__ == "__main__":
    unittest.main()
