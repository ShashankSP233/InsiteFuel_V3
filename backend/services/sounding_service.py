from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.attachment import Attachment
from backend.models.sounding import Sounding
from backend.models.vessel import Vessel
from backend.services.audit_service import AuditService


SOUNDING_DEADLINE_HOUR = 6
SOUNDING_DEADLINE_MINUTE = 0

ALLOWED_SOUNDING_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


class SoundingService:

    @staticmethod
    def get_deadline(report_date: date) -> datetime:
        """
        Sounding for a report date is due by 06:00
        on the following calendar day.
        """
        deadline_date = report_date + timedelta(days=1)

        return datetime.combine(
            deadline_date,
            time(
                SOUNDING_DEADLINE_HOUR,
                SOUNDING_DEADLINE_MINUTE,
                tzinfo=timezone.utc,
            ),
        )

    @staticmethod
    def create_sounding(
        db: Session,
        *,
        vessel_id: int,
        report_date: date,
        attachment_id: int,
        submitted_by_user_id: int,
    ) -> Sounding:

        # ---------------------------------------------------------
        # Validate vessel
        # ---------------------------------------------------------
        vessel = db.get(Vessel, vessel_id)

        if vessel is None:
            raise ValueError("Vessel not found.")

        # ---------------------------------------------------------
        # Validate attachment
        # ---------------------------------------------------------
        attachment = db.get(Attachment, attachment_id)

        if attachment is None:
            raise ValueError("Attachment not found.")

        if attachment.content_type not in ALLOWED_SOUNDING_CONTENT_TYPES:
            raise ValueError(
                "Sounding attachment must be a JPEG, PNG, or WebP image."
            )

        # ---------------------------------------------------------
        # Create sounding
        # ---------------------------------------------------------
        submitted_at = datetime.now(timezone.utc)

        sounding = Sounding(
            vessel_id=vessel_id,
            report_date=report_date,
            attachment_id=attachment_id,
            submitted_at=submitted_at,
            submitted_by_user_id=submitted_by_user_id,
        )

        db.add(sounding)
        db.flush()

        # ---------------------------------------------------------
        # Audit
        # ---------------------------------------------------------
        AuditService.log(
            db,
            user_id=submitted_by_user_id,
            action="CREATE_SOUNDING",
            entity="Sounding",
            entity_id=sounding.id,
            new_values={
                "vessel_id": vessel_id,
                "report_date": report_date.isoformat(),
                "attachment_id": attachment_id,
                "submitted_at": submitted_at.isoformat(),
            },
        )

        return sounding

    @staticmethod
    def get_sounding(
        db: Session,
        sounding_id: int,
    ) -> Sounding | None:

        return db.get(Sounding, sounding_id)

    @staticmethod
    def list_soundings(
        db: Session,
        *,
        vessel_id: int,
        report_date: date | None = None,
    ) -> list[Sounding]:

        # Make sure the vessel exists.
        vessel = db.get(Vessel, vessel_id)

        if vessel is None:
            raise ValueError("Vessel not found.")

        stmt = select(Sounding).where(
            Sounding.vessel_id == vessel_id
        )

        if report_date is not None:
            stmt = stmt.where(
                Sounding.report_date == report_date
            )

        stmt = stmt.order_by(
            Sounding.submitted_at.desc()
        )

        return list(db.scalars(stmt).all())

    @staticmethod
    def get_status(
        *,
        report_date: date,
        soundings: list[Sounding],
        now: datetime | None = None,
    ) -> str:

        if now is None:
            now = datetime.now(timezone.utc)

        deadline = SoundingService.get_deadline(report_date)

        # No sounding submitted yet.
        if not soundings:
            if now <= deadline:
                return "DUE"

            return "MISSING"

        # At least one sounding exists.
        #
        # If any sounding was submitted by the deadline,
        # the requirement was satisfied on time.
        for sounding in soundings:
            if sounding.submitted_at <= deadline:
                return "SUBMITTED"

        # Soundings exist, but all were submitted after
        # the deadline.
        return "LATE"

    @staticmethod
    def get_all_vessel_statuses(
        db: Session,
        *,
        report_date: date,
        now: datetime | None = None,
    ) -> list[dict]:
        """
        Return sounding status for every active vessel
        for the specified report date.
        """

        if now is None:
            now = datetime.utcnow()

        vessels = list(
            db.scalars(
                select(Vessel)
                .where(Vessel.active.is_(True))
                .order_by(Vessel.name)
            ).all()
        )

        results = []

        for vessel in vessels:
            soundings = SoundingService.list_soundings(
                db=db,
                vessel_id=vessel.id,
                report_date=report_date,
            )

            status = SoundingService.get_status(
                report_date=report_date,
                soundings=soundings,
                now=now,
            )

            results.append(
                {
                    "vessel_id": vessel.id,
                    "vessel_name": vessel.name,
                    "report_date": report_date,
                    "status": status,
                    "deadline": SoundingService.get_deadline(report_date),
                    "sounding_count": len(soundings),
                }
            )

        return results


    @staticmethod
    def get_compliance(
        db: Session,
        *,
        report_date: date,
        now: datetime | None = None,
    ) -> dict:
        statuses = SoundingService.get_all_vessel_statuses(
            db=db,
            report_date=report_date,
            now=now,
        )

        expected = len(statuses)
        submitted = sum(
            1 for item in statuses
            if item["status"] == "SUBMITTED"
        )
        late = sum(
            1 for item in statuses
            if item["status"] == "LATE"
        )
        missing = sum(
            1 for item in statuses
            if item["status"] == "MISSING"
        )
        due = sum(
            1 for item in statuses
            if item["status"] == "DUE"
        )

        completed = submitted + late

        compliance_percentage = (
            (completed / expected) * 100
            if expected > 0
            else 100.0
        )

        return {
            "report_date": report_date,
            "expected": expected,
            "submitted": submitted,
            "late": late,
            "missing": missing,
            "due": due,
            "compliance_percentage": round(
                compliance_percentage,
                2,
            ),
        }