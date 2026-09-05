from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dependencies import (
    db_session,
    get_current_user,
    require_roles,
)
from backend.models.user import User, UserRole
from backend.models.vessel import Vessel
from backend.schemas.vessel import (
    VesselCreate,
    VesselResponse,
    VesselUpdate,
)
from backend.services.vessel_service import (
    create_vessel,
    get_vessel_by_id,
    update_fuel_threshold,
    update_vessel,
)


router = APIRouter(
    prefix="/api/vessels",
    tags=["Vessels"],
)


@router.get(
    "",
    response_model=list[VesselResponse],
)
def list_vessels(
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    return db.scalars(
        select(Vessel).order_by(Vessel.id)
    ).all()


@router.get(
    "/{vessel_id}",
    response_model=VesselResponse,
)
def get_vessel(
    vessel_id: int,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    vessel = get_vessel_by_id(
        db,
        vessel_id,
    )

    if vessel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vessel not found.",
        )

    return vessel


@router.post(
    "",
    response_model=VesselResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_new_vessel(
    payload: VesselCreate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER)
    ),
):
    try:
        vessel = create_vessel(
            db=db,
            project_id=payload.project_id,
            name=payload.name,
            code=payload.code,
            fuel_threshold_litres=payload.fuel_threshold_litres,
            created_by_user_id=current_user.id
        )

        db.commit()
        db.refresh(vessel)

        return vessel

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.patch(
    "/{vessel_id}",
    response_model=VesselResponse,
)
def update_existing_vessel(
    vessel_id: int,
    payload: VesselUpdate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER)
    ),
):
    vessel = get_vessel_by_id(
        db,
        vessel_id,
    )

    if vessel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vessel not found.",
        )

    try:
        vessel = update_vessel(
            db,
            vessel,
            project_id=payload.project_id,
            name=payload.name,
            code=payload.code,
            is_active=payload.is_active,
            fuel_threshold_litres=payload.fuel_threshold_litres,
            updated_by_user_id=current_user.id
        )

        db.commit()
        db.refresh(vessel)

        return vessel

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

@router.put(
    "/{vessel_id}/threshold",
    response_model=VesselResponse,
)
def update_vessel_threshold(
    vessel_id: int,
    payload: VesselUpdate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER)
    ),
):
    vessel = get_vessel_by_id(
        db,
        vessel_id,
    )

    if vessel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vessel not found.",
        )

    if payload.fuel_threshold_litres is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fuel_threshold_litres is required.",
        )

    try:
        vessel = update_fuel_threshold(
            db,
            vessel,
            payload.fuel_threshold_litres,
            updated_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(vessel)

        return vessel

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )