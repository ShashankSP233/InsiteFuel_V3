from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.project import Project
from backend.models.site import Site
from backend.services.audit_service import AuditService


def get_site_by_id(
    db: Session,
    site_id: int,
) -> Site | None:
    return db.get(
        Site,
        site_id,
    )


def get_site_by_code(
    db: Session,
    project_id: int,
    site_code: str,
) -> Site | None:
    return db.scalar(
        select(Site).where(
            Site.project_id == project_id,
            Site.site_code == site_code,
        )
    )


def get_sites(
    db: Session,
    project_id: int | None = None,
) -> list[Site]:

    query = select(Site).order_by(
        Site.project_id,
        Site.id,
    )

    if project_id is not None:
        query = query.where(
            Site.project_id == project_id
        )

    return list(
        db.scalars(query).all()
    )


def create_site(
    db: Session,
    *,
    project_id: int,
    name: str,
    site_code: str,
    is_active: bool = True,
    created_by_user_id: int | None = None,
) -> Site:

    project = db.get(
        Project,
        project_id,
    )

    if project is None:
        raise ValueError(
            "Project not found."
        )

    name = name.strip()
    site_code = site_code.strip()

    if not name:
        raise ValueError(
            "Site name cannot be empty."
        )

    if not site_code:
        raise ValueError(
            "Site code cannot be empty."
        )

    existing = get_site_by_code(
        db,
        project_id,
        site_code,
    )

    if existing is not None:
        raise ValueError(
            f"Site code '{site_code}' already exists in this project."
        )

    site = Site(
        project_id=project_id,
        name=name,
        site_code=site_code,
        is_active=is_active,
    )

    db.add(site)
    db.flush()

    AuditService.log(
        db=db,
        user_id=created_by_user_id,
        action="CREATE_SITE",
        entity="sites",
        entity_id=site.id,
        old_values=None,
        new_values={
            "project_id": site.project_id,
            "name": site.name,
            "site_code": site.site_code,
            "is_active": site.is_active,
        },
        details="Site created.",
    )

    return site


def update_site(
    db: Session,
    site: Site,
    *,
    project_id: int | None = None,
    name: str | None = None,
    site_code: str | None = None,
    is_active: bool | None = None,
    updated_by_user_id: int | None = None,
) -> Site:

    old_values = {
        "project_id": site.project_id,
        "name": site.name,
        "site_code": site.site_code,
        "is_active": site.is_active,
    }

    target_project_id = (
        project_id
        if project_id is not None
        else site.project_id
    )

    project = db.get(
        Project,
        target_project_id,
    )

    if project is None:
        raise ValueError(
            "Project not found."
        )

    if name is not None:
        name = name.strip()

        if not name:
            raise ValueError(
                "Site name cannot be empty."
            )

        site.name = name

    if site_code is not None:
        site_code = site_code.strip()

        if not site_code:
            raise ValueError(
                "Site code cannot be empty."
            )

        existing = get_site_by_code(
            db,
            target_project_id,
            site_code,
        )

        if (
            existing is not None
            and existing.id != site.id
        ):
            raise ValueError(
                f"Site code '{site_code}' already exists in this project."
            )

        site.site_code = site_code

    if project_id is not None:
        site.project_id = project_id

    if is_active is not None:
        site.is_active = is_active

    db.flush()

    new_values = {
        "project_id": site.project_id,
        "name": site.name,
        "site_code": site.site_code,
        "is_active": site.is_active,
    }

    AuditService.log(
        db=db,
        user_id=updated_by_user_id,
        action="UPDATE_SITE",
        entity="sites",
        entity_id=site.id,
        old_values=old_values,
        new_values=new_values,
        details="Site updated.",
    )

    return site