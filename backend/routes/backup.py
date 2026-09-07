from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.dependencies import require_roles
from backend.models.user import User, UserRole
from backend.services.backup_service import BackupService


router = APIRouter(prefix="/api/backup", tags=["Backup"])


@router.post("")
def create_backup(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    try:
        backup_path = BackupService.create_backup(
            created_by_user_id=current_user.id
        )

        return {
            "message": "Backup created successfully",
            "filename": backup_path.name,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Backup creation failed: {exc}",
        )


@router.get("")
def list_backups(
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    return BackupService.list_backups()


@router.get("/{filename}/download")
def download_backup(
    filename: str,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    backup_path = BackupService.get_backup(filename)

    if not backup_path:
        raise HTTPException(
            status_code=404,
            detail="Backup not found",
        )

    return FileResponse(
        path=backup_path,
        filename=backup_path.name,
        media_type="application/zip",
    )