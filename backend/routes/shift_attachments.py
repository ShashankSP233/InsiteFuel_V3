from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
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