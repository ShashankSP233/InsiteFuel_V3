"""
Scenario tests for shift-creation rules and the "later shift" guard.

Unlike the mock-based tests, these run against a real in-memory SQLite
database, so they exercise the actual queries, ordering and locking calls.
"""
import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import backend.models  # noqa: F401  (registers every table on Base.metadata)
from backend.database import Base
from backend.models.fuel import FuelTransactionType
from backend.models.shift import Shift
from backend.models.vessel import Vessel
from backend.services.fuel_service import FuelService


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


def dec(value):
    return Decimal(str(value))


class ShiftCreationRulesTest(unittest.TestCase):
    D1 = date(2026, 10, 13)
    D2 = date(2026, 10, 14)

    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        vessel = Vessel(
            project_id=1,
            name="Test Vessel",
            code="TV1",
            vessel_type="Dredger",
            is_active=True,
            fuel_threshold_litres=Decimal("0"),
        )
        self.db.add(vessel)
        self.db.flush()
        self.vessel_id = vessel.id
        self.morning = FuelService.establish_initial_opening_fuel(
            self.db, self.vessel_id, self.D1, Decimal("1000"), created_by_user_id=1
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    # -- helpers ---------------------------------------------------------
    def _close(self, shift):
        # Mirrors close_shift: settle the closing fuel, then close.
        FuelService.recalculate_shift(self.db, shift.id)
        shift.status = "CLOSED"
        self.db.flush()

    def _new_shift(self, shift_date, shift_name):
        return FuelService.get_or_create_shift(
            self.db, self.vessel_id, shift_date, shift_name, 1
        )

    def _shift_count(self):
        return self.db.scalar(select(func.count(Shift.id)))

    # -- rule: no new shift while a previous shift is open ---------------
    def test_new_shift_is_blocked_while_previous_shift_is_open(self):
        with self.assertRaisesRegex(
            ValueError, r"Previous open shift on 2026-10-13 \(MORNING\) exists"
        ):
            self._new_shift(self.D1, "EVENING")
        self.assertEqual(self._shift_count(), 1)

    def test_next_shift_inherits_closing_fuel_once_previous_is_closed(self):
        FuelService.add_transaction(
            self.db, self.vessel_id, self.D1, "MORNING",
            FuelTransactionType.RECEIPT, Decimal("200"), 1,
        )
        self._close(self.morning)
        evening = self._new_shift(self.D1, "EVENING")
        self.assertEqual(dec(evening.opening_fuel), Decimal("1200"))
        self.assertEqual(evening.status, "OPEN")

    def test_any_earlier_open_shift_blocks_creation_not_only_the_latest(self):
        self._close(self.morning)
        evening = self._new_shift(self.D1, "EVENING")
        self._close(evening)
        FuelService.reopen_shift(self.db, self.morning.id, 1, "fix receipt")
        with self.assertRaisesRegex(
            ValueError, r"Previous open shift on 2026-10-13 \(MORNING\) exists"
        ):
            self._new_shift(self.D2, "MORNING")

    def test_morning_only_previous_day_is_not_skipped(self):
        FuelService.add_transaction(
            self.db, self.vessel_id, self.D1, "MORNING",
            FuelTransactionType.RECEIPT, Decimal("50"), 1,
        )
        self._close(self.morning)
        next_morning = self._new_shift(self.D2, "MORNING")
        self.assertEqual(dec(next_morning.opening_fuel), Decimal("1050"))

    def test_vessel_is_locked_before_any_shift_lookup(self):
        with patch.object(
            FuelService, "lock_vessels", wraps=FuelService.lock_vessels
        ) as lock:
            self._new_shift(self.D1, "MORNING")
        lock.assert_called_once()

    # -- guard: no writes to a shift that has later shifts ---------------
    def test_transactions_are_blocked_on_reopened_shift_with_later_shift(self):
        self._close(self.morning)
        evening = self._new_shift(self.D1, "EVENING")
        self._close(evening)
        FuelService.reopen_shift(self.db, self.morning.id, 1, "fix receipt")
        with self.assertRaisesRegex(ValueError, "later shifts exist"):
            FuelService.add_transaction(
                self.db, self.vessel_id, self.D1, "MORNING",
                FuelTransactionType.RECEIPT, Decimal("10"), 1,
            )

    def test_has_later_shift_orders_morning_before_evening(self):
        self._close(self.morning)
        evening = self._new_shift(self.D1, "EVENING")
        self.assertTrue(FuelService.has_later_shift(self.db, self.morning))
        self.assertFalse(FuelService.has_later_shift(self.db, evening))
        self._close(evening)
        self._new_shift(self.D2, "MORNING")
        self.assertTrue(FuelService.has_later_shift(self.db, evening))

    def test_in_memory_ordering_uses_shift_name_not_id(self):
        morning = SimpleNamespace(id=5, shift_date=self.D1, shift_name="MORNING")
        evening = SimpleNamespace(id=3, shift_date=self.D1, shift_name="EVENING")
        self.assertTrue(FuelService.is_later_shift(evening, morning))
        self.assertFalse(FuelService.is_later_shift(morning, evening))


if __name__ == "__main__":
    unittest.main()
