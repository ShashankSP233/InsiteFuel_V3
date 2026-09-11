from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


VesselType = Literal[
    "Dredger",
    "Tug Boat",
    "Survey Boat",
    "House Boat",
    "Wooden Boat",
    "Steel Boat",
    "Fiber Boat",
    "Dredge Pump Boat",
    "Tanker",
]


class VesselCreate(BaseModel):
    project_id: int

    site_id: int

    name: str = Field(
        min_length=1,
        max_length=150,
    )

    code: str = Field(
        min_length=1,
        max_length=50,
    )

    vessel_type: VesselType

    is_active: bool = True

    fuel_threshold_litres: Decimal = Decimal("0")


class VesselUpdate(BaseModel):
    project_id: int | None = None

    site_id: int | None = None

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    code: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )

    vessel_type: VesselType | None = None

    is_active: bool | None = None

    fuel_threshold_litres: Decimal | None = None


class VesselResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    project_id: int
    site_id: int | None
    name: str
    code: str | None
    vessel_type: str | None
    is_active: bool
    fuel_threshold_litres: Decimal