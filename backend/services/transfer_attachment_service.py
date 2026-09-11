from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.attachment import Attachment
from backend.models.transfer import FuelTransfer
from backend.models.transfer_attachment import TransferAttachment
from backend.services.audit_service import AuditService


class TransferAttachmentService:
    MAX_ATTACHMENTS_PER_TRANSFER = 5

    @staticmethod
    def add_attachment(
        db: Session,
        transfer_id: int,
        attachment_id: int,
        created_by_user_id: int,
    ) -> TransferAttachment:

        transfer = db.scalar(
            select(FuelTransfer)
            .where(FuelTransfer.id == transfer_id)
            .with_for_update()
        )

        if transfer is None:
            raise ValueError("Transfer not found.")

        attachment = db.get(Attachment, attachment_id)

        if attachment is None:
            raise ValueError("Attachment not found.")

        attachment_count = db.scalar(
            select(func.count(TransferAttachment.id))
            .where(
                TransferAttachment.transfer_id == transfer_id
            )
        ) or 0

        if attachment_count >= TransferAttachmentService.MAX_ATTACHMENTS_PER_TRANSFER:
            raise ValueError(
                "This transfer already has the maximum of 5 transfer notes."
            )

        # Prevent the same attachment from being linked twice.
        existing = db.scalar(
            select(TransferAttachment)
            .where(
                TransferAttachment.transfer_id == transfer_id,
                TransferAttachment.attachment_id == attachment_id,
            )
        )

        if existing is not None:
            raise ValueError(
                "This attachment is already linked to the transfer."
            )

        transfer_attachment = TransferAttachment(
            transfer_id=transfer_id,
            attachment_id=attachment_id,
        )

        db.add(transfer_attachment)
        db.flush()

        AuditService.log(
            db=db,
            user_id=created_by_user_id,
            action="ADD_TRANSFER_ATTACHMENT",
            entity="transfer_attachments",
            entity_id=transfer_attachment.id,
            new_values={
                "transfer_id": transfer_id,
                "attachment_id": attachment_id,
            },
            details=(
                f"Transfer note attached to Transfer #{transfer_id}."
            ),
        )

        return transfer_attachment

    @staticmethod
    def list_attachments(
        db: Session,
        transfer_id: int,
    ) -> list[TransferAttachment]:

        transfer = db.scalar(
            select(FuelTransfer)
            .where(FuelTransfer.id == transfer_id)
            .with_for_update()
        )

        if transfer is None:
            raise ValueError("Transfer not found.")

        statement = (
            select(TransferAttachment)
            .where(
                TransferAttachment.transfer_id == transfer_id
            )
            .order_by(TransferAttachment.created_at.asc())
        )

        return list(db.scalars(statement).all())

    @staticmethod
    def count_attachments(
        db: Session,
        transfer_id: int,
    ) -> int:

        return (
            db.scalar(
                select(func.count(TransferAttachment.id))
                .where(
                    TransferAttachment.transfer_id == transfer_id
                )
            )
            or 0
        )