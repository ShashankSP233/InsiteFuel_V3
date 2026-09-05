from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.dependencies import require_roles
from backend.models.audit_log import AuditLog
from backend.models.user import User, UserRole
from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    action: str
    entity: str
    entity_id: int | None
    old_values: dict | None
    new_values: dict | None
    reason: str | None
    details: str | None
    created_at: datetime


router = APIRouter(
    prefix="/api/audit",
    tags=["Audit"],
)


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[AuditLogResponse])
def get_audit_logs(
    action: str | None = Query(default=None),
    entity: str | None = Query(default=None),
    entity_id: int | None = Query(default=None),
    user_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    query = select(AuditLog)

    if action:
        query = query.where(AuditLog.action == action)

    if entity:
        query = query.where(AuditLog.entity == entity)

    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)

    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)

    query = (
        query
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    )

    return db.scalars(query).all()
