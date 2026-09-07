from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductionCreate(BaseModel):
    project_id: int
    vessel_id: int
    shift_id: int
    production_date: date

    as_per_qty: Decimal = Field(
        ge=0,
    )

    true_qty: Decimal = Field(
        ge=0,
    )

    fuel_rate: Decimal | None = Field(
        default=None,
        ge=0,
    )

    remarks: str | None = Field(
        default=None,
        max_length=500,
    )


class ProductionResponse(BaseModel):
    id: int

    project_id: int
    vessel_id: int
    shift_id: int
    production_date: date

    as_per_qty: Decimal
    true_qty: Decimal
    fuel_rate: Decimal | None

    remarks: str | None

    created_by_user_id: int
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class ProductionCalculatedResponse(ProductionResponse):
    quantity_variance: Decimal
    achievement_percentage: Decimal | None