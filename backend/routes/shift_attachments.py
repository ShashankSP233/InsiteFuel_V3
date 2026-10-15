from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, require_roles
from backend.models.user import User, UserRole
from backend.services.shift_attachment_service import ShiftAttachmentService


router = APIRouter(
    prefix="/api/shifts",
    tags=["Shift Attachments"],
)


class ShiftAttachmentCreate(BaseModel):
    attachment_id: int
    attachment_type: Literal[
        "BILL",
        "TRANSFER_NOTE",
        "SOUNDING",
    ]


class ShiftAttachmentDelete(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


@router.post(
    "/{shift_id}/attachments",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
def attach_to_shift(
    shift_id: int,
    payload: ShiftAttachmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        link = ShiftAttachmentService.attach(
            db=db,
            shift_id=shift_id,
            attachment_id=payload.attachment_id,
            attachment_type=payload.attachment_type,
            created_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(link)

        return {
            "id": link.id,
            "shift_id": link.shift_id,
            "attachment_id": link.attachment_id,
            "attachment_type": link.attachment_type,
            "created_by_user_id": link.created_by_user_id,
            "created_at": link.created_at,
        }

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/{shift_id}/attachments",
    response_model=list[dict],
)
def get_shift_attachments(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ShiftAttachmentService.list_for_shift(
        db=db,
        shift_id=shift_id,
    )


@router.delete(
    "/{shift_id}/attachments/{link_id}",
    response_model=dict,
)
def remove_shift_attachment(
    shift_id: int,
    link_id: int,
    payload: ShiftAttachmentDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        ShiftAttachmentService.remove_link(
            db=db,
            shift_id=shift_id,
            link_id=link_id,
            removed_by_user_id=current_user.id,
            reason=payload.reason,
        )
        db.commit()
        return {"removed": True, "link_id": link_id}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )