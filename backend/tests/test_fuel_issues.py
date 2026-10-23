import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import backend.models  # noqa: F401
from backend.database import Base
from backend.models.fuel import FuelTransaction, FuelTransactionType
from backend.models.issue import FuelIssue, IssueStatus
from backend.models.vessel import Vessel
from backend.services.fuel_service import FuelService
from backend.services.issue_service import IssueService


@compiles(JSONB, "sqlite")
def _jsonb_as_json_on_sqlite(type_, compiler, **kw):
    return "JSON"


class FuelIssueTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        vessel = Vessel(project_id=1, name="Tracked", code="T1", vessel_type="Dredger",
                        is_active=True, fuel_threshold_litres=Decimal("0"))
        self.db.add(vessel)
        self.db.flush()
        self.vessel_id = vessel.id
        self.shift = FuelService.establish_initial_opening_fuel(
            self.db, vessel.id, date(2026, 10, 20), Decimal("100"), 1
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _create(self, quantity="25"):
        return IssueService.create(
            self.db, vessel_id=self.vessel_id, shift_id=self.shift.id,
            receiving_vessel="Small steel boat", quantity=Decimal(quantity),
            notes="Fuel issue", user_id=1,
        )

    def test_pending_issue_does_not_change_shift_balance(self):
        self._create()
        balance = FuelService.calculate_shift_balance(self.db, self.shift.id)
        self.assertEqual(balance["closing_fuel"], Decimal("100"))
        self.assertEqual(self.db.scalars(select(FuelTransaction)).all(), [])

    def test_approval_deducts_once_from_source_shift(self):
        issue = self._create("25.125")
        IssueService.review(self.db, issue_id=issue.id, approved=True, reviewer_id=2)
        self.db.flush()
        balance = FuelService.calculate_shift_balance(self.db, self.shift.id)
        self.assertEqual(balance["issue_out"], Decimal("25.125"))
        self.assertEqual(balance["closing_fuel"], Decimal("74.875"))
        transactions = self.db.scalars(select(FuelTransaction).where(
            FuelTransaction.reference_type == "FUEL_ISSUE",
            FuelTransaction.reference_id == issue.id,
        )).all()
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].transaction_type, FuelTransactionType.ISSUE_OUT.value)
        with self.assertRaisesRegex(ValueError, "Only pending issues"):
            IssueService.review(self.db, issue_id=issue.id, approved=True, reviewer_id=2)
        self.assertEqual(self.db.get(FuelIssue, issue.id).status, IssueStatus.APPROVED.value)

    def test_rejected_issue_does_not_change_balance(self):
        issue = self._create()
        IssueService.review(self.db, issue_id=issue.id, approved=False,
                            reviewer_id=2, remark="Not authorized")
        self.db.flush()
        self.assertEqual(FuelService.calculate_shift_balance(self.db, self.shift.id)["closing_fuel"], Decimal("100"))
        self.assertEqual(self.db.scalars(select(FuelTransaction)).all(), [])

    def test_approval_cannot_issue_more_than_available_fuel(self):
        issue = self._create("100.001")
        with self.assertRaisesRegex(ValueError, "exceeds the source shift"):
            IssueService.review(self.db, issue_id=issue.id, approved=True, reviewer_id=2)
        self.db.rollback()

    def test_receiving_vessel_must_not_be_tracked(self):
        with self.assertRaisesRegex(ValueError, "only be made to an untracked"):
            IssueService.create(
                self.db, vessel_id=self.vessel_id, shift_id=self.shift.id,
                receiving_vessel="Tracked", quantity=Decimal("1"),
                notes=None, user_id=1,
            )

    def test_issue_cannot_be_submitted_from_a_closed_shift(self):
        self.shift.status = "CLOSED"
        self.db.flush()
        with self.assertRaisesRegex(ValueError, "only be issued from an open shift"):
            self._create()

    def test_issue_cannot_be_approved_after_source_shift_closes(self):
        issue = self._create()
        self.shift.status = "CLOSED"
        self.db.flush()
        with self.assertRaisesRegex(ValueError, "source shift is closed"):
            IssueService.review(self.db, issue_id=issue.id, approved=True, reviewer_id=2)
        self.assertEqual(self.db.scalars(select(FuelTransaction)).all(), [])

    def test_issue_approval_reconciles_downstream_shift_balances(self):
        issue = self._create("25")
        self.shift.status = "CLOSED"
        self.shift.calculated_closing_fuel = Decimal("100")
        self.db.flush()
        evening = FuelService.get_or_create_shift(
            self.db, self.vessel_id, date(2026, 10, 20), "EVENING", 1
        )
        FuelService.add_transaction(
            self.db, self.vessel_id, date(2026, 10, 20), "EVENING",
            FuelTransactionType.RECEIPT, Decimal("50"), 1,
        )
        evening.status = "CLOSED"
        evening.calculated_closing_fuel = Decimal("150")
        self.db.flush()
        next_shift = FuelService.get_or_create_shift(
            self.db, self.vessel_id, date(2026, 10, 21), "MORNING", 1
        )
        FuelService.reopen_shift(self.db, self.shift.id, 1, "Approve prior issue")

        with self.assertRaisesRegex(ValueError, "downstream reconciliation is required first"):
            IssueService.review(self.db, issue_id=issue.id, approved=True, reviewer_id=2)
        IssueService.review(self.db, issue_id=issue.id, approved=True, reviewer_id=2,
                            reconcile_downstream=True)

        self.assertEqual(self.shift.calculated_closing_fuel, Decimal("75.000"))
        self.assertEqual(evening.opening_fuel, Decimal("75.000"))
        self.assertEqual(evening.calculated_closing_fuel, Decimal("125.000"))
        self.assertEqual(next_shift.opening_fuel, Decimal("125.000"))


if __name__ == "__main__":
    unittest.main()
