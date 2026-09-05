from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class SoundingResponse(BaseModel):
    id: int
    vessel_id: int
    report_date: date
    attachment_id: int
    submitted_at: datetime
    submitted_by_user_id: int

    model_config = ConfigDict(from_attributes=True)


class SoundingStatusResponse(BaseModel):
    vessel_id: int
    report_date: date
    status: str
    deadline: datetime
    sounding_count: int

class SoundingMissingResponse(BaseModel):
    vessel_id: int
    vessel_name: str
    report_date: date
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