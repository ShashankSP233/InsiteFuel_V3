from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dependencies import (
    db_session,
    get_current_user,
    require_roles,
)
from backend.models.equipment import Equipment
from backend.models.user import User, UserRole
from backend.schemas.equipment import (
    EquipmentCreate,
    EquipmentResponse,
    EquipmentUpdate,
)
from backend.services.equipment_service import (
    create_equipment,
    get_equipment_by_id,
    update_equipment,
)


router = APIRouter(
    prefix="/api/equipment",
    tags=["Equipment"],
)


@router.get(
    "",
    response_model=list[EquipmentResponse],
)
def list_equipment(
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    return db.scalars(
        select(Equipment).order_by(Equipment.id)
    ).all()


@router.get(
    "/{equipment_id}",
    response_model=EquipmentResponse,
)
def get_equipment(
    equipment_id: int,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    equipment = get_equipment_by_id(
        db,
        equipment_id,
    )

    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment not found.",
        )

    return equipment


@router.post(
    "",
    response_model=EquipmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_new_equipment(
    payload: EquipmentCreate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER)
    ),
):
    try:
        equipment = create_equipment(
            db=db,
            vessel_id=payload.vessel_id,
            name=payload.name,
            equipment_type=payload.equipment_type,
            code=payload.code,
        )

        db.commit()
        db.refresh(equipment)

        return equipment

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.patch(
    "/{equipment_id}",
    response_model=EquipmentResponse,
)
def update_existing_equipment(
    equipment_id: int,
    payload: EquipmentUpdate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER)
    ),
):
    equipment = get_equipment_by_id(
        db,
        equipment_id,
    )

    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment not found.",
        )

    try:
        equipment = update_equipment(
            db,
            equipment,
            vessel_id=payload.vessel_id,
            name=payload.name,
            equipment_type=payload.equipment_type,
            code=payload.code,
            is_active=payload.is_active,
        )

        db.commit()
        db.refresh(equipment)

        return equipment

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )