from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class FuelIssueCreate(BaseModel):
    vessel_id: int
    shift_id: int
    receiving_vessel: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    notes: str | None = Field(default=None, max_length=1000)


class FuelIssueReview(BaseModel):
    admin_remark: str | None = Field(default=None, max_length=1000)
    reconcile_downstream: bool = False


class FuelIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vessel_id: int
    shift_id: int
    receiving_vessel: str
    quantity: Decimal
    notes: str | None
    status: str
    created_by_user_id: int
    reviewed_by_user_id: int | None
    admin_remark: str | None
    created_at: datetime
    reviewed_at: datetime | None
