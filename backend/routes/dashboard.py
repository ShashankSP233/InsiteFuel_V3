from datetime import date, timedelta
from decimal import Decimal
import math
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.schemas.dashboard import (
    FuelDashboardResponse,
    FuelDashboardRow,
    FuelDashboardSummary,
    VesselFuelBalance,
    ConsumptionTrendPoint,
    FuelEfficiencyResponse,
    MissingSoundingItem,
    SoundingComplianceResponse,
    DashboardAlert,
    DashboardComparisonResponse,
    ManagementSummaryResponse,
    DashboardChartsResponse,
    EfficiencyReportResponse,
)
from backend.services.sounding_service import SoundingService
from backend.services.dashboard_service import DashboardService


router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"],
)


@router.get("/fuel", response_model=FuelDashboardResponse)
def get_fuel_dashboard(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    vessel_id: int | None = Query(None),
    shift_name: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if to_date is None:
        to_date = date.today()

    if from_date is None:
        from_date = to_date - timedelta(days=29)

    rows = DashboardService.get_fuel_dashboard(
        db=db,
        from_date=from_date,
        to_date=to_date,
        vessel_id=vessel_id,
        shift_name=shift_name,
    )
    total_records = len(rows)

    total_pages = (
        math.ceil(total_records / page_size)
        if total_records > 0
        else 0
    )

    start_index = (page - 1) * page_size
    end_index = start_index + page_size

    paginated_rows = rows[start_index:end_index]


    total_received = sum(
        (row["received_fuel"] for row in rows),
        Decimal("0"),
    )

    total_consumption = sum(
        (row["total_engine_consumption"] for row in rows),
        Decimal("0"),
    )

    total_transfer_out = sum(
        (row["transfer_out"] for row in rows),
        Decimal("0"),
    )

    total_advancement_m = sum(
        (
            Decimal(str(row["advancement_m"]))
            if row["advancement_m"] is not None
            else Decimal("0")
            for row in rows
        ),
        Decimal("0"),
    )

    total_dredging_hours = sum(
        (
            Decimal(str(row["dredging_hours"]))
            if row["dredging_hours"] is not None
            else Decimal("0")
            for row in rows
        ),
        Decimal("0"),
    )

    negative_balance_count = sum(
        1 for row in rows
        if "NEGATIVE_BALANCE" in row["flags"]
    )

    low_fuel_count = sum(
        1 for row in rows
        if "LOW_FUEL" in row["flags"]
    )

    # Latest closing balance per vessel.
    # Do not sum every shift's closing balance.
    vessel_ids = list({row["vessel_id"] for row in rows})

    latest_closing = DashboardService.get_latest_closing_by_vessel(
        db=db,
        vessel_ids=vessel_ids,
    )

    total_fuel = sum(
        latest_closing.values(),
        Decimal("0"),
    )

    submitted_count = sum(
        1 for row in rows
        if row["status"] != "OPEN"
    )

    return FuelDashboardResponse(
        rows=paginated_rows,
        total_fuel=total_fuel,
        total_received=total_received,
        total_consumption=total_consumption,
        total_transfer_out=total_transfer_out,
        total_advancement_m=total_advancement_m,
        total_dredging_hours=total_dredging_hours,
        record_count=len(paginated_rows),
        submitted_count=submitted_count,
        negative_balance_count=negative_balance_count,
        low_fuel_count=low_fuel_count,
        page=page,
        page_size=page_size,
        total_records=total_records,
        total_pages=total_pages,
    )


@router.get("/summary", response_model=FuelDashboardSummary)
def get_dashboard_summary(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if to_date is None:
        to_date = date.today()

    if from_date is None:
        from_date = to_date - timedelta(days=29)

    rows = DashboardService.get_fuel_dashboard(
        db=db,
        from_date=from_date,
        to_date=to_date,
    )

    total_received = sum(
        (row["received_fuel"] for row in rows),
        Decimal("0"),
    )

    total_consumption = sum(
        (row["total_engine_consumption"] for row in rows),
        Decimal("0"),
    )

    total_transfer_out = sum(
        (row["transfer_out"] for row in rows),
        Decimal("0"),
    )

    negative_balance_count = len({
        row["vessel_id"]
        for row in rows
        if "NEGATIVE_BALANCE" in row["flags"]
    })

    low_fuel_count = len({
        row["vessel_id"]
        for row in rows
        if "LOW_FUEL" in row["flags"]
    })

    vessel_ids = list({
        row["vessel_id"]
        for row in rows
    })

    latest_closing = DashboardService.get_latest_closing_by_vessel(
        db=db,
        vessel_ids=vessel_ids,
    )

    total_fuel = sum(
        latest_closing.values(),
        Decimal("0"),
    )

    return FuelDashboardSummary(
        from_date=from_date,
        to_date=to_date,
        total_fuel=total_fuel,
        total_received=total_received,
        total_consumption=total_consumption,
        total_transfer_out=total_transfer_out,
        active_vessel_count=len(vessel_ids),
        negative_balance_count=negative_balance_count,
        low_fuel_count=low_fuel_count,
    )

@router.get(
    "/vessel-balances",
    response_model=list[VesselFuelBalance],
)
def get_vessel_balances(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    vessel_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if to_date is None:
        to_date = date.today()

    if from_date is None:
        from_date = to_date - timedelta(days=6)

    return DashboardService.get_vessel_balances(
        db=db,
        from_date=from_date,
        to_date=to_date,
        vessel_id=vessel_id,
    )



@router.get(
    "/consumption-trend",
    response_model=list[ConsumptionTrendPoint],
)
def get_consumption_trend(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    vessel_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if to_date is None:
        to_date = date.today()

    if from_date is None:
        from_date = to_date - timedelta(days=29)

    return DashboardService.get_consumption_trend(
        db=db,
        from_date=from_date,
        to_date=to_date,
        vessel_id=vessel_id,
    )


@router.get(
    "/efficiency",
    response_model=FuelEfficiencyResponse,
)
def get_fuel_efficiency(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    vessel_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if to_date is None:
        to_date = date.today()

    if from_date is None:
        from_date = to_date - timedelta(days=29)

    return DashboardService.get_fuel_efficiency(
        db=db,
        from_date=from_date,
        to_date=to_date,
        vessel_id=vessel_id,
    )


@router.get(
    "/missing-soundings",
    response_model=list[MissingSoundingItem],
)
def get_missing_soundings(
    report_date: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if report_date is None:
        report_date = date.today()

    statuses = SoundingService.get_all_vessel_statuses(
        db=db,
        report_date=report_date,
    )

    return [
        item
        for item in statuses
        if item["status"] in {"MISSING", "DUE", "LATE"}
    ]

@router.get(
    "/sounding-compliance",
    response_model=SoundingComplianceResponse,
)
def get_sounding_compliance(
    report_date: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if report_date is None:
        report_date = date.today()

    return SoundingService.get_compliance(
        db=db,
        report_date=report_date,
    )


@router.get(
    "/alerts",
    response_model=list[DashboardAlert],
)
def get_dashboard_alerts(
    report_date: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if report_date is None:
        report_date = date.today()

    statuses = SoundingService.get_all_vessel_statuses(
        db=db,
        report_date=report_date,
    )

    return [
        {
            "alert_type": item["status"],
            "vessel_id": item["vessel_id"],
            "vessel_name": item["vessel_name"],
            "report_date": item["report_date"],
            "deadline": item["deadline"],
            "sounding_count": item["sounding_count"],
        }
        for item in statuses
        if item["status"] in {"MISSING", "LATE", "DUE"}
    ]

@router.get(
    "/comparison",
    response_model=DashboardComparisonResponse,
)
def get_dashboard_comparison(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    vessel_ids: list[int] | None = Query(None),
    shift_name: str | None = Query(None),
    project_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if to_date is None:
        to_date = date.today()

    if from_date is None:
        from_date = to_date - timedelta(days=29)

    rows = DashboardService.get_dashboard_comparison(
        db=db,
        from_date=from_date,
        to_date=to_date,
        vessel_ids=vessel_ids,
        shift_name=shift_name,
        project_id=project_id,
    )

    return DashboardComparisonResponse(
        rows=rows,
    )




@router.get(
    "/management-summary",
    response_model=ManagementSummaryResponse,
)
def get_management_summary(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    vessel_ids: list[int] | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if to_date is None:
        to_date = date.today()

    if from_date is None:
        from_date = to_date - timedelta(days=29)

    return DashboardService.get_management_summary(
        db=db,
        from_date=from_date,
        to_date=to_date,
        vessel_ids=vessel_ids,
    )


@router.get(
    "/charts",
    response_model=DashboardChartsResponse,
)
def get_dashboard_charts(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    vessel_ids: list[int] | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if to_date is None:
        to_date = date.today()

    if from_date is None:
        from_date = to_date - timedelta(days=29)

    return DashboardService.get_dashboard_charts(
        db=db,
        from_date=from_date,
        to_date=to_date,
        vessel_ids=vessel_ids,
    )






@router.get(
    "/efficiency-report",
    response_model=EfficiencyReportResponse,
)
def get_efficiency_report(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if to_date is None:
        to_date = date.today()

    if from_date is None:
        from_date = to_date - timedelta(days=29)

    rows = DashboardService.get_efficiency_report(
        db=db,
        from_date=from_date,
        to_date=to_date,
    )

    return EfficiencyReportResponse(
        from_date=from_date,
        to_date=to_date,
        rows=rows,
    )


