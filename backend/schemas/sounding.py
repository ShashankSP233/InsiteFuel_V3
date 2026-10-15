from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SoundingResponse(BaseModel):
    id: int
    shift_id: int | None
    vessel_id: int
    report_date: date
    attachment_id: int
    submitted_at: datetime
    submitted_by_user_id: int

    model_config = ConfigDict(from_attributes=True)


class AdminSoundingCreate(BaseModel):
    attachment_id: int


class AdminSoundingUpdate(BaseModel):
    attachment_id: int
    reason: str = Field(min_length=1, max_length=1000)


class AdminSoundingDelete(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class SoundingStatusResponse(BaseModel):
    shift_id: int
    vessel_id: int
    report_date: date
    shift_name: str | None
    status: str
    deadline: datetime
    sounding_count: int


class SoundingMissingResponse(BaseModel):
    shift_id: int
    vessel_id: int
    vessel_name: str
    report_date: date
    shift_name: str | None
    status: str
    deadline: datetime
    sounding_count: int


class SoundingComplianceResponse(BaseModel):
    report_date: date
    expected: int
    submitted: int
    late: int
    missing: int
    due: int
    compliance_percentage: float