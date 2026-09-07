from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.equipment import Equipment
from backend.models.project import Project
from backend.models.user import User, UserRole
from backend.models.vessel import Vessel
from backend.services.audit_service import AuditService
from backend.services.auth_service import hash_password


class BootstrapService:

    @staticmethod
    def is_required(db: Session) -> bool:
        return db.scalar(select(User.id).limit(1)) is None

    @staticmethod
    def initialize(db: Session) -> bool:
        """
        Initialize a completely empty V3 database.

        This is intentionally only for the first startup.
        Once a user exists, startup will never seed data again.
        """

        if not BootstrapService.is_required(db):
            return False

        # ---------------------------------------------------------
        # ADMIN
        # ---------------------------------------------------------

        admin = User(
            username=settings.bootstrap_admin_username,
            password_hash=hash_password(
                settings.bootstrap_admin_password
            ),
            role=UserRole.ADMIN.value,
            full_name=settings.bootstrap_admin_name,
            is_active=True,
        )

        db.add(admin)
        db.flush()

        AuditService.log(
            db=db,
            user_id=admin.id,
            action="BOOTSTRAP_ADMIN",
            entity="users",
            entity_id=admin.id,
            old_values=None,
            new_values={
                "username": admin.username,
                "role": admin.role,
                "full_name": admin.full_name,
                "is_active": admin.is_active,
            },
            details="Initial administrator account created during system bootstrap.",
        )

        # ---------------------------------------------------------
        # PROJECTS
        # ---------------------------------------------------------

        project1 = Project(
            name="Demo Project Alpha",
            code="DEMO-A",
            description="Initial V3 development project.",
            is_active=True,
        )

        project2 = Project(
            name="Demo Project Beta",
            code="DEMO-B",
            description="Initial V3 development project.",
            is_active=True,
        )

        db.add_all([project1, project2])
        db.flush()

        for project in (project1, project2):
            AuditService.log(
                db=db,
                user_id=admin.id,
                action="BOOTSTRAP_PROJECT",
                entity="Project",
                entity_id=project.id,
                old_values=None,
                new_values={
                    "name": project.name,
                    "code": project.code,
                    "is_active": project.is_active,
                },
                details="Initial project created during system bootstrap.",
            )

        # ---------------------------------------------------------
        # VESSELS
        # ---------------------------------------------------------

        vessel1 = Vessel(
            project_id=project1.id,
            name="Demo Dredger 01",
            code="DREDGER-01",
            fuel_threshold_litres=500,
            is_active=True,
        )

        vessel2 = Vessel(
            project_id=project1.id,
            name="Demo Dredger 02",
            code="DREDGER-02",
            fuel_threshold_litres=500,
            is_active=True,
        )

        vessel3 = Vessel(
            project_id=project2.id,
            name="Demo Barge 01",
            code="BARGE-01",
            fuel_threshold_litres=300,
            is_active=True,
        )

        db.add_all([vessel1, vessel2, vessel3])
        db.flush()

        for vessel in (vessel1, vessel2, vessel3):
            AuditService.log(
                db=db,
                user_id=admin.id,
                action="BOOTSTRAP_VESSEL",
                entity="Vessel",
                entity_id=vessel.id,
                old_values=None,
                new_values={
                    "project_id": vessel.project_id,
                    "name": vessel.name,
                    "code": vessel.code,
                    "fuel_threshold_litres": str(
                        vessel.fuel_threshold_litres
                    ),
                    "is_active": vessel.is_active,
                },
                details="Initial vessel created during system bootstrap.",
            )

        # ---------------------------------------------------------
        # EQUIPMENT
        # ---------------------------------------------------------

        vessels = [vessel1, vessel2, vessel3]

        for vessel in vessels:
            equipment_items = [
                Equipment(
                    vessel_id=vessel.id,
                    name="Main Engine",
                    equipment_type="ME",
                    code=f"{vessel.code}-ME",
                    is_active=True,
                ),
                Equipment(
                    vessel_id=vessel.id,
                    name="Auxiliary Engine",
                    equipment_type="AUX",
                    code=f"{vessel.code}-AUX",
                    is_active=True,
                ),
                Equipment(
                    vessel_id=vessel.id,
                    name="Diesel Generator",
                    equipment_type="DG",
                    code=f"{vessel.code}-DG",
                    is_active=True,
                ),
            ]

            db.add_all(equipment_items)
            db.flush()

            for equipment in equipment_items:
                AuditService.log(
                    db=db,
                    user_id=admin.id,
                    action="BOOTSTRAP_EQUIPMENT",
                    entity="Equipment",
                    entity_id=equipment.id,
                    old_values=None,
                    new_values={
                        "vessel_id": equipment.vessel_id,
                        "name": equipment.name,
                        "equipment_type": equipment.equipment_type,
                        "code": equipment.code,
                        "is_active": equipment.is_active,
                    },
                    details="Initial equipment created during system bootstrap.",
                )

        db.commit()

        return True