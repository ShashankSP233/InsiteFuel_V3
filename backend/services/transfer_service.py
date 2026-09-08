from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.fuel import FuelTransaction, FuelTransactionType
from backend.models.shift import Shift
from backend.models.transfer import FuelTransfer, TransferStatus
from backend.models.vessel import Vessel
from backend.services.fuel_service import FuelService
from backend.services.audit_service import AuditService

class TransferService:

    @staticmethod
    def initiate_transfer(
        db: Session,
        from_vessel_id: int,
        from_shift_id: int,
        to_vessel_id: int,
        to_shift_id: int,
        initiated_quantity: Decimal,
        initiated_by_user_id: int,
        notes: str | None = None,
    ) -> FuelTransfer:

        if initiated_quantity <= 0:
            raise ValueError(
                "Transfer quantity must be greater than zero."
            )

        if from_vessel_id == to_vessel_id:
            raise ValueError(
                "Source and destination vessels must be different."
            )

        from_vessel = db.get(Vessel, from_vessel_id)

        if from_vessel is None:
            raise ValueError("Source vessel not found.")

        to_vessel = db.get(Vessel, to_vessel_id)

        if to_vessel is None:
            raise ValueError("Destination vessel not found.")

        if not from_vessel.is_active:
            raise ValueError("Source vessel is inactive.")

        if not to_vessel.is_active:
            raise ValueError("Destination vessel is inactive.")

        # Get source shift
        from_shift = db.get(Shift, from_shift_id)

        if from_shift is None:
            raise ValueError("Source shift not found.")

        # Get destination shift
        to_shift = db.get(Shift, to_shift_id)

        if to_shift is None:
            raise ValueError("Destination shift not found.")

        # Make sure the source shift belongs to the source vessel.
        if from_shift.vessel_id != from_vessel_id:
            raise ValueError(
                "Source shift does not belong to the source vessel."
            )

        # Make sure the destination shift belongs to the destination vessel.
        if to_shift.vessel_id != to_vessel_id:
            raise ValueError(
                "Destination shift does not belong to the destination vessel."
            )

        # Transfers must be initiated against open shifts.
        if from_shift.status != "OPEN":
            raise ValueError(
                "Source shift is closed."
            )

        if to_shift.status != "OPEN":
            raise ValueError(
                "Destination shift is closed."
            )

        transfer = FuelTransfer(
            from_vessel_id=from_vessel_id,
            from_shift_id=from_shift_id,
            to_vessel_id=to_vessel_id,
            to_shift_id=to_shift_id,
            initiated_quantity=initiated_quantity,
            status=TransferStatus.INITIATED,
            initiated_by_user_id=initiated_by_user_id,
            notes=notes,
        )

        db.add(transfer)
        db.flush()
        AuditService.log(
            db=db,
            user_id=initiated_by_user_id,
            action="INITIATE_TRANSFER",
            entity="transfers",
            entity_id=transfer.id,
            old_values=None,
            new_values={
                "from_vessel_id": transfer.from_vessel_id,
                "from_shift_id": transfer.from_shift_id,
                "to_vessel_id": transfer.to_vessel_id,
                "to_shift_id": transfer.to_shift_id,
                "initiated_quantity": str(transfer.initiated_quantity),
                "status": transfer.status.value,
                "notes": transfer.notes,
            },
            details="Fuel transfer initiated.",
        )
        return transfer

    @staticmethod
    def confirm_receiving(
        db: Session,
        transfer_id: int,
        received_quantity: Decimal,
        received_by_user_id: int,
        notes: str | None = None,
    ) -> FuelTransfer:

        if received_quantity < 0:
            raise ValueError(
                "Received quantity cannot be negative."
            )

        transfer = db.get(FuelTransfer, transfer_id)

        if transfer is None:
            raise ValueError("Transfer not found.")

        if transfer.status != TransferStatus.INITIATED:
            raise ValueError(
                "Only initiated transfers can be receiving-confirmed."
            )

        # Get the destination shift recorded when the transfer was initiated.
        to_shift = db.get(Shift, transfer.to_shift_id)

        if to_shift is None:
            raise ValueError(
                "Destination shift not found."
            )

        # Make sure the stored shift still belongs to the destination vessel.
        if to_shift.vessel_id != transfer.to_vessel_id:
            raise ValueError(
                "Destination shift does not belong to the destination vessel."
            )

        if to_shift.status != "OPEN":
            raise ValueError(
                "Destination shift is closed."
            )

        initiated_quantity = Decimal(
            str(transfer.initiated_quantity)
        )

        received_quantity = Decimal(
            str(received_quantity)
        )

        if received_quantity > initiated_quantity:
            raise ValueError(
                "Received quantity cannot exceed initiated quantity."
            )

        loss_quantity = (
            initiated_quantity - received_quantity
        ).quantize(Decimal("0.001"))

        transfer.received_quantity = received_quantity
        transfer.loss_quantity = loss_quantity
        transfer.received_by_user_id = received_by_user_id
        transfer.received_at = now_ist()

        if notes:
            transfer.notes = notes

        transfer.status = TransferStatus.RECEIVING_CONFIRMED

        AuditService.log(
            db=db,
            user_id=received_by_user_id,
            action="CONFIRM_TRANSFER_RECEIVING",
            entity="transfers",
            entity_id=transfer.id,
            old_values={
                "status": TransferStatus.INITIATED.value,
                "received_quantity": None,
                "loss_quantity": None,
            },
            new_values={
                "status": TransferStatus.RECEIVING_CONFIRMED.value,
                "received_quantity": str(transfer.received_quantity),
                "loss_quantity": str(transfer.loss_quantity),
                "notes": transfer.notes,
            },
            details="Receiving vessel confirmed the actual received fuel quantity.",
        )

        db.flush()

        return transfer

    @staticmethod
    def submit_for_manager_review(
        db: Session,
        transfer_id: int,
        submitted_by_user_id: int,
    ) -> FuelTransfer:

        transfer = db.get(FuelTransfer, transfer_id)

        if transfer is None:
            raise ValueError("Transfer not found.")

        if transfer.status != TransferStatus.RECEIVING_CONFIRMED:
            raise ValueError(
                "Only receiving-confirmed transfers can be submitted for manager review."
            )

        if transfer.received_quantity is None:
            raise ValueError(
                "Received quantity must be recorded before review."
            )

        transfer.status = TransferStatus.MANAGER_REVIEW

        db.flush()
        AuditService.log(
            db=db,
            user_id=submitted_by_user_id,
            action="SUBMIT_TRANSFER_FOR_REVIEW",
            entity="transfers",
            entity_id=transfer.id,
            old_values={
                "status": TransferStatus.RECEIVING_CONFIRMED.value,
            },
            new_values={
                "status": TransferStatus.MANAGER_REVIEW.value,
            },
            details="Fuel transfer submitted for Manager/Admin review.",
        )
        return transfer

    @staticmethod
    def reject_transfer(
        db: Session,
        transfer_id: int,
        reviewed_by_user_id: int,
        manager_remark: str,
    ) -> FuelTransfer:
        """
        Reject a transfer during Manager/Admin review.

        Rejection does not create any fuel ledger transactions.
        """

        if not manager_remark or not manager_remark.strip():
            raise ValueError(
                "A rejection remark is required."
            )

        transfer = db.get(FuelTransfer, transfer_id)

        if transfer is None:
            raise ValueError("Transfer not found.")

        if transfer.status != TransferStatus.MANAGER_REVIEW:
            raise ValueError(
                "Only transfers awaiting manager review can be rejected."
            )

        transfer.status = TransferStatus.REJECTED
        transfer.reviewed_by_user_id = reviewed_by_user_id
        transfer.reviewed_at = now_ist()
        transfer.manager_remark = manager_remark.strip()

        AuditService.log(
            db=db,
            user_id=reviewed_by_user_id,
            action="REJECT_TRANSFER",
            entity="transfers",
            entity_id=transfer.id,
            old_values={
                "status": TransferStatus.MANAGER_REVIEW.value,
            },
            new_values={
                "status": TransferStatus.REJECTED.value,
                "manager_remark": transfer.manager_remark,
            },
            reason=transfer.manager_remark,
            details=f"Transfer #{transfer.id} rejected during Manager/Admin review.",
        )

        db.flush()

        return transfer

    @staticmethod
    def approve_transfer(
        db: Session,
        transfer_id: int,
        approved_by_user_id: int,
        manager_remark: str | None = None,
    ) -> FuelTransfer:
        """
        Approve a transfer and apply its fuel ledger effects atomically.

        Source vessel:
            TRANSFER_OUT = initiated quantity

        Destination vessel:
            TRANSFER_IN = received quantity

        Transfer loss:
            Stored on FuelTransfer.loss_quantity and does not affect either
            vessel's fuel balance.
        """

        transfer = db.get(FuelTransfer, transfer_id)

        if transfer is None:
            raise ValueError("Transfer not found.")

        if transfer.status != TransferStatus.MANAGER_REVIEW:
            raise ValueError(
                "Only transfers awaiting manager review can be approved."
            )

        if transfer.received_quantity is None:
            raise ValueError(
                "Received quantity must be recorded before approval."
            )

        # Get both shifts.
        from_shift = db.get(Shift, transfer.from_shift_id)

        if from_shift is None:
            raise ValueError(
                "Source shift not found."
            )

        to_shift = db.get(Shift, transfer.to_shift_id)

        if to_shift is None:
            raise ValueError(
                "Destination shift not found."
            )

        # Verify the shifts still belong to the correct vessels.
        if from_shift.vessel_id != transfer.from_vessel_id:
            raise ValueError(
                "Source shift does not belong to the source vessel."
            )

        if to_shift.vessel_id != transfer.to_vessel_id:
            raise ValueError(
                "Destination shift does not belong to the destination vessel."
            )

        # Both shifts must still be open.
        if from_shift.status != "OPEN":
            raise ValueError(
                "Source shift is closed."
            )

        if to_shift.status != "OPEN":
            raise ValueError(
                "Destination shift is closed."
            )

        initiated_quantity = Decimal(
            str(transfer.initiated_quantity)
        )

        received_quantity = Decimal(
            str(transfer.received_quantity)
        )

        # Recalculate the loss instead of blindly trusting the stored value.
        loss_quantity = (
            initiated_quantity - received_quantity
        ).quantize(Decimal("0.001"))

        if loss_quantity < 0:
            raise ValueError(
                "Received quantity cannot exceed initiated quantity."
            )

        source_balance = FuelService.calculate_shift_balance(
            db,
            from_shift.id,
        )

        if source_balance["closing_fuel"] < initiated_quantity:
            raise ValueError(
                "Source shift does not have enough fuel for this transfer."
            )

        # Keep the transfer record consistent with the calculated value.
        transfer.loss_quantity = loss_quantity

        # Source vessel loses the quantity that was actually sent.
        FuelService.record_transfer_out(
            db=db,
            vessel_id=transfer.from_vessel_id,
            shift_date=from_shift.shift_date,
            shift_name=from_shift.shift_name,
            quantity=initiated_quantity,
            transfer_id=transfer.id,
            created_by_user_id=approved_by_user_id,
            remarks=f"Transfer #{transfer.id} out",
        )

        # Destination vessel receives the quantity that was actually received.
        # A zero receipt is valid and therefore creates no TRANSFER_IN entry.
        if received_quantity > 0:
            FuelService.record_transfer_in(
                db=db,
                vessel_id=transfer.to_vessel_id,
                shift_date=to_shift.shift_date,
                shift_name=to_shift.shift_name,
                quantity=received_quantity,
                transfer_id=transfer.id,
                created_by_user_id=approved_by_user_id,
                remarks=f"Transfer #{transfer.id} in",
            )

        transfer.status = TransferStatus.APPROVED
        transfer.reviewed_by_user_id = approved_by_user_id
        transfer.reviewed_at = now_ist()
        transfer.approved_by_user_id = approved_by_user_id
        transfer.approved_at = now_ist()

        if manager_remark:
            transfer.manager_remark = manager_remark.strip()

        db.flush()

        # Mark the transfer as fully applied only after both ledger
        # transactions have been created successfully.
        transfer.status = TransferStatus.BALANCES_UPDATED

        AuditService.log(
            db=db,
            user_id=approved_by_user_id,
            action="APPROVE_TRANSFER",
            entity="transfers",
            entity_id=transfer.id,
            old_values={
                "status": TransferStatus.MANAGER_REVIEW.value,
                "initiated_quantity": str(initiated_quantity),
                "received_quantity": str(received_quantity),
                "loss_quantity": str(loss_quantity),
            },
            new_values={
                "status": TransferStatus.BALANCES_UPDATED.value,
                "initiated_quantity": str(initiated_quantity),
                "received_quantity": str(received_quantity),
                "loss_quantity": str(loss_quantity),
            },
            reason=(
                manager_remark.strip()
                if manager_remark and manager_remark.strip()
                else "Transfer approved by Manager/Admin."
            ),
            details=(
                f"Transfer #{transfer.id} approved. "
                f"Source decreased by {initiated_quantity}; "
                f"destination increased by {received_quantity}; "
                f"loss recorded as {loss_quantity}."
            ),
        )

        db.flush()

        return transfer

    @staticmethod
    def correct_transfer_before_approval(
        db: Session,
        transfer_id: int,
        corrected_by_user_id: int,
        initiated_quantity: Decimal | None = None,
        received_quantity: Decimal | None = None,
        manager_remark: str | None = None,
        notes: str | None = None,
    ):
        transfer = db.get(FuelTransfer, transfer_id)

        if transfer is None:
            raise ValueError("Transfer not found.")

        allowed_statuses = {
            TransferStatus.INITIATED.value,
            TransferStatus.RECEIVING_CONFIRMED.value,
            TransferStatus.MANAGER_REVIEW.value,
        }

        if transfer.status not in allowed_statuses:
            raise ValueError(
                "Only transfers that have not been approved can be corrected."
            )

        old_status = (
            transfer.status.value
            if hasattr(transfer.status, "value")
            else transfer.status
        )
        old_manager_remark = transfer.manager_remark
        old_notes = transfer.notes
        old_loss = (
            Decimal(str(transfer.loss_quantity))
            if transfer.loss_quantity is not None
            else None
        )

        current_initiated = Decimal(str(transfer.initiated_quantity))

        new_initiated = (
            current_initiated
            if initiated_quantity is None
            else Decimal(str(initiated_quantity))
        )

        if new_initiated <= 0:
            raise ValueError(
                "Initiated quantity must be greater than zero."
            )

        current_received = (
            None
            if transfer.received_quantity is None
            else Decimal(str(transfer.received_quantity))
        )

        new_received = (
            current_received
            if received_quantity is None
            else Decimal(str(received_quantity))
        )

        if new_received is not None:
            if new_received < 0:
                raise ValueError(
                    "Received quantity cannot be negative."
                )

            if new_received > new_initiated:
                raise ValueError(
                    "Received quantity cannot exceed initiated quantity."
                )

        # If the transfer has not been received yet, do not create a
        # received quantity or loss value.
        if new_received is None:
            new_loss = None
        else:
            new_loss = (
                new_initiated - new_received
            ).quantize(Decimal("0.001"))

        transfer.initiated_quantity = new_initiated

        if new_received is not None:
            transfer.received_quantity = new_received
            transfer.loss_quantity = new_loss

        if manager_remark is not None:
            transfer.manager_remark = manager_remark

        if notes is not None:
            transfer.notes = notes

        AuditService.log(
            db=db,
            user_id=corrected_by_user_id,
            action="CORRECT_TRANSFER",
            entity="transfers",
            entity_id=transfer.id,
            old_values={
                "status": old_status,
                "initiated_quantity": str(current_initiated),
                "received_quantity": (
                    str(current_received)
                    if current_received is not None
                    else None
                ),
                "loss_quantity": (
                    str(old_loss)
                    if old_loss is not None
                    else None
                ),
                "manager_remark": old_manager_remark,
                "notes": old_notes,
            },
            new_values={
                "status": transfer.status.value if hasattr(transfer.status, "value") else transfer.status,
                "initiated_quantity": str(new_initiated),
                "received_quantity": (
                    str(new_received)
                    if new_received is not None
                    else None
                ),
                "loss_quantity": (
                    str(new_loss)
                    if new_loss is not None
                    else None
                ),
                "manager_remark": transfer.manager_remark,
                "notes": transfer.notes,
            },
            reason=(
                manager_remark.strip()
                if manager_remark and manager_remark.strip()
                else "Pre-approval transfer correction."
            ),
            details=(
                f"Transfer #{transfer.id} corrected before approval. "
                "No fuel ledger transactions were created or changed."
            ),
        )

        db.flush()

        return transfer

    @staticmethod
    def _get_current_transfer_ledger_transaction(
        db: Session,
        transfer_id: int,
        transaction_type: str,
    ):
        current = db.scalars(
            select(FuelTransaction)
            .where(
                FuelTransaction.reference_type == "TRANSFER",
                FuelTransaction.reference_id == transfer_id,
                FuelTransaction.transaction_type == transaction_type,
            )
            .order_by(FuelTransaction.id.asc())
        ).first()

        if current is None:
            return None

        while True:
            corrected = db.scalars(
                select(FuelTransaction)
                .where(
                    FuelTransaction.reference_type == "TRANSFER_CORRECTION",
                    FuelTransaction.reference_id == current.id,
                    FuelTransaction.transaction_type == transaction_type,
                )
                .order_by(FuelTransaction.id.desc())
            ).first()

            if corrected is None:
                return current

            current = corrected

    @staticmethod
    def correct_approved_transfer(
        db: Session,
        transfer_id: int,
        corrected_by_user_id: int,
        initiated_quantity: Decimal | None = None,
        received_quantity: Decimal | None = None,
        manager_remark: str | None = None,
        notes: str | None = None,
    ):
        transfer = db.get(FuelTransfer, transfer_id)

        if transfer is None:
            raise ValueError("Transfer not found.")

        allowed_statuses = {
            TransferStatus.APPROVED.value,
            TransferStatus.BALANCES_UPDATED.value,
        }

        if transfer.status not in allowed_statuses:
            raise ValueError(
                "Only approved transfers can use approved-transfer correction."
            )

        old_status = (
            transfer.status.value
            if hasattr(transfer.status, "value")
            else transfer.status
        )
        old_manager_remark = transfer.manager_remark
        old_notes = transfer.notes

        current_initiated = Decimal(str(transfer.initiated_quantity))

        new_initiated = (
            current_initiated
            if initiated_quantity is None
            else Decimal(str(initiated_quantity))
        )

        if new_initiated <= 0:
            raise ValueError(
                "Initiated quantity must be greater than zero."
            )

        current_received = (
            None
            if transfer.received_quantity is None
            else Decimal(str(transfer.received_quantity))
        )

        if current_received is None:
            raise ValueError(
                "Approved transfer does not have a received quantity."
            )

        new_received = (
            current_received
            if received_quantity is None
            else Decimal(str(received_quantity))
        )

        if new_received < 0:
            raise ValueError(
                "Received quantity cannot be negative."
            )

        if new_received > new_initiated:
            raise ValueError(
                "Received quantity cannot exceed initiated quantity."
            )

        from_shift = db.get(Shift, transfer.from_shift_id)
        to_shift = db.get(Shift, transfer.to_shift_id)

        if from_shift is None:
            raise ValueError("Source shift not found.")

        if to_shift is None:
            raise ValueError("Destination shift not found.")

        if from_shift.vessel_id != transfer.from_vessel_id:
            raise ValueError(
                "Source shift does not belong to source vessel."
            )

        if to_shift.vessel_id != transfer.to_vessel_id:
            raise ValueError(
                "Destination shift does not belong to destination vessel."
            )

        old_source_transaction = (
            TransferService._get_current_transfer_ledger_transaction(
                db,
                transfer_id,
                FuelTransactionType.TRANSFER_OUT.value,
            )
        )

        if old_source_transaction is None:
            raise ValueError(
                "Current source transfer ledger entry not found."
            )

        old_source_quantity = Decimal(
            str(old_source_transaction.quantity)
        )

        old_destination_transaction = (
            TransferService._get_current_transfer_ledger_transaction(
                db,
                transfer_id,
                FuelTransactionType.TRANSFER_IN.value,
            )
        )

        old_destination_quantity = (
            Decimal(str(old_destination_transaction.quantity))
            if old_destination_transaction is not None
            else Decimal("0")
        )

        # Current balances already include the existing transfer effect.
        # Reverse that effect conceptually before checking the corrected value.
        source_balance = FuelService.calculate_shift_balance(
            db,
            from_shift.id,
        )

        projected_source_balance = (
            Decimal(str(source_balance["closing_fuel"]))
            + old_source_quantity
            - new_initiated
        )

        if projected_source_balance < 0:
            raise ValueError(
                "Correction would make the source shift fuel balance negative."
            )

        destination_balance = FuelService.calculate_shift_balance(
            db,
            to_shift.id,
        )

        projected_destination_balance = (
            Decimal(str(destination_balance["closing_fuel"]))
            - old_destination_quantity
            + new_received
        )

        if projected_destination_balance < 0:
            raise ValueError(
                "Correction would make the destination shift fuel balance negative."
            )

        # ---------------------------------------------------------
        # SOURCE REVERSAL
        # ---------------------------------------------------------

        source_reversal = FuelTransaction(
            shift_id=from_shift.id,
            vessel_id=from_shift.vessel_id,
            transaction_type=FuelTransactionType.TRANSFER_IN.value,
            quantity=old_source_quantity,
            reference_type="TRANSFER_CORRECTION_REVERSAL",
            reference_id=old_source_transaction.id,
            remarks=(
                f"Reversal of transfer correction ledger entry "
                f"#{old_source_transaction.id}"
            ),
            created_by_user_id=corrected_by_user_id,
        )

        db.add(source_reversal)
        db.flush()

        # ---------------------------------------------------------
        # SOURCE CORRECTED ENTRY
        # ---------------------------------------------------------

        source_corrected = FuelTransaction(
            shift_id=from_shift.id,
            vessel_id=from_shift.vessel_id,
            transaction_type=FuelTransactionType.TRANSFER_OUT.value,
            quantity=new_initiated,
            reference_type="TRANSFER_CORRECTION",
            reference_id=old_source_transaction.id,
            remarks=(
                f"Corrected transfer #{transfer.id}: "
                f"source quantity changed to {new_initiated}"
            ),
            created_by_user_id=corrected_by_user_id,
        )

        db.add(source_corrected)
        db.flush()

        # ---------------------------------------------------------
        # DESTINATION REVERSAL
        # ---------------------------------------------------------

        if old_destination_transaction is not None:
            destination_reversal = FuelTransaction(
                shift_id=to_shift.id,
                vessel_id=to_shift.vessel_id,
                transaction_type=FuelTransactionType.TRANSFER_OUT.value,
                quantity=old_destination_quantity,
                reference_type="TRANSFER_CORRECTION_REVERSAL",
                reference_id=old_destination_transaction.id,
                remarks=(
                    f"Reversal of transfer correction ledger entry "
                    f"#{old_destination_transaction.id}"
                ),
                created_by_user_id=corrected_by_user_id,
            )

            db.add(destination_reversal)
            db.flush()

        # ---------------------------------------------------------
        # DESTINATION CORRECTED ENTRY
        # ---------------------------------------------------------

        if new_received > 0:
            destination_corrected = FuelTransaction(
                shift_id=to_shift.id,
                vessel_id=to_shift.vessel_id,
                transaction_type=FuelTransactionType.TRANSFER_IN.value,
                quantity=new_received,
                reference_type="TRANSFER_CORRECTION",
                reference_id=(
                    old_destination_transaction.id
                    if old_destination_transaction is not None
                    else transfer.id
                ),
                remarks=(
                    f"Corrected transfer #{transfer.id}: "
                    f"received quantity changed to {new_received}"
                ),
                created_by_user_id=corrected_by_user_id,
            )

            db.add(destination_corrected)
            db.flush()

        # ---------------------------------------------------------
        # UPDATE TRANSFER EFFECTIVE VALUES
        # ---------------------------------------------------------

        transfer.initiated_quantity = new_initiated
        transfer.received_quantity = new_received
        transfer.loss_quantity = (
            new_initiated - new_received
        ).quantize(Decimal("0.001"))

        if manager_remark is not None:
            transfer.manager_remark = manager_remark

        if notes is not None:
            transfer.notes = notes

        # ---------------------------------------------------------
        # RECALCULATE BOTH SHIFTS
        # ---------------------------------------------------------

        FuelService.recalculate_shift(
            db,
            from_shift.id,
        )

        FuelService.recalculate_shift(
            db,
            to_shift.id,
        )

        AuditService.log(
            db=db,
            user_id=corrected_by_user_id,
            action="CORRECT_APPROVED_TRANSFER",
            entity="transfers",
            entity_id=transfer.id,
            old_values={
                "status": old_status,
                "initiated_quantity": str(current_initiated),
                "received_quantity": str(current_received),
                "loss_quantity": str(
                    (
                        current_initiated - current_received
                    ).quantize(Decimal("0.001"))
                ),
                "manager_remark": old_manager_remark,
                "notes": old_notes,
            },
            new_values={
                "status": old_status,
                "initiated_quantity": str(new_initiated),
                "received_quantity": str(new_received),
                "loss_quantity": str(
                    (
                        new_initiated - new_received
                    ).quantize(Decimal("0.001"))
                ),
                "manager_remark": transfer.manager_remark,
                "notes": transfer.notes,
            },
            reason=(
                manager_remark.strip()
                if manager_remark and manager_remark.strip()
                else "Approved transfer correction."
            ),
            details=(
                f"Approved transfer #{transfer.id} corrected. "
                "Ledger history was preserved using reversal and corrected entries."
            ),
        )

        db.flush()

        return transfer


    