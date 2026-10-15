from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict


class EngineEventCreate(BaseModel):
    equipment_id: int
    shift_id: int

    start_time: datetime
    stop_time: datetime

    lph_rate: Decimal = Field(ge=0)
    consumption: Decimal | None = Field(default=None, ge=0)

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


class EngineEventAdminUpdate(BaseModel):
    equipment_id: int
    start_time: datetime
    stop_time: datetime
    lph_rate: Decimal = Field(ge=0)
    consumption: Decimal | None = Field(default=None, gt=0)
    remarks: str | None = Field(default=None, max_length=500)
    reason: str = Field(min_length=1, max_length=1000)


class EngineEventDeleteRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)