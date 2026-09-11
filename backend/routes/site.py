from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.dependencies import (
    db_session,
    get_current_user,
    require_roles,
)
from backend.models.user import User, UserRole
from backend.schemas.site import (
    SiteCreate,
    SiteResponse,
    SiteUpdate,
)
from backend.services.site_service import (
    create_site,
    get_site_by_id,
    get_sites,
    update_site,
)


router = APIRouter(
    prefix="/api/sites",
    tags=["Sites"],
)


@router.get(
    "",
    response_model=list[SiteResponse],
)
def list_sites(
    project_id: int | None = Query(
        default=None,
    ),
    db: Session = Depends(db_session),
    current_user: User = Depends(
        get_current_user
    ),
):
    return get_sites(
        db,
        project_id=project_id,
    )


@router.get(
    "/{site_id}",
    response_model=SiteResponse,
)
def get_site(
    site_id: int,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        get_current_user
    ),
):
    site = get_site_by_id(
        db,
        site_id,
    )

    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    return site


@router.post(
    "",
    response_model=SiteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_new_site(
    payload: SiteCreate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER)
    ),
):
    try:
        site = create_site(
            db=db,
            project_id=payload.project_id,
            name=payload.name,
            site_code=payload.site_code,
            is_active=payload.is_active,
            created_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(site)

        return site

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.put(
    "/{site_id}",
    response_model=SiteResponse,
)
def update_existing_site(
    site_id: int,
    payload: SiteUpdate,
    db: Session = Depends(db_session),
    current_user: User = Depends(
        require_roles(UserRole.MANAGER)
    ),
):
    site = get_site_by_id(
        db,
        site_id,
    )

    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site not found.",
        )

    try:
        site = update_site(
            db,
            site,
            project_id=payload.project_id,
            name=payload.name,
            site_code=payload.site_code,
            is_active=payload.is_active,
            updated_by_user_id=current_user.id,
        )

        db.commit()
        db.refresh(site)

        return site

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )