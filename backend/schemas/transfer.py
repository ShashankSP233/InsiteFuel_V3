from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from backend.models.transfer import TransferStatus


class TransferCreate(BaseModel):
    from_vessel_id: int
    from_shift_id: int
    to_vessel_id: int
    to_shift_id: int
    initiated_quantity: Decimal = Field(gt=0)
    transfer_date: datetime | None = None
    notes: str | None = Field(None, max_length=1000)


class TransferReceive(BaseModel):
    received_quantity: Decimal = Field(ge=0)
    notes: str | None = Field(None, max_length=1000)


class TransferSubmitReview(BaseModel):
    pass


class TransferReject(BaseModel):
    manager_remark: str = Field(min_length=1, max_length=1000)


class TransferApprove(BaseModel):
    manager_remark: str | None = Field(None, max_length=1000)


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int

    from_vessel_id: int
    from_shift_id: int

    to_vessel_id: int
    to_shift_id: int

    initiated_quantity: Decimal
    received_quantity: Decimal | None
    loss_quantity: Decimal | None

    status: TransferStatus

    transfer_date: datetime

    initiated_by_user_id: int
    received_by_user_id: int | None
    reviewed_by_user_id: int | None
    approved_by_user_id: int | None

    initiated_at: datetime
    received_at: datetime | None
    reviewed_at: datetime | None
    approved_at: datetime | None

    manager_remark: str | None
    notes: str | None

    created_at: datetime

class TransferCorrection(BaseModel):
    initiated_quantity: Decimal | None = Field(
        default=None,
        gt=0,
    )

    received_quantity: Decimal | None = Field(
        default=None,
        ge=0,
    )

    manager_remark: str | None = Field(
        default=None,
        max_length=1000,
    )

    notes: str | None = Field(
        default=None,
        max_length=1000,
    )

    