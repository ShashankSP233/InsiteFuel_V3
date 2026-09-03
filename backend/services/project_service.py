from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.project import Project


def get_project_by_id(
    db: Session,
    project_id: int,
) -> Project | None:
    return db.get(Project, project_id)


def get_project_by_name(
    db: Session,
    name: str,
) -> Project | None:
    return db.scalar(
        select(Project).where(
            Project.name == name
        )
    )


def get_project_by_code(
    db: Session,
    code: str,
) -> Project | None:
    return db.scalar(
        select(Project).where(
            Project.code == code
        )
    )


def create_project(
    db: Session,
    name: str,
    code: str | None = None,
    description: str | None = None,
) -> Project:

    name = name.strip()

    if not name:
        raise ValueError(
            "Project name cannot be empty."
        )

    if get_project_by_name(db, name):
        raise ValueError(
            f"Project '{name}' already exists."
        )

    if code is not None:
        code = code.strip()

        if not code:
            code = None

        if code is not None and get_project_by_code(db, code):
            raise ValueError(
                f"Project code '{code}' already exists."
            )

    project = Project(
        name=name,
        code=code,
        description=description,
        is_active=True,
    )

    db.add(project)
    db.flush()

    return project


def update_project(
    db: Session,
    project: Project,
    *,
    name: str | None = None,
    code: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> Project:

    if name is not None:
        name = name.strip()

        if not name:
            raise ValueError(
                "Project name cannot be empty."
            )

        existing = get_project_by_name(db, name)

        if (
            existing is not None
            and existing.id != project.id
        ):
            raise ValueError(
                f"Project '{name}' already exists."
            )

        project.name = name

    if code is not None:
        code = code.strip()

        if not code:
            code = None

        if code is not None:
            existing = get_project_by_code(db, code)

            if (
                existing is not None
                and existing.id != project.id
            ):
                raise ValueError(
                    f"Project code '{code}' already exists."
                )

        project.code = code

    if description is not None:
        project.description = description

    if is_active is not None:
        project.is_active = is_active

    db.flush()

    return project