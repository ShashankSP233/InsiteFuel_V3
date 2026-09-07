from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.production import ProductionRecord
from backend.models.project import Project
from backend.models.shift import Shift
from backend.models.vessel import Vessel
from backend.services.audit_service import AuditService


class ProductionService:

    @staticmethod
    def create_production(
        db: Session,
        *,
        project_id: int,
        vessel_id: int,
        shift_id: int,
        production_date,
        as_per_qty: Decimal,
        true_qty: Decimal,
        fuel_rate: Decimal | None,
        created_by_user_id: int,
        remarks: str | None = None,
    ) -> ProductionRecord:

        if as_per_qty < 0:
            raise ValueError(
                "as_per_qty cannot be negative."
            )

        if true_qty < 0:
            raise ValueError(
                "true_qty cannot be negative."
            )

        if fuel_rate is not None and fuel_rate < 0:
            raise ValueError(
                "fuel_rate cannot be negative."
            )

        project = db.get(Project, project_id)

        if project is None:
            raise ValueError(
                "Project not found."
            )

        vessel = db.get(Vessel, vessel_id)

        if vessel is None:
            raise ValueError(
                "Vessel not found."
            )

        if not vessel.is_active:
            raise ValueError(
                "Vessel is inactive."
            )

        shift = db.get(Shift, shift_id)

        if shift is None:
            raise ValueError(
                "Shift not found."
            )

        if shift.vessel_id != vessel_id:
            raise ValueError(
                "Shift does not belong to the selected vessel."
            )

        if shift.shift_date != production_date:
            raise ValueError(
                "Production date must match the shift date."
            )

        if vessel.project_id != project_id:
            raise ValueError(
                "Vessel does not belong to the selected project."
            )

        production = ProductionRecord(
            project_id=project_id,
            vessel_id=vessel_id,
            shift_id=shift_id,
            production_date=production_date,
            as_per_qty=as_per_qty,
            true_qty=true_qty,
            fuel_rate=fuel_rate,
            remarks=remarks,
            created_by_user_id=created_by_user_id,
        )

        db.add(production)
        db.flush()

        AuditService.log(
            db=db,
            user_id=created_by_user_id,
            action="CREATE_PRODUCTION_RECORD",
            entity="ProductionRecord",
            entity_id=production.id,
            new_values={
                "project_id": project_id,
                "vessel_id": vessel_id,
                "shift_id": shift_id,
                "production_date": production_date.isoformat(),
                "as_per_qty": str(as_per_qty),
                "true_qty": str(true_qty),
                "fuel_rate": (
                    str(fuel_rate)
                    if fuel_rate is not None
                    else None
                ),
                "remarks": remarks,
            },
            details="Production record created.",
        )

        return production

    @staticmethod
    def get_production(
        db: Session,
        production_id: int,
    ) -> ProductionRecord | None:

        return db.get(
            ProductionRecord,
            production_id,
        )

    @staticmethod
    def list_production(
        db: Session,
        *,
        production_date=None,
        vessel_id: int | None = None,
        project_id: int | None = None,
        shift_id: int | None = None,
    ) -> list[ProductionRecord]:

        stmt = select(
            ProductionRecord
        ).order_by(
            ProductionRecord.production_date.desc(),
            ProductionRecord.id.desc(),
        )

        if production_date is not None:
            stmt = stmt.where(
                ProductionRecord.production_date
                == production_date
            )

        if vessel_id is not None:
            stmt = stmt.where(
                ProductionRecord.vessel_id
                == vessel_id
            )

        if project_id is not None:
            stmt = stmt.where(
                ProductionRecord.project_id
                == project_id
            )

        if shift_id is not None:
            stmt = stmt.where(
                ProductionRecord.shift_id
                == shift_id
            )

        return list(
            db.scalars(stmt).all()
        )

    @staticmethod
    def calculate_metrics(
        production: ProductionRecord,
    ) -> dict:

        as_per_qty = Decimal(
            str(production.as_per_qty)
        )

        true_qty = Decimal(
            str(production.true_qty)
        )

        quantity_variance = (
            true_qty - as_per_qty
        ).quantize(
            Decimal("0.001")
        )

        achievement_percentage = None

        if as_per_qty > 0:
            achievement_percentage = (
                true_qty
                / as_per_qty
                * Decimal("100")
            ).quantize(
                Decimal("0.01")
            )

        return {
            "quantity_variance": quantity_variance,
            "achievement_percentage": achievement_percentage,
        }
