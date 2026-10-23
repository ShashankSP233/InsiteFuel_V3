from sqlalchemy import create_engine, event, or_, select, union_all
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, with_loader_criteria

from backend.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


@event.listens_for(Session, "do_orm_execute")
def restrict_project_scoped_queries(execute_state):
    """Apply project access rules to ORM reads and bulk writes for authenticated sessions."""
    if not execute_state.is_orm_statement:
        return
    project_ids = execute_state.session.info.get("project_scope_ids")
    user_id = execute_state.session.info.get("project_scope_user_id")
    if project_ids is None:
        return

    from backend.models.attachment import Attachment
    from backend.models.engine import EngineEvent
    from backend.models.equipment import Equipment
    from backend.models.fuel import FuelTransaction
    from backend.models.production import ProductionRecord
    from backend.models.project import Project
    from backend.models.shift import Shift
    from backend.models.shift_attachments import ShiftAttachment
    from backend.models.site import Site
    from backend.models.sounding import Sounding
    from backend.models.transfer import FuelTransfer
    from backend.models.issue import FuelIssue
    from backend.models.transfer_attachment import TransferAttachment
    from backend.models.vessel import Vessel

    vessel_ids = select(Vessel.id).where(Vessel.project_id.in_(project_ids))
    shift_ids = select(Shift.id).where(Shift.vessel_id.in_(vessel_ids))
    equipment_ids = select(Equipment.id).where(Equipment.vessel_id.in_(vessel_ids))
    transfer_ids = select(FuelTransfer.id).where(
        FuelTransfer.from_vessel_id.in_(vessel_ids),
        FuelTransfer.to_vessel_id.in_(vessel_ids),
    )
    attachment_ids = union_all(
        select(ShiftAttachment.attachment_id).where(ShiftAttachment.shift_id.in_(shift_ids)),
        select(Sounding.attachment_id).where(Sounding.vessel_id.in_(vessel_ids)),
        select(TransferAttachment.attachment_id).where(TransferAttachment.transfer_id.in_(transfer_ids)),
    )
    all_attachment_ids = union_all(
        select(ShiftAttachment.attachment_id),
        select(Sounding.attachment_id),
        select(TransferAttachment.attachment_id),
    )

    statement = execute_state.statement
    statement = statement.options(
        with_loader_criteria(Project, Project.id.in_(project_ids), include_aliases=True),
        with_loader_criteria(Site, Site.project_id.in_(project_ids), include_aliases=True),
        with_loader_criteria(Vessel, Vessel.project_id.in_(project_ids), include_aliases=True),
        with_loader_criteria(Equipment, Equipment.vessel_id.in_(vessel_ids), include_aliases=True),
        with_loader_criteria(Shift, Shift.vessel_id.in_(vessel_ids), include_aliases=True),
        with_loader_criteria(Sounding, Sounding.vessel_id.in_(vessel_ids), include_aliases=True),
        with_loader_criteria(
            FuelTransaction,
            (FuelTransaction.vessel_id.in_(vessel_ids))
            & or_(
                FuelTransaction.source_vessel_id.is_(None),
                FuelTransaction.source_vessel_id.in_(vessel_ids),
            ),
            include_aliases=True,
        ),
        with_loader_criteria(
            EngineEvent,
            EngineEvent.shift_id.in_(shift_ids) & EngineEvent.equipment_id.in_(equipment_ids),
            include_aliases=True,
        ),
        with_loader_criteria(
            FuelTransfer,
            FuelTransfer.from_vessel_id.in_(vessel_ids)
            & FuelTransfer.to_vessel_id.in_(vessel_ids),
            include_aliases=True,
        ),
        with_loader_criteria(
            FuelIssue,
            FuelIssue.shift_id.in_(shift_ids),
            include_aliases=True,
        ),
        with_loader_criteria(
            ProductionRecord,
            ProductionRecord.project_id.in_(project_ids)
            & ProductionRecord.vessel_id.in_(vessel_ids),
            include_aliases=True,
        ),
        with_loader_criteria(ShiftAttachment, ShiftAttachment.shift_id.in_(shift_ids), include_aliases=True),
        with_loader_criteria(TransferAttachment, TransferAttachment.transfer_id.in_(transfer_ids), include_aliases=True),
        with_loader_criteria(
            Attachment,
            Attachment.id.in_(attachment_ids)
            | (
                (Attachment.uploaded_by_user_id == user_id)
                & Attachment.id.not_in(all_attachment_ids)
            ),
            include_aliases=True,
        ),
    )
    execute_state.statement = statement


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
