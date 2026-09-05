from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy.orm import Session

from backend.models.attachment import Attachment
from backend.services.audit_service import AuditService


# Store uploaded files outside the Python source tree.
ATTACHMENT_STORAGE_DIR = Path("storage/attachments")

# Initial allowed types.
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class AttachmentService:

    @staticmethod
    def create_attachment(
        db: Session,
        *,
        file: UploadFile,
        uploaded_by_user_id: int,
    ) -> Attachment:

        if not file.filename:
            raise ValueError(
                "Uploaded file must have a filename."
            )

        if file.content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError(
                "Unsupported file type. Only JPEG, PNG, WebP, PDF files are allowed."
            )

        original_filename = Path(
            file.filename
        ).name

        if not original_filename:
            raise ValueError(
                "Invalid filename."
            )

        file_bytes = file.file.read()

        if not file_bytes:
            raise ValueError(
                "Uploaded file is empty."
            )

        file_size = len(file_bytes)

        if file_size > MAX_FILE_SIZE:
            raise ValueError(
                "File size cannot exceed 10 MB."
            )

        ATTACHMENT_STORAGE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        stored_filename = (
            f"{uuid4().hex}"
            f"{Path(original_filename).suffix.lower()}"
        )

        storage_path = (
            ATTACHMENT_STORAGE_DIR
            / stored_filename
        )

        storage_path.write_bytes(
            file_bytes
        )

        attachment = Attachment(
            original_filename=original_filename,
            stored_filename=stored_filename,
            storage_path=str(storage_path),
            content_type=file.content_type,
            file_size=file_size,
            uploaded_by_user_id=uploaded_by_user_id,
        )

        db.add(attachment)
        db.flush()

        AuditService.log(
            db,
            user_id=uploaded_by_user_id,
            action="UPLOAD_ATTACHMENT",
            entity="Attachment",
            entity_id=attachment.id,
            new_values={
                "original_filename": original_filename,
                "stored_filename": stored_filename,
                "content_type": file.content_type,
                "file_size": file_size,
            },
        )

        return attachment

    @staticmethod
    def get_attachment(
        db: Session,
        attachment_id: int,
    ) -> Attachment | None:
        return db.get(
            Attachment,
            attachment_id,
        )

    @staticmethod
    def delete_attachment(
        db: Session,
        *,
        attachment: Attachment,
        deleted_by_user_id: int,
    ) -> None:

        storage_path = Path(
            attachment.storage_path
        )

        if storage_path.exists():
            storage_path.unlink()

        AuditService.log(
            db,
            user_id=deleted_by_user_id,
            action="DELETE_ATTACHMENT",
            entity="Attachment",
            entity_id=attachment.id,
            old_values={
                "original_filename": attachment.original_filename,
                "stored_filename": attachment.stored_filename,
                "storage_path": attachment.storage_path,
                "content_type": attachment.content_type,
                "file_size": attachment.file_size,
            },
        )

        db.delete(attachment)
        db.flush()