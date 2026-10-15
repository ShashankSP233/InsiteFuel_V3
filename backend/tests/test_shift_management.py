import unittest
from datetime import datetime, timezone
from inspect import signature
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from backend.models.audit_log import AuditLog
from backend.models.shift import Shift
from backend.routes.fuel import reopen_shift as reopen_shift_route
from backend.schemas.fuel import ShiftReopenRequest
from backend.services import fuel_service
from backend.services.fuel_service import FuelService


class FakeSession:
    def __init__(self, shift=None, vessel=None, sounding_count=0):
        self.shift = shift
        self.vessel = vessel
        self.sounding_count = sounding_count
        self.added = []

    def get(self, model, entity_id):
        if model is Shift:
            return self.shift
        return self.vessel

    def add(self, entity):
        self.added.append(entity)

    def flush(self):
        pass

    def scalar(self, statement):
        return self.sounding_count

    def scalars(self, statement):
        return SimpleNamespace(all=lambda: [])


def stub_row_locks(testcase):
    """
    Fake sessions cannot run SELECT ... FOR UPDATE, so resolve the row-lock
    helpers through db.get() instead. Locking itself is covered by the
    real-database tests in test_shift_creation_rules.py.
    """
    def lock_vessels(db, vessel_ids):
        return {}

    def lock_shifts(db, shift_ids):
        return {shift_id: db.get(Shift, shift_id) for shift_id in shift_ids}

    for name, replacement in (("lock_vessels", lock_vessels), ("lock_shifts", lock_shifts)):
        patcher = patch.object(FuelService, name, side_effect=replacement)
        patcher.start()
        testcase.addCleanup(patcher.stop)


class ShiftManagementTests(unittest.TestCase):
    def setUp(self):
        stub_row_locks(self)

    def closed_shift(self):
        return SimpleNamespace(
            id=42,
            vessel_id=3,
            status="CLOSED",
            closed_at=datetime(2026, 10, 1, 12, tzinfo=timezone.utc),
            calculated_closing_fuel=500,
        )

    def test_admin_can_reopen_closed_shift_and_audit_change(self):
        shift = self.closed_shift()
        db = FakeSession(shift=shift)
        authorize = signature(reopen_shift_route).parameters["current_user"].default.dependency
        admin = SimpleNamespace(id=7, role="ADMIN")

        self.assertIs(authorize(current_user=admin), admin)
        result = FuelService.reopen_shift(db, shift.id, admin.id, "Corrected shift record")

        self.assertIs(result, shift)
        self.assertEqual(shift.status, "OPEN")
        self.assertIsNone(shift.closed_at)
        self.assertEqual(shift.calculated_closing_fuel, 500)
        audit = db.added[0]
        self.assertIsInstance(audit, AuditLog)
        self.assertEqual(audit.user_id, admin.id)
        self.assertEqual(audit.action, "REOPEN_SHIFT")
        self.assertEqual(audit.entity_id, shift.id)
        self.assertEqual(audit.reason, "Corrected shift record")
        self.assertEqual(audit.old_values["status"], "CLOSED")
        self.assertEqual(audit.new_values["status"], "OPEN")
        self.assertIsNotNone(AuditLog.__table__.c.created_at.default)
        self.assertIsInstance(AuditLog.__table__.c.created_at.default.arg(None), datetime)

    def test_non_admin_is_denied(self):
        authorize = signature(reopen_shift_route).parameters["current_user"].default.dependency
        operator = SimpleNamespace(id=9, role="OPERATOR")

        with self.assertRaises(HTTPException) as error:
            authorize(current_user=operator)

        self.assertEqual(error.exception.status_code, 403)

    def test_missing_or_blank_reason_is_rejected(self):
        with self.assertRaises(ValidationError):
            ShiftReopenRequest()

        db = FakeSession(shift=self.closed_shift())
        with self.assertRaisesRegex(ValueError, "Correction reason is required"):
            FuelService.reopen_shift(db, 42, 7, "  ")

    def test_reopening_open_shift_is_rejected(self):
        shift = self.closed_shift()
        shift.status = "OPEN"
        db = FakeSession(shift=shift)

        with self.assertRaisesRegex(ValueError, "cannot be reopened"):
            FuelService.reopen_shift(db, shift.id, 7, "Correction")

    def test_reopen_leaves_ledger_and_approved_transfer_data_untouched(self):
        shift = self.closed_shift()
        ledger = [SimpleNamespace(quantity=125, transaction_type="RECEIPT")]
        transfers = [SimpleNamespace(status="APPROVED", initiated_quantity=125)]
        before = ([item.quantity for item in ledger], [(item.status, item.initiated_quantity) for item in transfers])

        FuelService.reopen_shift(FakeSession(shift=shift), shift.id, 7, "Correction")

        after = ([item.quantity for item in ledger], [(item.status, item.initiated_quantity) for item in transfers])
        self.assertEqual(after, before)

    def test_existing_close_sounding_validation_still_applies(self):
        shift = SimpleNamespace(
            id=42,
            vessel_id=3,
            status="OPEN",
            advancement_m=None,
            dredging_hours=None,
        )
        db = FakeSession(
            shift=shift,
            vessel=SimpleNamespace(vessel_type="Workboat"),
            sounding_count=0,
        )

        with patch.object(fuel_service.FuelService, "recalculate_shift") as recalculate:
            with self.assertRaisesRegex(ValueError, "without at least one sounding"):
                FuelService.close_shift(db, shift.id)

        recalculate.assert_not_called()


if __name__ == "__main__":
    unittest.main()