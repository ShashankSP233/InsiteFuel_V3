from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.dependencies import (
    db_session,
    get_current_user,
    require_roles,
)
from backend.models.project import Project
from backend.models.user import User, UserRole
from backend.schemas.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from backend.services.project_service import (
    create_project,
    get_project_by_id,
    update_project,
)


router = APIRouter(
    prefix="/api/projects",
    tags=["Projects"],
)


@router.get(
    "",
    response_model=list[ProjectResponse],
)
def list_projects(
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    return db.scalars(
        select(Project).order_by(Project.id)
    ).all()


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
def get_project(
    project_id: int,
    db: Session = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    project = get_project_by_id(
        db,
        project_id,
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    return project


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_new_project(
    payload: ProjectCreate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(
            UserRole.MANAGER,
        )
    ),
):
    try:
        project = create_project(
            db=db,
            name=payload.name,
            code=payload.code,
            description=payload.description,
        )

        db.commit()
        db.refresh(project)

        return project

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
)
def update_existing_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(
            UserRole.MANAGER,
        )
    ),
):
    project = get_project_by_id(
        db,
        project_id,
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    try:
        project = update_project(
            db,
            project,
            name=payload.name,
            code=payload.code,
            description=payload.description,
            is_active=payload.is_active,
        )

        db.commit()
        db.refresh(project)

        return project

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )