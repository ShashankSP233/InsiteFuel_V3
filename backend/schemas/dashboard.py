from datetime import date, datetime, timezone
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class FuelDashboardRow(BaseModel):
    shift_id: int
    vessel_id: int
    vessel_name: str
    project_id: int | None = None

    shift_date: date
    shift_name: str | None
    status: str

    opening_fuel: Decimal
    received_fuel: Decimal
    transfer_in: Decimal

    me_consumption: Decimal
    me_hours: Decimal

    aux_consumption: Decimal
    aux_hours: Decimal

    dg_consumption: Decimal
    dg_hours: Decimal

    total_engine_consumption: Decimal
    transfer_out: Decimal

    adjustment_in: Decimal
    adjustment_out: Decimal

    closing_fuel: Decimal
    fuel_threshold_litres: Decimal

    flags: list[str]

    model_config = ConfigDict(from_attributes=True)


class FuelDashboardResponse(BaseModel):
    rows: list[FuelDashboardRow]

    total_fuel: Decimal
    total_received: Decimal
    total_consumption: Decimal
    total_transfer_out: Decimal

    record_count: int
    submitted_count: int

    negative_balance_count: int
    low_fuel_count: int

    page: int
    page_size: int
    total_records: int
    total_pages: int

class FuelDashboardSummary(BaseModel):
    from_date: date
    to_date: date

    total_fuel: Decimal
    total_received: Decimal
    total_consumption: Decimal
    total_transfer_out: Decimal

    active_vessel_count: int
    negative_balance_count: int
    low_fuel_count: int

class VesselFuelBalance(BaseModel):
    vessel_id: int
    vessel_name: str
    project_id: int | None = None

    current_fuel: Decimal
    fuel_threshold_litres: Decimal

    recent_consumption: Decimal
    average_daily_consumption: Decimal
    estimated_days_remaining: Decimal | None = None

    flags: list[str]  

class ConsumptionTrendPoint(BaseModel):
    date: date
    consumption: Decimal

class FuelEfficiencyResponse(BaseModel):
    total_consumption: Decimal
    total_production: Decimal
    consumption_per_unit: Decimal | None = None

class MissingSoundingItem(BaseModel):
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

class DashboardAlert(BaseModel):
    alert_type: str
    vessel_id: int
    vessel_name: str
    report_date: date
    deadline: datetime
    sounding_count: int

class DashboardComparisonRow(BaseModel):
    project_id: int | None = None
    project_name: str | None = None

    vessel_id: int
    vessel_name: str

    shift_name: str | None

    record_count: int

    me_litres: Decimal
    aux_litres: Decimal
    dg_litres: Decimal
    total_litres: Decimal

    me_lph: Decimal | None = None
    aux_lph: Decimal | None = None
    dg_lph: Decimal | None = None

    transfer_out: Decimal


class DashboardComparisonResponse(BaseModel):
    rows: list[DashboardComparisonRow]


class ManagementVesselSummary(BaseModel):
    project_id: int
    project_name: str

    vessel_id: int
    vessel_name: str

    current_fuel: Decimal
    fuel_threshold_litres: Decimal
    low_fuel: bool
    negative_balance: bool

    me_consumption: Decimal
    aux_consumption: Decimal
    dg_consumption: Decimal
    total_consumption: Decimal

    me_hours: Decimal
    aux_hours: Decimal
    dg_hours: Decimal
    total_hours: Decimal

    me_lph: Decimal | None = None
    aux_lph: Decimal | None = None
    dg_lph: Decimal | None = None


class ManagementProjectSummary(BaseModel):
    project_id: int
    project_name: str

    vessel_count: int

    current_fuel: Decimal
    total_consumption: Decimal

    me_consumption: Decimal
    aux_consumption: Decimal
    dg_consumption: Decimal

    me_hours: Decimal
    aux_hours: Decimal
    dg_hours: Decimal

    transfer_out: Decimal


class ManagementSummaryResponse(BaseModel):
    from_date: date
    to_date: date

    project_totals: list[ManagementProjectSummary]
    vessel_totals: list[ManagementVesselSummary]

    total_fuel: Decimal
    total_consumption: Decimal
    total_transfer_out: Decimal

    me_consumption: Decimal
    aux_consumption: Decimal
    dg_consumption: Decimal

    me_hours: Decimal
    aux_hours: Decimal
    dg_hours: Decimal
    total_hours: Decimal

    me_lph: Decimal | None = None
    aux_lph: Decimal | None = None
    dg_lph: Decimal | None = None

    sounding_expected: int
    sounding_submitted: int
    sounding_late: int
    sounding_missing: int
    sounding_due: int
    sounding_compliance_percentage: float


class DailyFuelConsumptionPoint(BaseModel):
    date: date
    consumption: Decimal


class EngineConsumptionPoint(BaseModel):
    date: date
    me_litres: Decimal
    aux_litres: Decimal
    dg_litres: Decimal
    total_litres: Decimal


class EngineLphPoint(BaseModel):
    date: date
    me_lph: Decimal | None = None
    aux_lph: Decimal | None = None
    dg_lph: Decimal | None = None


class ClosingBalancePoint(BaseModel):
    date: date
    vessel_id: int
    vessel_name: str
    closing_fuel: Decimal


class EngineSplit(BaseModel):
    me_litres: Decimal
    aux_litres: Decimal
    dg_litres: Decimal
    total_litres: Decimal


class MultiVesselComparisonPoint(BaseModel):
    vessel_id: int
    vessel_name: str
    consumption: Decimal


class DashboardChartsResponse(BaseModel):
    daily_fuel_consumption: list[DailyFuelConsumptionPoint]
    engine_consumption: list[EngineConsumptionPoint]
    engine_lph: list[EngineLphPoint]
    closing_balance: list[ClosingBalancePoint]
    engine_split: EngineSplit
    vessel_comparison: list[MultiVesselComparisonPoint]


class EfficiencyReportRow(BaseModel):
    project_id: int
    project_name: str

    vessel_id: int
    vessel_name: str

    days: int

    me_litres: Decimal
    me_hours: Decimal
    me_lph: Decimal | None = None

    aux_litres: Decimal
    aux_hours: Decimal
    aux_lph: Decimal | None = None

    dg_litres: Decimal
    dg_hours: Decimal
    dg_lph: Decimal | None = None

    total_litres: Decimal
    total_hours: Decimal


class EfficiencyReportResponse(BaseModel):
    from_date: date
    to_date: date
    rows: list[EfficiencyReportRow]