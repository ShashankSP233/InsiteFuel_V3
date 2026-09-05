from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class InitialOpeningFuelCreate(BaseModel):
    vessel_id: int
    shift_date: date
    opening_fuel: Decimal = Field(ge=0)


class OpeningFuelCorrection(BaseModel):
    opening_fuel: Decimal = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)


class FuelTransactionCreate(BaseModel):
    vessel_id: int
    shift_date: date
    shift_name: str
    transaction_type: str
    quantity: Decimal = Field(gt=0)
    adjustment_direction: str | None = None
    reference_type: str | None = None
    reference_id: int | None = None
    remarks: str | None = Field(default=None, max_length=500)
    source_vessel_id: int | None = None
    fuel_source: str | None = Field(default=None, max_length=200)


class FuelTransactionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    shift_id: int
    vessel_id: int
    transaction_type: str
    quantity: Decimal
    adjustment_direction: str | None
    reference_type: str | None
    reference_id: int | None
    transaction_date: datetime
    remarks: str | None
    created_by_user_id: int
    created_at: datetime
    source_vessel_id: int | None
    fuel_source: str | None


class ShiftResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    vessel_id: int
    shift_date: date
    shift_name: str
    opening_fuel: Decimal
    calculated_closing_fuel: Decimal | None
    status: str
    created_at: datetime
    closed_at: datetime | None


class ShiftBalanceResponse(BaseModel):
    shift_id: int
    vessel_id: int
    shift_date: date
    shift_name: str

    opening_fuel: Decimal
    received_fuel: Decimal
    transfer_in: Decimal
    engine_consumption: Decimal
    transfer_out: Decimal
    adjustment_in: Decimal
    adjustment_out: Decimal
    closing_fuel: Decimal

class ShiftCloseResponse(BaseModel):
    id: int
    vessel_id: int
    shift_date: date
    shift_name: str
    opening_fuel: Decimal
    calculated_closing_fuel: Decimal
    status: str
    closed_at: datetime | None

    model_config = {"from_attributes": True}

class ShiftOpenRequest(BaseModel):
    vessel_id: int
    shift_date: date
    shift_name: str

class ShiftReportResponse(BaseModel):
    shift: ShiftResponse
    balance: ShiftBalanceResponse
    transactions: list[FuelTransactionResponse]