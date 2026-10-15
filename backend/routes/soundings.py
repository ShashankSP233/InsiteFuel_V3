from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.attachment import Attachment
from backend.models.sounding import Sounding
from backend.models.user import User, UserRole
from backend.schemas.sounding import (
    AdminSoundingCreate,
    AdminSoundingDelete,
    AdminSoundingUpdate,
    SoundingComplianceResponse,
    SoundingMissingResponse,
    SoundingResponse,
    SoundingStatusResponse,
)
from backend.dependencies import get_current_user, require_roles
from backend.services.sounding_service import SoundingService


router = APIRouter(
    prefix="/api/soundings",
    tags=["Soundings"],
)


@router.post(
    "",
    response_model=SoundingResponse,
)
def create_sounding(
    shift_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        sounding = SoundingService.create_sounding(
            db=db,
            shift_id=shift_id,
            attachment_id=attachment_id,
            submitted_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(sounding)

        return sounding

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


@router.post(
    "/admin/{shift_id}",
    response_model=SoundingResponse,
    status_code=201,
)
def admin_create_sounding(
    shift_id: int,
    data: AdminSoundingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        sounding = SoundingService.create_sounding(
            db=db,
            shift_id=shift_id,
            attachment_id=data.attachment_id,
            submitted_by_user_id=current_user.id,
        )
        db.commit()
        db.refresh(sounding)
        return sounding
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.put(
    "/admin/{shift_id}/{sounding_id}",
    response_model=SoundingResponse,
)
def admin_update_sounding(
    shift_id: int,
    sounding_id: int,
    data: AdminSoundingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        sounding = SoundingService.update_sounding_attachment(
            db=db,
            sounding_id=sounding_id,
            shift_id=shift_id,
            attachment_id=data.attachment_id,
            corrected_by_user_id=current_user.id,
            reason=data.reason,
        )
        db.commit()
        db.refresh(sounding)
        return sounding
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete(
    "/admin/{shift_id}/{sounding_id}",
    response_model=dict,
)
def admin_delete_sounding(
    shift_id: int,
    sounding_id: int,
    data: AdminSoundingDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        SoundingService.delete_sounding(
            db=db,
            sounding_id=sounding_id,
            shift_id=shift_id,
            deleted_by_user_id=current_user.id,
            reason=data.reason,
        )
        db.commit()
        return {"deleted": True, "sounding_id": sounding_id}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "",
    response_model=list[SoundingResponse],
)
def list_soundings(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SoundingService.list_soundings(
        db=db,
        shift_id=shift_id,
    )


@router.get(
    "/status",
    response_model=SoundingStatusResponse,
)
def get_sounding_status(
    shift_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return SoundingService.get_shift_status(
            db=db,
            shift_id=shift_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )


@router.get(
    "/status/all",
    response_model=list[SoundingMissingResponse],
)
def get_all_sounding_statuses(
    report_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SoundingService.get_all_vessel_statuses(
        db=db,
        report_date=report_date,
    )


@router.get(
    "/compliance",
    response_model=SoundingComplianceResponse,
)
def get_sounding_compliance(
    report_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SoundingService.get_compliance(
        db=db,
        report_date=report_date,
    )


@router.get(
    "/{sounding_id}",
    response_model=SoundingResponse,
)
def get_sounding(
    sounding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sounding = db.get(Sounding, sounding_id)

    if sounding is None:
        raise HTTPException(
            status_code=404,
            detail="Sounding not found.",
        )

    return sounding


@router.get(
    "/{sounding_id}/image",
)
def get_sounding_image(
    sounding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sounding = db.get(Sounding, sounding_id)

    if sounding is None:
        raise HTTPException(
            status_code=404,
            detail="Sounding not found.",
        )

    attachment = db.get(
        Attachment,
        sounding.attachment_id,
    )

    if attachment is None:
        raise HTTPException(
            status_code=404,
            detail="Sounding attachment not found.",
        )

    return FileResponse(
        attachment.storage_path,
        media_type=attachment.content_type,
        filename=attachment.original_filename,
    )