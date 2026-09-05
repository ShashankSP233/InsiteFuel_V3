from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from backend.database import SessionLocal
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.schemas.engine import (
    EngineEventCreate,
    EngineEventResponse,
)
from backend.services.engine_service import EngineService


router = APIRouter(
    prefix="/api/engine",
    tags=["Engine"],
)


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post(
    "/event",
    response_model=EngineEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_engine_event(
    data: EngineEventCreate,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        event = EngineService.create_engine_event(
            db=db,
            equipment_id=data.equipment_id,
            shift_id=data.shift_id,
            start_time=data.start_time,
            stop_time=data.stop_time,
            lph_rate=data.lph_rate,
            created_by_user_id=current_user.id,
            remarks=data.remarks,
        )

        db.commit()
        db.refresh(event)

        return event

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

@router.get(
    "/events",
    response_model=list[EngineEventResponse],
)
def get_engine_events(
    shift_id: int | None = None,
    equipment_id: int | None = None,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    return EngineService.get_engine_events(
        db=db,
        shift_id=shift_id,
        equipment_id=equipment_id,
    )

@router.get(
    "/event/{event_id}",
    response_model=EngineEventResponse,
)
def get_engine_event(
    event_id: int,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        return EngineService.get_engine_event(
            db=db,
            event_id=event_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )