import csv
import io
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user, require_roles
from backend.models.fuel import FuelTransaction
from backend.models.shift import Shift
from backend.models.transfer import FuelTransfer, TransferStatus
from backend.models.vessel import Vessel
from backend.models.user import User, UserRole
from backend.schemas.transfer import (
    AdminTransferCorrection,
    TransferApprove,
    TransferCorrection,
    TransferCreate,
    TransferReject,
    TransferResponse,
    TransferReceive,
    TransferSubmitReview,
    BalanceNeutralTransferLedgerRequest,
)

from backend.schemas.transfer_attachment import (
    TransferAttachmentCreate,
    TransferAttachmentResponse,
)
from backend.services.transfer_attachment_service import (
    TransferAttachmentService,
)

from backend.services.transfer_service import TransferService


router = APIRouter(
    prefix="/api/transfers",
    tags=["Transfers"],
)


@router.post("/admin/{transfer_id}/record-balance-neutral-ledger")
def record_balance_neutral_transfer_ledger(
    transfer_id: int,
    data: BalanceNeutralTransferLedgerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        entries = TransferService.record_balance_neutral_ledger(
            db,
            transfer_id=transfer_id,
            recorded_by_user_id=current_user.id,
            reason=data.reason,
        )
        db.commit()
        return {
            "transfer_id": transfer_id,
            "created": len(entries),
            "transaction_ids": [entry.id for entry in entries],
            "balances_changed": False,
        }
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


def _admin_transfer_rows(
    db: Session,
    from_date: date | None,
    to_date: date | None,
    transfer_status: str | None,
    vessel_id: int | None,
):
    # The transfer timestamp records when it was entered in the system. The
    # report is operational, so date filtering and display use the source
    # shift's date instead.
    statement = (
        select(FuelTransfer, Shift.shift_date.label("shift_date"))
        .join(Shift, Shift.id == FuelTransfer.from_shift_id)
    )
    if from_date:
        statement = statement.where(
            Shift.shift_date >= from_date
        )
    if to_date:
        statement = statement.where(
            Shift.shift_date <= to_date
        )
    if transfer_status:
        statement = statement.where(FuelTransfer.status == transfer_status)
    if vessel_id is not None:
        statement = statement.where(
            (FuelTransfer.from_vessel_id == vessel_id)
            | (FuelTransfer.to_vessel_id == vessel_id)
        )
    transfer_rows = db.execute(
        statement.order_by(Shift.shift_date.desc(), FuelTransfer.id.desc())
    ).all()
    transfers = [transfer for transfer, _ in transfer_rows]
    shift_dates = {
        transfer.id: shift_date.isoformat() if shift_date else None
        for transfer, shift_date in transfer_rows
    }
    vessel_ids = {value for transfer in transfers for value in (transfer.from_vessel_id, transfer.to_vessel_id)}
    transfer_ids = [transfer.id for transfer in transfers]
    ledger_entries = db.execute(
        select(
            FuelTransaction.reference_id,
            FuelTransaction.reference_type,
            FuelTransaction.transaction_type,
        ).where(
            FuelTransaction.reference_id.in_(transfer_ids),
            FuelTransaction.reference_type.in_(
                ("TRANSFER", "BALANCE_NEUTRAL_TRANSFER")
            ),
        )
    ).all() if transfer_ids else []
    ledger_by_transfer: dict[int, list[tuple[str, str]]] = {}
    for reference_id, reference_type, transaction_type in ledger_entries:
        ledger_by_transfer.setdefault(reference_id, []).append(
            (reference_type, transaction_type)
        )
    def ledger_state(transfer: FuelTransfer) -> str:
        entries = ledger_by_transfer.get(transfer.id, [])
        if any(kind == "TRANSFER" for kind, _ in entries):
            return "RECORDED"
        if not entries:
            return "MISSING"
        transaction_types = {transaction_type for _, transaction_type in entries}
        expected_types = {"TRANSFER_OUT", "TRANSFER_IN"}
        return "BALANCE_NEUTRAL" if expected_types.issubset(transaction_types) else "PARTIAL"
    names = {
        vessel.id: vessel.name
        for vessel in db.scalars(select(Vessel).where(Vessel.id.in_(vessel_ids))).all()
    } if vessel_ids else {}
    return [
        {
            "id": transfer.id,
            "from_vessel": names.get(transfer.from_vessel_id, str(transfer.from_vessel_id)),
            "to_vessel": names.get(transfer.to_vessel_id, str(transfer.to_vessel_id)),
            "shift_date": shift_dates.get(transfer.id),
            "initiated_quantity": str(transfer.initiated_quantity),
            "received_quantity": str(transfer.received_quantity) if transfer.received_quantity is not None else None,
            "loss_quantity": str(transfer.loss_quantity) if transfer.loss_quantity is not None else None,
            "status": transfer.status.value if hasattr(transfer.status, "value") else transfer.status,
            "notes": transfer.notes,
            "manager_remark": transfer.manager_remark,
            "ledger_state": ledger_state(transfer),
        }
        for transfer in transfers
    ]


@router.get("/admin/report")
def admin_transfer_report(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    transfer_status: str | None = Query(None, alias="status"),
    vessel_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="From date cannot be later than to date.")
    return _admin_transfer_rows(db, from_date, to_date, transfer_status, vessel_id)


@router.get("/admin/report.csv")
def export_admin_transfer_report(
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    transfer_status: str | None = Query(None, alias="status"),
    vessel_id: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="From date cannot be later than to date.")
    rows = _admin_transfer_rows(db, from_date, to_date, transfer_status, vessel_id)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    headers = ["ID", "From vessel", "To vessel", "Shift date", "Initiated (L)", "Received (L)", "Loss (L)", "Status", "Notes", "Manager remark"]
    writer.writerow(headers)
    def safe_cell(value):
        text = "" if value is None else str(value)
        return f"'{text}" if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text

    fields = ("id", "from_vessel", "to_vessel", "shift_date", "initiated_quantity", "received_quantity", "loss_quantity", "status", "notes", "manager_remark")
    quantity_fields = {"initiated_quantity", "received_quantity", "loss_quantity"}
    csv_rows = []
    for row in rows:
        values = []
        for key in fields:
            value = row[key]
            if value is not None and key in quantity_fields:
                value = str(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            values.append(safe_cell(value))
        csv_rows.append(values)
    writer.writerows(csv_rows)
    suffix = f"_{from_date}_{to_date}" if from_date and to_date else ""
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="insitefuel_transfers{suffix}.csv"'},
    )

@router.post(
    "/{transfer_id}/attachments",
    response_model=TransferAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_transfer_attachment(
    transfer_id: int,
    data: TransferAttachmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        transfer_attachment = (
            TransferAttachmentService.add_attachment(
                db=db,
                transfer_id=transfer_id,
                attachment_id=data.attachment_id,
                created_by_user_id=current_user.id,
            )
        )

        db.commit()
        db.refresh(transfer_attachment)

        return transfer_attachment

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/{transfer_id}/attachments",
    response_model=list[TransferAttachmentResponse],
)
def list_transfer_attachments(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return TransferAttachmentService.list_attachments(
            db=db,
            transfer_id=transfer_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

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


@router.post(
    "/admin/{transfer_id}/correct",
    response_model=TransferResponse,
)
def admin_correct_transfer(
    transfer_id: int,
    data: AdminTransferCorrection,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    if not data.reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Correction reason is required.",
        )
    if not (data.model_fields_set - {"reason"}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one correction field must be provided.",
        )

    try:
        transfer = db.get(FuelTransfer, transfer_id)
        if transfer is None:
            raise ValueError("Transfer not found.")

        source_shift = db.get(Shift, transfer.from_shift_id)
        destination_shift = db.get(Shift, transfer.to_shift_id)
        if source_shift is None or destination_shift is None:
            raise ValueError("Both transfer shifts must exist.")
        if source_shift.vessel_id != transfer.from_vessel_id:
            raise ValueError("Source shift does not belong to source vessel.")
        if destination_shift.vessel_id != transfer.to_vessel_id:
            raise ValueError("Destination shift does not belong to destination vessel.")
        if source_shift.status != "OPEN" or destination_shift.status != "OPEN":
            raise ValueError(
                "Transfer corrections require both shifts to be OPEN. "
                "Reopen them explicitly before correcting the transfer."
            )

        if transfer.status == TransferStatus.INITIATED.value:
            if data.received_quantity is not None:
                raise ValueError(
                    "An INITIATED transfer cannot be corrected with a received quantity."
                )
            corrected = TransferService.correct_transfer_before_approval(
                db=db,
                transfer_id=transfer_id,
                corrected_by_user_id=current_user.id,
                initiated_quantity=data.initiated_quantity,
                notes=data.notes,
                correction_reason=data.reason.strip(),
            )
        elif transfer.status in {
            TransferStatus.RECEIVING_CONFIRMED.value,
            TransferStatus.MANAGER_REVIEW.value,
        }:
            corrected = TransferService.correct_transfer_before_approval(
                db=db,
                transfer_id=transfer_id,
                corrected_by_user_id=current_user.id,
                initiated_quantity=data.initiated_quantity,
                received_quantity=data.received_quantity,
                notes=data.notes,
                correction_reason=data.reason.strip(),
            )
        elif transfer.status in {
            TransferStatus.APPROVED.value,
            TransferStatus.BALANCES_UPDATED.value,
        }:
            if (
                data.initiated_quantity is None
                and data.received_quantity is None
            ):
                raise ValueError(
                    "Approved-transfer correction requires a quantity change."
                )
            corrected = TransferService.correct_approved_transfer(
                db=db,
                transfer_id=transfer_id,
                corrected_by_user_id=current_user.id,
                initiated_quantity=data.initiated_quantity,
                received_quantity=data.received_quantity,
                notes=data.notes,
                correction_reason=data.reason.strip(),
                reconcile_downstream=data.reconcile_downstream,
            )
        else:
            raise ValueError(
                f"Transfer in status '{transfer.status}' cannot be corrected."
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

