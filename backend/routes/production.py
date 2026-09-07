from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.schemas.production import (
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