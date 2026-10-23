from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.models.fuel import FuelTransaction, FuelTransactionType
from backend.models.issue import FuelIssue, IssueStatus
from backend.models.shift import Shift
from backend.models.vessel import Vessel
from backend.services.audit_service import AuditService
from backend.services.fuel_service import FuelService
from backend.utils.time import now_ist


class IssueService:
    @staticmethod
    def create(db: Session, *, vessel_id: int, shift_id: int, receiving_vessel: str,
               quantity: Decimal, notes: str | None, user_id: int) -> FuelIssue:
        vessel = db.get(Vessel, vessel_id)
        shift = db.get(Shift, shift_id)
        if vessel is None or not vessel.is_active:
            raise ValueError("Source vessel not found or inactive.")
        if shift is None or shift.vessel_id != vessel_id:
            raise ValueError("Selected shift does not belong to the source vessel.")
        if shift.status != "OPEN":
            raise ValueError("Fuel can only be issued from an open shift.")
        receiver = receiving_vessel.strip()
        if not receiver:
            raise ValueError("Receiving vessel is required.")
        tracked_receiver = db.scalar(select(Vessel.id).where(or_(
            func.lower(Vessel.name) == receiver.lower(),
            func.lower(Vessel.code) == receiver.lower(),
        )))
        if tracked_receiver is not None:
            raise ValueError("Fuel issues can only be made to an untracked vessel.")
        issue = FuelIssue(vessel_id=vessel_id, shift_id=shift_id,
                          receiving_vessel=receiver, quantity=quantity,
                          notes=notes.strip() if notes else None,
                          status=IssueStatus.PENDING.value, created_by_user_id=user_id)
        db.add(issue)
        db.flush()
        AuditService.log(db=db, user_id=user_id, action="CREATE_FUEL_ISSUE",
                         entity="fuel_issues", entity_id=issue.id,
                         new_values={"vessel_id": vessel_id, "shift_id": shift_id,
                                     "receiving_vessel": receiver, "quantity": str(quantity),
                                     "status": IssueStatus.PENDING.value})
        return issue

    @staticmethod
    def review(db: Session, *, issue_id: int, approved: bool,
               reviewer_id: int, remark: str | None = None,
               reconcile_downstream: bool = False) -> FuelIssue:
        issue = db.scalar(select(FuelIssue).where(FuelIssue.id == issue_id).with_for_update())
        if issue is None:
            raise ValueError("Issue not found.")
        if issue.status != IssueStatus.PENDING.value:
            raise ValueError("Only pending issues can be reviewed.")
        shift_hint = db.get(Shift, issue.shift_id)
        if shift_hint is None or shift_hint.vessel_id != issue.vessel_id:
            raise ValueError("Issue source shift is missing or does not match its vessel.")
        downstream_reconciled = False
        if approved:
            vessel_shifts = FuelService.lock_vessel_shifts(db, issue.vessel_id)
            shift = next((candidate for candidate in vessel_shifts if candidate.id == issue.shift_id), None)
            if shift is None:
                raise ValueError("Issue source shift is missing.")
            if shift.status != "OPEN":
                raise ValueError("The source shift is closed; reopen it before approving this issue.")
            subsequent_shifts = sorted(
                (candidate for candidate in vessel_shifts if FuelService.is_later_shift(candidate, shift)),
                key=FuelService.shift_order_key,
            )
            if subsequent_shifts and not reconcile_downstream:
                raise ValueError(
                    "This event would change fuel available to subsequent shifts; downstream reconciliation is required first."
                )
            balance = FuelService.calculate_shift_balance(db, shift.id)
            quantity = Decimal(str(issue.quantity))
            if quantity > balance["closing_fuel"]:
                raise ValueError("Issue quantity exceeds the source shift's available fuel.")
            existing = db.scalar(select(FuelTransaction).where(
                FuelTransaction.reference_type == "FUEL_ISSUE",
                FuelTransaction.reference_id == issue.id,
                FuelTransaction.transaction_type == FuelTransactionType.ISSUE_OUT.value,
            ))
            if existing is None:
                FuelService.add_transaction(
                    db=db, vessel_id=issue.vessel_id, shift_date=shift.shift_date,
                    shift_name=shift.shift_name or "MORNING",
                    transaction_type=FuelTransactionType.ISSUE_OUT,
                    quantity=quantity, created_by_user_id=reviewer_id,
                    reference_type="FUEL_ISSUE", reference_id=issue.id,
                    remarks=f"Issue to {issue.receiving_vessel}" + (f": {issue.notes}" if issue.notes else ""),
                    allow_downstream_reconciliation=bool(subsequent_shifts),
                )
                downstream_changes = FuelService.reconcile_downstream_shifts(
                    db, shift_id=shift.id, reconciled_by_user_id=reviewer_id,
                    reason=remark or f"Approved fuel issue #{issue.id}",
                ) if subsequent_shifts else []
                downstream_reconciled = bool(downstream_changes)
        old_status = issue.status
        issue.status = IssueStatus.APPROVED.value if approved else IssueStatus.REJECTED.value
        issue.reviewed_by_user_id = reviewer_id
        issue.admin_remark = remark.strip() if remark else None
        issue.reviewed_at = now_ist()
        db.flush()
        AuditService.log(db=db, user_id=reviewer_id,
                         action="APPROVE_FUEL_ISSUE" if approved else "REJECT_FUEL_ISSUE",
                         entity="fuel_issues", entity_id=issue.id,
                         old_values={"status": old_status},
                         new_values={"status": issue.status, "admin_remark": issue.admin_remark,
                                     "ledger_transaction_created": approved,
                                     "downstream_reconciled": downstream_reconciled})
        return issue
