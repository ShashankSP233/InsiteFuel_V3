from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, require_roles
from backend.models.transfer import FuelTransfer
from backend.models.user import User, UserRole
from backend.schemas.transfer import (
    TransferApprove,
    TransferCorrection,
    TransferCreate,
    TransferReject,
    TransferResponse,
    TransferReceive,
    TransferSubmitReview,
)
from backend.services.transfer_service import TransferService


router = APIRouter(
    prefix="/api/transfers",
    tags=["Transfers"],
)


@router.post(
    "",
    response_model=TransferResponse,
    status_code=status.HTTP_201_CREATED,
)
def initiate_transfer(
    data: TransferCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        transfer = TransferService.initiate_transfer(
            db=db,
            from_vessel_id=data.from_vessel_id,
            from_shift_id=data.from_shift_id,
            to_vessel_id=data.to_vessel_id,
            to_shift_id=data.to_shift_id,
            initiated_quantity=data.initiated_quantity,
            initiated_by_user_id=current_user.id,
            transfer_date=data.transfer_date,
            notes=data.notes,
        )

        db.commit()
        db.refresh(transfer)

        return transfer

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/{transfer_id}/receive",
    response_model=TransferResponse,
)
def confirm_receiving(
    transfer_id: int,
    data: TransferReceive,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        transfer = TransferService.confirm_receiving(
            db=db,
            transfer_id=transfer_id,
            received_quantity=data.received_quantity,
            received_by_user_id=current_user.id,
            notes=data.notes,
        )

        db.commit()
        db.refresh(transfer)

        return transfer

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/{transfer_id}/submit-review",
    response_model=TransferResponse,
)
def submit_for_manager_review(
    transfer_id: int,
    data: TransferSubmitReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        transfer = TransferService.submit_for_manager_review(
            db=db,
            transfer_id=transfer_id,
            submitted_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(transfer)

        return transfer

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/{transfer_id}/reject",
    response_model=TransferResponse,
)
def reject_transfer(
    transfer_id: int,
    data: TransferReject,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER, UserRole.ADMIN)
    ),
):
    try:
        transfer = TransferService.reject_transfer(
            db=db,
            transfer_id=transfer_id,
            reviewed_by_user_id=current_user.id,
            manager_remark=data.manager_remark,
        )

        db.commit()
        db.refresh(transfer)

        return transfer

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/{transfer_id}/approve",
    response_model=TransferResponse,
)
def approve_transfer(
    transfer_id: int,
    data: TransferApprove,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER, UserRole.ADMIN)
    ),
):
    try:
        transfer = TransferService.approve_transfer(
            db=db,
            transfer_id=transfer_id,
            approved_by_user_id=current_user.id,
            manager_remark=data.manager_remark,
        )

        db.commit()
        db.refresh(transfer)

        return transfer

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "",
    response_model=list[TransferResponse],
)
def list_transfers(
    transfer_status: str | None = Query(default=None, alias="status"),
    from_vessel_id: int | None = None,
    to_vessel_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    statement = select(FuelTransfer)

    if transfer_status:
        statement = statement.where(
            FuelTransfer.status == transfer_status
        )

    if from_vessel_id is not None:
        statement = statement.where(
            FuelTransfer.from_vessel_id == from_vessel_id
        )

    if to_vessel_id is not None:
        statement = statement.where(
            FuelTransfer.to_vessel_id == to_vessel_id
        )

    statement = statement.order_by(FuelTransfer.created_at.desc())

    return db.scalars(statement).all()


@router.get(
    "/{transfer_id}",
    response_model=TransferResponse,
)
def get_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    transfer = db.get(FuelTransfer, transfer_id)

    if transfer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer not found.",
        )

    return transfer

@router.post(
    "/{transfer_id}/correct",
    response_model=TransferResponse,
)
def correct_transfer(
    transfer_id: int,
    data: TransferCorrection,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER, UserRole.ADMIN)
    ),
):
    if not data.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one correction field must be provided.",
        )

    try:
        transfer = TransferService.correct_transfer_before_approval(
            db=db,
            transfer_id=transfer_id,
            corrected_by_user_id=current_user.id,
            initiated_quantity=data.initiated_quantity,
            received_quantity=data.received_quantity,
            manager_remark=data.manager_remark,
            notes=data.notes,
        )

        db.commit()
        db.refresh(transfer)

        return transfer

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

@router.post(
    "/{transfer_id}/correct-approved",
    response_model=TransferResponse,
)
def correct_approved_transfer(
    transfer_id: int,
    data: TransferCorrection,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER, UserRole.ADMIN)
    ),
):
    if not data.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one correction field must be provided.",
        )

    try:
        transfer = TransferService.correct_approved_transfer(
            db=db,
            transfer_id=transfer_id,
            corrected_by_user_id=current_user.id,
            initiated_quantity=data.initiated_quantity,
            received_quantity=data.received_quantity,
            manager_remark=data.manager_remark,
            notes=data.notes,
        )

        db.commit()
        db.refresh(transfer)

        return transfer

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

