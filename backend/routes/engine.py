from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from backend.dependencies import db_session, get_current_user, require_roles
from backend.models.user import User, UserRole
from backend.schemas.engine import (
    EngineEventCreate,
    EngineEventAdminUpdate,
    EngineEventDeleteRequest,
    EngineEventResponse,
)
from backend.services.engine_service import EngineService


router = APIRouter(
    prefix="/api/engine",
    tags=["Engine"],
)


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
            consumption=data.consumption,
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


@router.post(
    "/shift/{shift_id}/events",
    response_model=EngineEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_engine_event(
    shift_id: int,
    data: EngineEventCreate,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    if data.shift_id != shift_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request shift_id does not match the selected shift.",
        )
    try:
        event = EngineService.create_engine_event(
            db=db,
            equipment_id=data.equipment_id,
            shift_id=shift_id,
            start_time=data.start_time,
            stop_time=data.stop_time,
            lph_rate=data.lph_rate,
            created_by_user_id=current_user.id,
            consumption=data.consumption,
            remarks=data.remarks,
            reconcile_downstream=data.reconcile_downstream,
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


@router.put(
    "/shift/{shift_id}/events/{event_id}",
    response_model=EngineEventResponse,
)
def admin_update_engine_event(
    shift_id: int,
    event_id: int,
    data: EngineEventAdminUpdate,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        event = EngineService.update_engine_event(
            db=db,
            event_id=event_id,
            shift_id=shift_id,
            equipment_id=data.equipment_id,
            start_time=data.start_time,
            stop_time=data.stop_time,
            lph_rate=data.lph_rate,
            consumption=data.consumption,
            remarks=data.remarks,
            corrected_by_user_id=current_user.id,
            reason=data.reason,
            reconcile_downstream=data.reconcile_downstream,
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


@router.delete(
    "/shift/{shift_id}/events/{event_id}",
    response_model=dict,
)
def admin_delete_engine_event(
    shift_id: int,
    event_id: int,
    data: EngineEventDeleteRequest,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        EngineService.delete_engine_event(
            db=db,
            event_id=event_id,
            shift_id=shift_id,
            deleted_by_user_id=current_user.id,
            reason=data.reason,
            reconcile_downstream=data.reconcile_downstream,
        )
        db.commit()
        return {"deleted": True, "event_id": event_id}
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
