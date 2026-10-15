from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, require_roles
from backend.models.user import User, UserRole
from backend.schemas.production import (
    AdminProductionDelete,
    AdminProductionUpdate,
    ProductionCalculatedResponse,
    ProductionCreate,
    ProductionResponse,
)
from backend.services.production_service import (
    ProductionService,
)


router = APIRouter(
    prefix="/api/production",
    tags=["Production"],
)


@router.post(
    "",
    response_model=ProductionCalculatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_production(
    data: ProductionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        production = ProductionService.create_production(
            db=db,
            project_id=data.project_id,
            vessel_id=data.vessel_id,
            shift_id=data.shift_id,
            production_date=data.production_date,
            as_per_qty=data.as_per_qty,
            true_qty=data.true_qty,
            fuel_rate=data.fuel_rate,
            created_by_user_id=current_user.id,
            remarks=data.remarks,
        )

        metrics = ProductionService.calculate_metrics(
            production,
        )

        db.commit()
        db.refresh(production)

        return {
            **ProductionResponse.model_validate(
                production
            ).model_dump(),
            **metrics,
        }

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=list[ProductionResponse],
)
def list_production(
    production_date: date | None = None,
    vessel_id: int | None = None,
    project_id: int | None = None,
    shift_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ProductionService.list_production(
        db=db,
        production_date=production_date,
        vessel_id=vessel_id,
        project_id=project_id,
        shift_id=shift_id,
    )


@router.get(
    "/{production_id}",
    response_model=ProductionCalculatedResponse,
)
def get_production(
    production_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    production = ProductionService.get_production(
        db=db,
        production_id=production_id,
    )

    if production is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Production record not found.",
        )

    metrics = ProductionService.calculate_metrics(
        production,
    )

    return {
        **ProductionResponse.model_validate(
            production
        ).model_dump(),
        **metrics,
    }


@router.post(
    "/admin",
    response_model=ProductionCalculatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_production(
    data: ProductionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        if ProductionService.list_production(
            db=db,
            shift_id=data.shift_id,
        ):
            raise ValueError("A production record already exists for this shift.")
        production = ProductionService.create_production(
            db=db,
            project_id=data.project_id,
            vessel_id=data.vessel_id,
            shift_id=data.shift_id,
            production_date=data.production_date,
            as_per_qty=data.as_per_qty,
            true_qty=data.true_qty,
            fuel_rate=data.fuel_rate,
            created_by_user_id=current_user.id,
            remarks=data.remarks,
        )
        metrics = ProductionService.calculate_metrics(production)
        db.commit()
        db.refresh(production)
        return {
            **ProductionResponse.model_validate(production).model_dump(),
            **metrics,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.put(
    "/admin/{production_id}",
    response_model=ProductionCalculatedResponse,
)
def admin_update_production(
    production_id: int,
    data: AdminProductionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        production = ProductionService.update_production(
            db=db,
            production_id=production_id,
            as_per_qty=data.as_per_qty,
            true_qty=data.true_qty,
            fuel_rate=data.fuel_rate,
            remarks=data.remarks,
            corrected_by_user_id=current_user.id,
            reason=data.reason,
        )
        metrics = ProductionService.calculate_metrics(production)
        db.commit()
        db.refresh(production)
        return {
            **ProductionResponse.model_validate(production).model_dump(),
            **metrics,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.delete(
    "/admin/{production_id}",
    response_model=dict,
)
def admin_delete_production(
    production_id: int,
    data: AdminProductionDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        ProductionService.delete_production(
            db=db,
            production_id=production_id,
            deleted_by_user_id=current_user.id,
            reason=data.reason,
        )
        db.commit()
        return {"deleted": True, "production_id": production_id}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )