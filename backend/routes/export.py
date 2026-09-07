from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.services.export_service import ExportService


router = APIRouter(
    prefix="/api/export",
    tags=["Export"],
)


def resolve_dates(
    from_date: date | None,
    to_date: date | None,
):
    if to_date is None:
        to_date = date.today()

    if from_date is None:
        from_date = to_date - timedelta(days=29)

    if from_date > to_date:
        raise ValueError(
            "from_date cannot be later than to_date."
        )

    return from_date, to_date


@router.get("/csv")
def export_csv(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    shift_name: str | None = Query(None),
    vessel_ids: list[int] | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from_date, to_date = resolve_dates(
        from_date,
        to_date,
    )

    rows = ExportService.get_rows(
        db=db,
        from_date=from_date,
        to_date=to_date,
        vessel_ids=vessel_ids,
        shift_name=shift_name,
    )

    file = ExportService.create_csv(rows)

    return StreamingResponse(
        file,
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="fuel_dashboard_'
                f'{from_date}_{to_date}.csv"'
            )
        },
    )


@router.get("/excel")
def export_excel(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    shift_name: str | None = Query(None),
    vessel_ids: list[int] | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from_date, to_date = resolve_dates(
        from_date,
        to_date,
    )

    rows = ExportService.get_rows(
        db=db,
        from_date=from_date,
        to_date=to_date,
        vessel_ids=vessel_ids,
        shift_name=shift_name,
    )

    file = ExportService.create_excel(rows)

    return StreamingResponse(
        file,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                f'attachment; filename="fuel_dashboard_'
                f'{from_date}_{to_date}.xlsx"'
            )
        },
    )


@router.get("/pdf")
def export_pdf(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    shift_name: str | None = Query(None),
    vessel_ids: list[int] | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from_date, to_date = resolve_dates(
        from_date,
        to_date,
    )

    rows = ExportService.get_rows(
        db=db,
        from_date=from_date,
        to_date=to_date,
        vessel_ids=vessel_ids,
        shift_name=shift_name,
    )

    file = ExportService.create_pdf(rows)

    return StreamingResponse(
        file,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="fuel_dashboard_'
                f'{from_date}_{to_date}.pdf"'
            )
        },
    )