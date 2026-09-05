from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models.user import User
from backend.services.attachment_service import AttachmentService

router = APIRouter(
    prefix="/api/attachments",
    tags=["Attachments"],
)


@router.post(
    "/upload",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        attachment = AttachmentService.create_attachment(
            db=db,
            file=file,
            uploaded_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(attachment)

        return {
            "id": attachment.id,
            "original_filename": attachment.original_filename,
            "content_type": attachment.content_type,
            "file_size": attachment.file_size,
            "uploaded_by_user_id": attachment.uploaded_by_user_id,
            "created_at": attachment.created_at,
        }

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/{attachment_id}",
    response_model=dict,
)
def get_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = AttachmentService.get_attachment(
        db=db,
        attachment_id=attachment_id,
    )

    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found.",
        )

    return {
        "id": attachment.id,
        "original_filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "file_size": attachment.file_size,
        "uploaded_by_user_id": attachment.uploaded_by_user_id,
        "created_at": attachment.created_at,
    }


@router.get(
    "/{attachment_id}/download",
)
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = AttachmentService.get_attachment(
        db=db,
        attachment_id=attachment_id,
    )

    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found.",
        )

    return FileResponse(
        path=attachment.storage_path,
        media_type=attachment.content_type,
        filename=attachment.original_filename,
    )


@router.delete(
    "/{attachment_id}",
    response_model=dict,
)
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    attachment = AttachmentService.get_attachment(
        db=db,
        attachment_id=attachment_id,
    )

    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found.",
        )

    try:
        AttachmentService.delete_attachment(
            db=db,
            attachment=attachment,
            deleted_by_user_id=current_user.id,
        )

        db.commit()

        return {
            "message": "Attachment deleted successfully.",
        }

    except ValueError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )