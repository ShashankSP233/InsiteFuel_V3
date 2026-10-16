from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IotItemResult(BaseModel):
    index: int
    status: str  # PROCESSED | DUPLICATE | REJECTED
    payload_id: int | None = None
    shift_id: int | None = None
    errors: list[str] = []
    warnings: list[str] = []
    result: dict[str, Any] | None = None


class IotIngestResponse(BaseModel):
    received: int
    processed: int
    duplicates: int
    rejected: int
    awaiting_mapping: int = 0
    results: list[IotItemResult]


class IotPayloadSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_vessel_id: str | None
    vessel_id: int | None
    shift_id: int | None
    shift_date: date | None
    shift_name: str | None
    window_start: datetime | None
    window_end: datetime | None
    status: str
    errors: list[str] | None
    warnings: list[str] | None
    result: dict[str, Any] | None
    received_at: datetime
    processed_at: datetime | None


class IotPayloadDetail(IotPayloadSummary):
    raw_payload: Any | None


class VesselIotMapping(BaseModel):
    iot_vessel_id: str | None = Field(default=None, max_length=100)


class EquipmentIotMapping(BaseModel):
    iot_engine_name: str | None = Field(default=None, max_length=50)


class AutoCloseResponse(BaseModel):
    closed: list[int]
    failed: list[dict[str, Any]]
