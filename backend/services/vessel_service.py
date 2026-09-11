from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.project import Project
from backend.models.site import Site
from backend.models.vessel import Vessel
from backend.services.audit_service import AuditService


ALLOWED_VESSEL_TYPES = {
    "Dredger",
    "Tug Boat",
    "Survey Boat",
    "House Boat",
    "Wooden Boat",
    "Steel Boat",
    "Fiber Boat",
    "Dredge Pump Boat",
    "Tanker",
}


def get_vessel_by_id(
    db: Session,
    vessel_id: int,
) -> Vessel | None:
    return db.get(
        Vessel,
        vessel_id,
    )


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


def get_site_for_vessel(
    db: Session,
    site_id: int,
) -> Site | None:
    return db.get(
        Site,
        site_id,
    )


def validate_vessel_site(
    db: Session,
    *,
    project_id: int,
    site_id: int,
) -> Site:

    site = get_site_for_vessel(
        db,
        site_id,
    )

    if site is None:
        raise ValueError(
            "Site not found."
        )

    if site.project_id != project_id:
        raise ValueError(
            "Selected Site does not belong to the selected Project."
        )

    if not site.is_active:
        raise ValueError(
            "Cannot assign a vessel to an inactive Site."
        )

    return site


def create_vessel(
    db: Session,
    project_id: int,
    site_id: int,
    name: str,
    code: str,
    vessel_type: str,
    is_active: bool = True,
    fuel_threshold_litres: Decimal = Decimal("0"),
    created_by_user_id: int | None = None,
) -> Vessel:

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
            "Cannot create a vessel under an inactive project."
        )

    validate_vessel_site(
        db,
        project_id=project_id,
        site_id=site_id,
    )

    if vessel_type not in ALLOWED_VESSEL_TYPES:
        raise ValueError(
            f"Invalid vessel type '{vessel_type}'."
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

    code = code.strip()

    if not code:
        raise ValueError(
            "Vessel code cannot be empty."
        )

    if get_vessel_by_name(
        db,
        project_id,
        name,
    ):
        raise ValueError(
            f"Vessel '{name}' already exists in this project."
        )

    if get_vessel_by_code(
        db,
        code,
    ):
        raise ValueError(
            f"Vessel code '{code}' already exists."
        )

    vessel = Vessel(
        project_id=project_id,
        site_id=site_id,
        name=name,
        code=code,
        vessel_type=vessel_type,
        is_active=is_active,
        fuel_threshold_litres=fuel_threshold_litres,
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
            "site_id": vessel.site_id,
            "name": vessel.name,
            "code": vessel.code,
            "vessel_type": vessel.vessel_type,
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
    site_id: int | None = None,
    name: str | None = None,
    code: str | None = None,
    vessel_type: str | None = None,
    is_active: bool | None = None,
    fuel_threshold_litres: Decimal | None = None,
    updated_by_user_id: int | None = None,
) -> Vessel:

    old_values = {
        "project_id": vessel.project_id,
        "site_id": vessel.site_id,
        "name": vessel.name,
        "code": vessel.code,
        "vessel_type": vessel.vessel_type,
        "is_active": vessel.is_active,
        "fuel_threshold_litres": str(
            vessel.fuel_threshold_litres
        ),
    }

    target_project_id = (
        project_id
        if project_id is not None
        else vessel.project_id
    )

    target_site_id = (
        site_id
        if site_id is not None
        else vessel.site_id
    )

    project = db.get(
        Project,
        target_project_id,
    )

    if project is None:
        raise ValueError(
            "Project not found."
        )

    if not project.is_active:
        raise ValueError(
            "Cannot move a vessel to an inactive project."
        )

    if target_site_id is not None:
        validate_vessel_site(
            db,
            project_id=target_project_id,
            site_id=target_site_id,
        )

    if name is not None:
        name = name.strip()

        if not name:
            raise ValueError(
                "Vessel name cannot be empty."
            )

        existing = get_vessel_by_name(
            db,
            target_project_id,
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
            raise ValueError(
                "Vessel code cannot be empty."
            )

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

    if vessel_type is not None:
        if vessel_type not in ALLOWED_VESSEL_TYPES:
            raise ValueError(
                f"Invalid vessel type '{vessel_type}'."
            )

        vessel.vessel_type = vessel_type

    project_changed = (
        vessel.project_id != target_project_id
    )

    site_changed = (
        vessel.site_id != target_site_id
    )

    vessel.project_id = target_project_id

    if site_id is not None:
        vessel.site_id = site_id

    if is_active is not None:
        vessel.is_active = is_active

    if fuel_threshold_litres is not None:
        if fuel_threshold_litres < 0:
            raise ValueError(
                "Fuel threshold cannot be negative."
            )

        vessel.fuel_threshold_litres = (
            fuel_threshold_litres
        )

    db.flush()

    new_values = {
        "project_id": vessel.project_id,
        "site_id": vessel.site_id,
        "name": vessel.name,
        "code": vessel.code,
        "vessel_type": vessel.vessel_type,
        "is_active": vessel.is_active,
        "fuel_threshold_litres": str(
            vessel.fuel_threshold_litres
        ),
    }

    AuditService.log(
        db,
        user_id=updated_by_user_id,
        action="UPDATE_VESSEL",
        entity="Vessel",
        entity_id=vessel.id,
        old_values=old_values,
        new_values=new_values,
    )

    if site_changed:
        AuditService.log(
            db,
            user_id=updated_by_user_id,
            action="MOVE_VESSEL_SITE",
            entity="Vessel",
            entity_id=vessel.id,
            old_values={
                "project_id": old_values["project_id"],
                "site_id": old_values["site_id"],
            },
            new_values={
                "project_id": vessel.project_id,
                "site_id": vessel.site_id,
            },
            details="Vessel moved to another Site.",
        )

    elif project_changed:
        AuditService.log(
            db,
            user_id=updated_by_user_id,
            action="MOVE_VESSEL_PROJECT",
            entity="Vessel",
            entity_id=vessel.id,
            old_values={
                "project_id": old_values["project_id"],
                "site_id": old_values["site_id"],
            },
            new_values={
                "project_id": vessel.project_id,
                "site_id": vessel.site_id,
            },
            details="Vessel moved to another Project.",
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