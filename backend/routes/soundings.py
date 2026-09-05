from datetime import date, datetime, timezone

from fastapi.responses import FileResponse
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.schemas.sounding import (
    SoundingResponse,
    SoundingStatusResponse,
    SoundingMissingResponse,
    SoundingComplianceResponse,
)
from backend.services.sounding_service import SoundingService

from backend.models.attachment import Attachment

router = APIRouter(
    prefix="/api/soundings",
    tags=["Soundings"],
)


@router.post(
    "",
    response_model=SoundingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_sounding(
    vessel_id: int,
    report_date: date,
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        sounding = SoundingService.create_sounding(
            db=db,
            vessel_id=vessel_id,
            report_date=report_date,
            attachment_id=attachment_id,
            submitted_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(sounding)

        return sounding

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=list[SoundingResponse],
)
def list_soundings(
    vessel_id: int,
    report_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return SoundingService.list_soundings(
            db=db,
            vessel_id=vessel_id,
            report_date=report_date,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.get(
    "/status",
    response_model=SoundingStatusResponse,
)
def get_sounding_status(
    vessel_id: int,
    report_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        soundings = SoundingService.list_soundings(
            db=db,
            vessel_id=vessel_id,
            report_date=report_date,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    now = datetime.now(timezone.utc)

    deadline = SoundingService.get_deadline(report_date)

    status_value = SoundingService.get_status(
        report_date=report_date,
        soundings=soundings,
        now=now,
    )

    return SoundingStatusResponse(
        vessel_id=vessel_id,
        report_date=report_date,
        status=status_value,
        deadline=deadline,
        sounding_count=len(soundings),
    )

@router.get("/{sounding_id}/image")
def get_sounding_image(
    sounding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sounding = SoundingService.get_sounding(
        db=db,
        sounding_id=sounding_id,
    )

    if sounding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sounding not found.",
        )

    attachment = db.get(Attachment, sounding.attachment_id)

    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sounding attachment not found.",
        )

    return FileResponse(
        path=attachment.storage_path,
        media_type=attachment.content_type,
        filename=attachment.original_filename,
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
    sounding = SoundingService.get_sounding(
        db=db,
        sounding_id=sounding_id,
    )

    if sounding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sounding not found.",
        )

    return sounding