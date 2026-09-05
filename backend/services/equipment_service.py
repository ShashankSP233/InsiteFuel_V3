from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.equipment import Equipment
from backend.models.vessel import Vessel
from backend.services.audit_service import AuditService

def get_equipment_by_id(
    db: Session,
    equipment_id: int,
) -> Equipment | None:
    return db.get(Equipment, equipment_id)


def get_equipment_by_name(
    db: Session,
    vessel_id: int,
    name: str,
) -> Equipment | None:
    return db.scalar(
        select(Equipment).where(
            Equipment.vessel_id == vessel_id,
            Equipment.name == name,
        )
    )


def get_equipment_by_code(
    db: Session,
    code: str,
) -> Equipment | None:
    return db.scalar(
        select(Equipment).where(
            Equipment.code == code,
        )
    )


def create_equipment(
    db,
    vessel_id,
    name,
    equipment_type,
    code=None,
    created_by_user_id: int | None = None,
) -> Equipment:
    
    vessel = db.get(Vessel, vessel_id)

    if vessel is None:
        raise ValueError(
            "Vessel not found."
        )

    if not vessel.is_active:
        raise ValueError(
            "Cannot create equipment under an inactive vessel."
        )

    name = name.strip()

    if not name:
        raise ValueError(
            "Equipment name cannot be empty."
        )

    equipment_type = equipment_type.strip()

    if not equipment_type:
        raise ValueError(
            "Equipment type cannot be empty."
        )

    if get_equipment_by_name(
        db,
        vessel_id,
        name,
    ):
        raise ValueError(
            f"Equipment '{name}' already exists on this vessel."
        )

    if code is not None:
        code = code.strip()

        if not code:
            code = None

        if (
            code is not None
            and get_equipment_by_code(db, code)
        ):
            raise ValueError(
                f"Equipment code '{code}' already exists."
            )

    equipment = Equipment(
        vessel_id=vessel_id,
        name=name,
        equipment_type=equipment_type,
        code=code,
        is_active=True,
    )

    db.add(equipment)
    db.flush()
    AuditService.log(
        db,
        user_id=created_by_user_id,
        action="CREATE_EQUIPMENT",
        entity="Equipment",
        entity_id=equipment.id,
        new_values={
            "vessel_id": equipment.vessel_id,
            "name": equipment.name,
            "equipment_type": equipment.equipment_type,
            "code": equipment.code,
            "is_active": equipment.is_active,
        },
    )
    return equipment


def update_equipment(
    db: Session,
    equipment: Equipment,
    *,
    vessel_id: int | None = None,
    name: str | None = None,
    equipment_type: str | None = None,
    code: str | None = None,
    is_active: bool | None = None,
    updated_by_user_id: int | None = None
) -> Equipment:

    target_vessel_id = (
        vessel_id
        if vessel_id is not None
        else equipment.vessel_id
    )
    old_values = {
        "vessel_id": equipment.vessel_id,
        "name": equipment.name,
        "equipment_type": equipment.equipment_type,
        "code": equipment.code,
        "is_active": equipment.is_active,
    }
    if vessel_id is not None:
        vessel = db.get(
            Vessel,
            vessel_id,
        )

        if vessel is None:
            raise ValueError(
                "Vessel not found."
            )

        if not vessel.is_active:
            raise ValueError(
                "Cannot move equipment to an inactive vessel."
            )

    if name is not None:
        name = name.strip()

        if not name:
            raise ValueError(
                "Equipment name cannot be empty."
            )

        existing = get_equipment_by_name(
            db,
            target_vessel_id,
            name,
        )

        if (
            existing is not None
            and existing.id != equipment.id
        ):
            raise ValueError(
                f"Equipment '{name}' already exists "
                "on this vessel."
            )

        equipment.name = name

    if vessel_id is not None:
        equipment.vessel_id = vessel_id

    if equipment_type is not None:
        equipment_type = equipment_type.strip()

        if not equipment_type:
            raise ValueError(
                "Equipment type cannot be empty."
            )

        equipment.equipment_type = equipment_type

    if code is not None:
        code = code.strip()

        if not code:
            code = None

        if code is not None:
            existing = get_equipment_by_code(
                db,
                code,
            )

            if (
                existing is not None
                and existing.id != equipment.id
            ):
                raise ValueError(
                    f"Equipment code '{code}' already exists."
                )

        equipment.code = code

    if is_active is not None:
        equipment.is_active = is_active

    db.flush()
    AuditService.log(
        db,
        user_id=updated_by_user_id,
        action="UPDATE_EQUIPMENT",
        entity="Equipment",
        entity_id=equipment.id,
        old_values=old_values,
        new_values={
            "vessel_id": equipment.vessel_id,
            "name": equipment.name,
            "equipment_type": equipment.equipment_type,
            "code": equipment.code,
            "is_active": equipment.is_active,
        },
    )
    return equipment