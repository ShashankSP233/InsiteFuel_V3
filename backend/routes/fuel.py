from datetime import date
from backend.models.shift import Shift

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.dependencies import get_current_user, require_roles
from backend.models.fuel import AdjustmentDirection
from backend.models.user import User, UserRole
from backend.schemas.fuel import (
    FuelTransactionCreate,
    FuelTransactionResponse,
    InitialOpeningFuelCreate,
    ShiftBalanceResponse,
    ShiftCloseResponse,
    ShiftOpenRequest,
    ShiftReportResponse,
    ShiftResponse,
    OpeningFuelCorrection,
)
from backend.services.fuel_service import FuelService


router = APIRouter(
    prefix="/api/fuel",
    tags=["Fuel"],
)


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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