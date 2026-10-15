from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.attachment import Attachment
from backend.models.shift_attachments import ShiftAttachment
from backend.services.audit_service import AuditService


class ShiftAttachmentService:

    @staticmethod
    def attach(
        db: Session,
        *,
        shift_id: int,
        attachment_id: int,
        attachment_type: str,
        created_by_user_id: int,
    ) -> ShiftAttachment:

        attachment = db.get(Attachment, attachment_id)
        if not attachment:
            raise ValueError("Attachment not found.")

        link = ShiftAttachment(
            shift_id=shift_id,
            attachment_id=attachment_id,
            attachment_type=attachment_type,
            created_by_user_id=created_by_user_id,
        )

        db.add(link)
        db.flush()

        return link

    @staticmethod
    def list_for_shift(
        db: Session,
        *,
        shift_id: int,
    ) -> list[dict]:

        rows = db.execute(
            select(ShiftAttachment, Attachment)
            .join(
                Attachment,
                Attachment.id == ShiftAttachment.attachment_id,
            )
            .where(ShiftAttachment.shift_id == shift_id)
            .order_by(ShiftAttachment.created_at.desc())
        ).all()

        return [
            {
                "id": link.id,
                "shift_id": link.shift_id,
                "attachment_id": attachment.id,
                "attachment_type": link.attachment_type,
                "original_filename": attachment.original_filename,
                "stored_filename": attachment.stored_filename,
                "content_type": attachment.content_type,
                "file_size": attachment.file_size,
                "created_by_user_id": link.created_by_user_id,
                "created_at": link.created_at,
            }
            for link, attachment in rows
        ]

    @staticmethod
    def remove_link(
        db: Session,
        *,
        shift_id: int,
        link_id: int,
        removed_by_user_id: int,
        reason: str,
    ) -> None:
        link = db.get(ShiftAttachment, link_id)
        if link is None:
            raise ValueError("Shift attachment link not found.")
        if link.shift_id != shift_id:
            raise ValueError("Attachment link does not belong to the selected shift.")

        reason = reason.strip() if reason else ""
        if not reason:
            raise ValueError("Correction reason is required.")
        if link.attachment_type == "SOUNDING":
            raise ValueError("Manage sounding attachments through the sounding record.")

        old_values = {
            "shift_id": link.shift_id,
            "attachment_id": link.attachment_id,
            "attachment_type": link.attachment_type,
        }
        link_id = link.id
        db.delete(link)
        db.flush()
        AuditService.log(
            db=db,
            user_id=removed_by_user_id,
            action="REMOVE_SHIFT_ATTACHMENT_LINK",
            entity="shift_attachments",
            entity_id=link_id,
            old_values=old_values,
            new_values=None,
            reason=reason,
            details="Shift attachment link removed; shared attachment file was retained.",
        )