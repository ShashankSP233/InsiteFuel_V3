from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.project import Project
from backend.models.vessel import Vessel
from backend.services.audit_service import AuditService


def get_vessel_by_id(
    db: Session,
    vessel_id: int,
) -> Vessel | None:
    return db.get(Vessel, vessel_id)


def get_vessel_by_name(
    db: Session,
    project_id: int,
    name: str,
) -> Vessel | None:
    return db.scalar(
        select(Vessel).where(
            Vessel.project_id == project_id,
            Vessel.name == name,
        )
    )


def get_vessel_by_code(
    db: Session,
    code: str,
) -> Vessel | None:
    return db.scalar(
        select(Vessel).where(
            Vessel.code == code,
        )
    )


def create_vessel(
    db: Session,
    project_id: int,
    name: str,
    code: str | None = None,
    fuel_threshold_litres: Decimal = Decimal("0"),
    created_by_user_id: int | None = None,
) -> Vessel:

    project = db.get(Project, project_id)

    if project is None:
        raise ValueError(
            "Project not found."
        )

    if not project.is_active:
        raise ValueError(
            "Cannot create a vessel under an inactive project."
        )

    if fuel_threshold_litres < 0:
        raise ValueError(
            "Fuel threshold cannot be negative."
        )

    name = name.strip()

    if not name:
        raise ValueError(
            "Vessel name cannot be empty."
        )

    if get_vessel_by_name(
        db,
        project_id,
        name,
    ):
        raise ValueError(
            f"Vessel '{name}' already exists in this project."
        )

    if code is not None:
        code = code.strip()

        if not code:
            code = None

        if (
            code is not None
            and get_vessel_by_code(db, code)
        ):
            raise ValueError(
                f"Vessel code '{code}' already exists."
            )

    vessel = Vessel(
        project_id=project_id,
        name=name,
        code=code,
        fuel_threshold_litres=fuel_threshold_litres,
        is_active=True,
    )

    db.add(vessel)
    db.flush()

    AuditService.log(
        db,
        user_id=created_by_user_id,
        action="CREATE_VESSEL",
        entity="Vessel",
        entity_id=vessel.id,
        new_values={
            "project_id": vessel.project_id,
            "name": vessel.name,
            "code": vessel.code,
            "fuel_threshold_litres": str(
                vessel.fuel_threshold_litres
            ),
            "is_active": vessel.is_active,
        },
    )

    return vessel


def update_vessel(
    db: Session,
    vessel: Vessel,
    *,
    project_id: int | None = None,
    name: str | None = None,
    code: str | None = None,
    is_active: bool | None = None,
    fuel_threshold_litres: Decimal | None = None,
    updated_by_user_id: int | None = None,
) -> Vessel:

    old_values = {
        "project_id": vessel.project_id,
        "name": vessel.name,
        "code": vessel.code,
        "is_active": vessel.is_active,
        "fuel_threshold_litres": str(
            vessel.fuel_threshold_litres
        ),
    }

    if project_id is not None:
        project = db.get(
            Project,
            project_id,
        )

        if project is None:
            raise ValueError(
                "Project not found."
            )

        if not project.is_active:
            raise ValueError(
                "Cannot move a vessel to an inactive project."
            )

        vessel.project_id = project_id

    if name is not None:
        name = name.strip()

        if not name:
            raise ValueError(
                "Vessel name cannot be empty."
            )

        existing = get_vessel_by_name(
            db,
            vessel.project_id,
            name,
        )

        if (
            existing is not None
            and existing.id != vessel.id
        ):
            raise ValueError(
                f"Vessel '{name}' already exists in this project."
            )

        vessel.name = name

    if code is not None:
        code = code.strip()

        if not code:
            code = None

        if code is not None:
            existing = get_vessel_by_code(
                db,
                code,
            )

            if (
                existing is not None
                and existing.id != vessel.id
            ):
                raise ValueError(
                    f"Vessel code '{code}' already exists."
                )

        vessel.code = code

    if is_active is not None:
        vessel.is_active = is_active

    if fuel_threshold_litres is not None:
        if fuel_threshold_litres < 0:
            raise ValueError(
                "Fuel threshold cannot be negative."
            )

        vessel.fuel_threshold_litres = fuel_threshold_litres

    db.flush()

    AuditService.log(
        db,
        user_id=updated_by_user_id,
        action="UPDATE_VESSEL",
        entity="Vessel",
        entity_id=vessel.id,
        old_values=old_values,
        new_values={
            "project_id": vessel.project_id,
            "name": vessel.name,
            "code": vessel.code,
            "is_active": vessel.is_active,
            "fuel_threshold_litres": str(
                vessel.fuel_threshold_litres
            ),
        },
    )

    return vessel


def update_fuel_threshold(
    db: Session,
    vessel: Vessel,
    fuel_threshold_litres: Decimal,
    updated_by_user_id: int | None = None,
) -> Vessel:

    if fuel_threshold_litres < 0:
        raise ValueError(
            "Fuel threshold cannot be negative."
        )

    old_value = vessel.fuel_threshold_litres

    vessel.fuel_threshold_litres = fuel_threshold_litres

    db.flush()

    AuditService.log(
        db,
        user_id=updated_by_user_id,
        action="UPDATE_VESSEL_FUEL_THRESHOLD",
        entity="Vessel",
        entity_id=vessel.id,
        old_values={
            "fuel_threshold_litres": str(old_value),
        },
        new_values={
            "fuel_threshold_litres": str(
                vessel.fuel_threshold_litres
            ),
        },
    )

    return vessel