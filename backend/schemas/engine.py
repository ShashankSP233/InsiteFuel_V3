from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict


class EngineEventCreate(BaseModel):
    equipment_id: int
    shift_id: int

    start_time: datetime
    stop_time: datetime

    lph_rate: Decimal = Field(ge=0)

    remarks: str | None = Field(
        default=None,
        max_length=500,
    )


class EngineEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shift_id: int
    equipment_id: int
    engine_type: str

    start_time: datetime
    stop_time: datetime

    hours_run: Decimal
    consumption: Decimal
    lph_rate: Decimal

    active: bool
    remarks: str | None

    created_by_user_id: int
    created_at: datetime