from datetime import date
from backend.models.shift import Shift

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dependencies import db_session, get_current_user, require_roles
from backend.models.fuel import AdjustmentDirection, FuelTransaction
from backend.models.user import User, UserRole
from backend.schemas.fuel import (
    FuelTransactionCreate,
    FuelTransactionResponse,
    AdminAdjustmentCorrection,
    AdminReceiptCorrection,
    AdminShiftCloseRequest,
    AdminShiftProductionDataUpdate,
    InitialOpeningFuelCreate,
    OpeningFuelCorrection,
    ShiftBalanceResponse,
    ShiftCloseResponse,
    ShiftOpenRequest,
    ShiftProductionDataUpdate,
    ShiftReopenRequest,
    ShiftReportResponse,
    ShiftResponse,
)
from backend.services.fuel_service import FuelService


router = APIRouter(
    prefix="/api/fuel",
    tags=["Fuel"],
)


@router.get(
    "/shift",
    response_model=ShiftResponse,
)
def get_shift(
    vessel_id: int,
    shift_date: date,
    shift_name: str,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    shift = FuelService.get_shift(
        db=db,
        vessel_id=vessel_id,
        shift_date=shift_date,
        shift_name=shift_name,
    )

    if shift is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shift not found.",
        )

    return shift


@router.get(
    "/admin/shifts",
    response_model=list[ShiftResponse],
)
def list_admin_shifts(
    from_date: date | None = None,
    to_date: date | None = None,
    vessel_id: int | None = None,
    shift_name: str | None = None,
    shift_status: str | None = None,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="From date cannot be after to date.",
        )

    if shift_status and shift_status.upper() not in {"OPEN", "CLOSED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Shift status must be OPEN or CLOSED.",
        )

    statement = select(Shift)
    if from_date:
        statement = statement.where(Shift.shift_date >= from_date)
    if to_date:
        statement = statement.where(Shift.shift_date <= to_date)
    if vessel_id is not None:
        statement = statement.where(Shift.vessel_id == vessel_id)
    if shift_name:
        normalized_name = shift_name.upper()
        if normalized_name not in {"MORNING", "EVENING"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Shift name must be MORNING or EVENING.",
            )
        statement = statement.where(Shift.shift_name == normalized_name)
    if shift_status:
        statement = statement.where(Shift.status == shift_status.upper())

    statement = statement.order_by(Shift.shift_date.desc(), Shift.id.desc())
    return db.scalars(statement).all()


@router.post(
    "/shift/initial-opening",
    response_model=ShiftResponse,
)
def establish_initial_opening(
    payload: InitialOpeningFuelCreate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER)
    ),
):
    try:
        shift = FuelService.establish_initial_opening_fuel(
            db=db,
            vessel_id=payload.vessel_id,
            shift_date=payload.shift_date,
            opening_fuel=payload.opening_fuel,
            created_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(shift)

        return shift

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/shift/balance",
    response_model=ShiftBalanceResponse,
)
def get_shift_balance(
    shift_id: int,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        balance = FuelService.calculate_shift_balance(
            db=db,
            shift_id=shift_id,
        )

        shift = db.get(Shift, shift_id)

        if shift is None:
            raise ValueError("Shift not found.")

        return ShiftBalanceResponse(
            shift_id=shift.id,
            vessel_id=shift.vessel_id,
            shift_date=shift.shift_date,
            shift_name=shift.shift_name,
            **balance,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


@router.post(
    "/receipt",
    response_model=FuelTransactionResponse,
)
def record_receipt(
    payload: FuelTransactionCreate,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        transaction = FuelService.record_receipt(
            db=db,
            vessel_id=payload.vessel_id,
            shift_date=payload.shift_date,
            shift_name=payload.shift_name,
            quantity=payload.quantity,
            created_by_user_id=current_user.id,
            remarks=payload.remarks,
            source_vessel_id=payload.source_vessel_id,
            fuel_source=payload.fuel_source,
        )
        db.commit()
        db.refresh(transaction)

        return transaction

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/adjustment",
    response_model=FuelTransactionResponse,
)
def record_adjustment(
    payload: FuelTransactionCreate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER)
    ),
):
    if payload.adjustment_direction not in {
        AdjustmentDirection.IN.value,
        AdjustmentDirection.OUT.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Adjustment direction must be IN or OUT.",
        )

    try:
        transaction = FuelService.record_adjustment(
            db=db,
            vessel_id=payload.vessel_id,
            shift_date=payload.shift_date,
            shift_name=payload.shift_name,
            quantity=payload.quantity,
            direction=AdjustmentDirection(
                payload.adjustment_direction
            ),
            created_by_user_id=current_user.id,
            remarks=payload.remarks,
        )

        db.commit()
        db.refresh(transaction)

        return transaction

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/shift/{shift_id}/close",
    response_model=ShiftCloseResponse,
)
def close_shift(
    shift_id: int,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        shift = FuelService.close_shift(
            db=db,
            shift_id=shift_id,
        )

        db.commit()
        db.refresh(shift)

        return shift

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/shift/{shift_id}/reopen",
    response_model=ShiftResponse,
)
def reopen_shift(
    shift_id: int,
    payload: ShiftReopenRequest,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        shift = FuelService.reopen_shift(
            db=db,
            shift_id=shift_id,
            reopened_by_user_id=current_user.id,
            reason=payload.reason,
        )

        db.commit()
        db.refresh(shift)

        return shift

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/admin/shift/{shift_id}/close",
    response_model=ShiftCloseResponse,
)
def admin_close_shift(
    shift_id: int,
    payload: AdminShiftCloseRequest,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        shift = FuelService.close_shift(
            db=db,
            shift_id=shift_id,
            closed_by_user_id=current_user.id,
            reason=payload.reason,
        )
        db.commit()
        db.refresh(shift)
        return shift
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.put(
    "/shift/{shift_id}/production-data",
    response_model=ShiftResponse,
)
def update_shift_production_data(
    shift_id: int,
    payload: ShiftProductionDataUpdate,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        shift = FuelService.update_shift_production_data(
            db=db,
            shift_id=shift_id,
            advancement_m=payload.advancement_m,
            dredging_hours=payload.dredging_hours,
            updated_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(shift)

        return shift

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.put(
    "/admin/shift/{shift_id}/operational-data",
    response_model=ShiftResponse,
)
def admin_update_shift_operational_data(
    shift_id: int,
    payload: AdminShiftProductionDataUpdate,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        shift = db.get(Shift, shift_id)
        if shift is None:
            raise ValueError("Shift not found.")
        shift = FuelService.update_shift_production_data(
            db=db,
            shift_id=shift_id,
            advancement_m=(
                payload.advancement_m
                if "advancement_m" in payload.model_fields_set
                else shift.advancement_m
            ),
            dredging_hours=(
                payload.dredging_hours
                if "dredging_hours" in payload.model_fields_set
                else shift.dredging_hours
            ),
            updated_by_user_id=current_user.id,
            correction_reason=payload.reason,
        )
        db.commit()
        db.refresh(shift)
        return shift
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.patch(
    "/admin/shift/{shift_id}/opening",
    response_model=ShiftResponse,
)
def admin_correct_opening(
    shift_id: int,
    payload: OpeningFuelCorrection,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        shift = FuelService.correct_admin_opening_fuel(
            db=db,
            shift_id=shift_id,
            new_opening_fuel=payload.opening_fuel,
            corrected_by_user_id=current_user.id,
            reason=payload.reason,
        )
        db.commit()
        db.refresh(shift)
        return shift
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.patch(
    "/shift/{shift_id}/opening",
    response_model=ShiftResponse,
)
def correct_opening(
    shift_id: int,
    payload: OpeningFuelCorrection,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER)
    ),
):
    try:
        shift = FuelService.correct_opening_fuel(
            db=db,
            shift_id=shift_id,
            new_opening_fuel=payload.opening_fuel,
            corrected_by_user_id=current_user.id,
            reason=payload.reason,
        )

        db.commit()
        db.refresh(shift)

        return shift

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

@router.post(
    "/admin/adjustments/{transaction_id}/correct",
    response_model=FuelTransactionResponse,
)
def admin_correct_adjustment(
    transaction_id: int,
    payload: AdminAdjustmentCorrection,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        transaction = db.get(FuelTransaction, transaction_id)
        if transaction is None:
            raise ValueError("Adjustment transaction not found.")
        shift = db.get(Shift, transaction.shift_id)
        if shift is None:
            raise ValueError("Shift associated with adjustment was not found.")
        if shift.status != "OPEN":
            raise ValueError("Adjustments can only be corrected on an OPEN shift.")

        corrected = FuelService.correct_adjustment(
            db=db,
            adjustment_id=transaction_id,
            new_quantity=payload.quantity,
            new_direction=AdjustmentDirection(payload.direction),
            corrected_by_user_id=current_user.id,
            correction_remarks=payload.reason,
            reconcile_downstream=payload.reconcile_downstream,
        )
        db.commit()
        db.refresh(corrected)
        return corrected
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/admin/receipts/{transaction_id}/correct",
    response_model=FuelTransactionResponse,
)
def admin_correct_receipt(
    transaction_id: int,
    payload: AdminReceiptCorrection,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        transaction = FuelService.correct_admin_receipt(
            db=db,
            transaction_id=transaction_id,
            quantity=payload.quantity,
            source_vessel_id=payload.source_vessel_id,
            fuel_source=payload.fuel_source,
            remarks=payload.remarks,
            corrected_by_user_id=current_user.id,
            reason=payload.reason,
            reconcile_downstream=payload.reconcile_downstream,
        )
        db.commit()
        db.refresh(transaction)
        return transaction
    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/shift/open",
    response_model=ShiftResponse,
)
def open_shift(
    payload: ShiftOpenRequest,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        shift = FuelService.get_or_create_shift(
            db=db,
            vessel_id=payload.vessel_id,
            shift_date=payload.shift_date,
            shift_name=payload.shift_name,
        )

        db.commit()
        db.refresh(shift)

        return shift

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

@router.get(
    "/shift/{shift_id}/transactions",
    response_model=list[FuelTransactionResponse],
)
def get_shift_transactions(
    shift_id: int,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        return FuelService.get_shift_transactions(
            db=db,
            shift_id=shift_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

@router.get(
    "/shift/{shift_id}/report",
    response_model=ShiftReportResponse,
)
def get_shift_report(
    shift_id: int,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        shift = db.get(Shift, shift_id)

        if shift is None:
            raise ValueError("Shift not found.")

        balance = FuelService.calculate_shift_balance(
            db=db,
            shift_id=shift_id,
        )

        transactions = FuelService.get_shift_transactions(
            db=db,
            shift_id=shift_id,
        )

        return ShiftReportResponse(
            shift=shift,
            balance=ShiftBalanceResponse(
                shift_id=shift.id,
                vessel_id=shift.vessel_id,
                shift_date=shift.shift_date,
                shift_name=shift.shift_name,
                **balance,
            ),
            transactions=transactions,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
