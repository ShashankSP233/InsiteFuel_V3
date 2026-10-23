from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, require_roles
from backend.models.issue import FuelIssue
from backend.models.user import User, UserRole
from backend.schemas.issue import FuelIssueCreate, FuelIssueResponse, FuelIssueReview
from backend.services.issue_service import IssueService

router = APIRouter(prefix="/api/issues", tags=["Fuel issues"])


@router.post("", response_model=FuelIssueResponse, status_code=status.HTTP_201_CREATED)
def create_issue(data: FuelIssueCreate, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    try:
        issue = IssueService.create(db, vessel_id=data.vessel_id, shift_id=data.shift_id,
                                    receiving_vessel=data.receiving_vessel,
                                    quantity=data.quantity, notes=data.notes,
                                    user_id=current_user.id)
        db.commit()
        db.refresh(issue)
        return issue
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[FuelIssueResponse])
def list_issues(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.scalars(select(FuelIssue).order_by(FuelIssue.created_at.desc(), FuelIssue.id.desc())).all()


@router.post("/{issue_id}/approve", response_model=FuelIssueResponse)
def approve_issue(issue_id: int, data: FuelIssueReview, db: Session = Depends(get_db),
                  current_user: User = Depends(require_roles(UserRole.ADMIN))):
    try:
        issue = IssueService.review(db, issue_id=issue_id, approved=True,
                                    reviewer_id=current_user.id, remark=data.admin_remark,
                                    reconcile_downstream=data.reconcile_downstream)
        db.commit()
        db.refresh(issue)
        return issue
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{issue_id}/reject", response_model=FuelIssueResponse)
def reject_issue(issue_id: int, data: FuelIssueReview, db: Session = Depends(get_db),
                 current_user: User = Depends(require_roles(UserRole.ADMIN))):
    try:
        issue = IssueService.review(db, issue_id=issue_id, approved=False,
                                    reviewer_id=current_user.id, remark=data.admin_remark)
        db.commit()
        db.refresh(issue)
        return issue
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
