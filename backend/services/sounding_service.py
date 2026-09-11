from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.attachment import Attachment
from backend.models.shift import Shift
from backend.models.sounding import Sounding
from backend.models.vessel import Vessel
from backend.services.audit_service import AuditService
from backend.utils.time import now_ist


class SoundingService:
    MAX_SOUNDINGS_PER_SHIFT = 5

    @staticmethod
    def get_deadline(report_date: date) -> datetime:
        """
        Soundings for a shift/date are due by 06:00 UTC on the
        following calendar day.
        """
        next_day = report_date + timedelta(days=1)
        return datetime.combine(
            next_day,
            time(6, 0),
        )

    @staticmethod
    def create_sounding(
        db: Session,
        shift_id: int,
        attachment_id: int,
        submitted_by_user_id: int,
    ) -> Sounding:
        """
        Create a sounding against a specific OPEN shift.

        A shift may contain a maximum of 5 soundings.
        """

        # Lock the shift row so two simultaneous uploads cannot
        # both pass the maximum-count check.
        shift = db.scalar(
            select(Shift)
            .where(Shift.id == shift_id)
            .with_for_update()
        )

        if shift is None:
            raise ValueError("Shift not found.")

        if shift.status != "OPEN":
            raise ValueError(
                "Sounding can only be submitted for an open shift."
            )

        sounding_count = db.scalar(
            select(func.count(Sounding.id))
            .where(Sounding.shift_id == shift.id)
        ) or 0

        if sounding_count >= SoundingService.MAX_SOUNDINGS_PER_SHIFT:
            raise ValueError(
                f"A shift can have a maximum of "
                f"{SoundingService.MAX_SOUNDINGS_PER_SHIFT} soundings."
            )

        attachment = db.get(Attachment, attachment_id)

        if attachment is None:
            raise ValueError("Attachment not found.")

        allowed_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
        }

        if attachment.content_type not in allowed_types:
            raise ValueError(
                "Sounding attachment must be a JPEG, PNG, or WebP image."
            )

        submitted_at = now_ist()

        sounding = Sounding(
            shift_id=shift.id,
            vessel_id=shift.vessel_id,
            report_date=shift.shift_date,
            attachment_id=attachment.id,
            submitted_at=submitted_at,
            submitted_by_user_id=submitted_by_user_id,
        )

        db.add(sounding)
        db.flush()

        AuditService.log(
            db=db,
            user_id=submitted_by_user_id,
            action="CREATE_SOUNDING",
            entity="soundings",
            entity_id=sounding.id,
            old_values=None,
            new_values={
                "shift_id": shift_id,
                "vessel_id": sounding.vessel_id,
                "report_date": sounding.report_date.isoformat(),
                "attachment_id": sounding.attachment_id,
                "submitted_at": sounding.submitted_at.isoformat(),
            },
            details="Shift sounding created.",
        )

        return sounding

    @staticmethod
    def list_soundings(
        db: Session,
        shift_id: int,
    ) -> list[Sounding]:
        """
        List all soundings belonging to one shift.
        """
        return list(
            db.scalars(
                select(Sounding)
                .where(Sounding.shift_id == shift_id)
                .order_by(Sounding.created_at.asc())
            ).all()
        )

    @staticmethod
    def get_status(
        report_date: date,
        soundings: list[Sounding],
        now: datetime | None = None,
    ) -> str:
        """
        Determine sounding compliance status for a shift.

        SUBMITTED:
            At least one sounding exists.

        LATE:
            No sounding existed before the deadline, but one exists now.

        DUE:
            Deadline has not passed and no sounding exists.

        MISSING:
            Deadline has passed and no sounding exists.
        """

        if soundings:
            deadline = SoundingService.get_deadline(report_date)

            if soundings[0].submitted_at > deadline:
                return "LATE"

            return "SUBMITTED"

        current_time = now or now_ist()
        deadline = SoundingService.get_deadline(report_date)

        if current_time >= deadline:
            return "MISSING"

        return "DUE"

    @staticmethod
    def get_shift_status(
        db: Session,
        shift_id: int,
        now: datetime | None = None,
    ) -> dict:
        """
        Return sounding status for a specific shift.
        """

        shift = db.get(Shift, shift_id)

        if shift is None:
            raise ValueError("Shift not found.")

        soundings = SoundingService.list_soundings(
            db=db,
            shift_id=shift.id,
        )

        deadline = SoundingService.get_deadline(
            shift.shift_date
        )

        status = SoundingService.get_status(
            report_date=shift.shift_date,
            soundings=soundings,
            now=now,
        )

        return {
            "shift_id": shift.id,
            "vessel_id": shift.vessel_id,
            "report_date": shift.shift_date,
            "shift_name": shift.shift_name,
            "status": status,
            "deadline": deadline,
            "sounding_count": len(soundings),
        }

    @staticmethod
    def get_all_vessel_statuses(
        db: Session,
        report_date: date,
    ) -> list[dict]:
        """
        Compatibility method for the existing dashboard.

        The old implementation returned one sounding status per vessel.
        Soundings are now shift-specific, so this returns one status
        for every shift belonging to an active vessel on the date.
        """

        shifts = list(
            db.scalars(
                select(Shift)
                .join(Vessel, Vessel.id == Shift.vessel_id)
                .where(
                    Shift.shift_date == report_date,
                    Vessel.is_active.is_(True),
                )
                .order_by(
                    Shift.vessel_id.asc(),
                    Shift.shift_name.asc(),
                    Shift.id.asc(),
                )
            ).all()
        )

        results = []

        for shift in shifts:
            soundings = SoundingService.list_soundings(
                db=db,
                shift_id=shift.id,
            )

            deadline = SoundingService.get_deadline(
                shift.shift_date
            )

            status = SoundingService.get_status(
                report_date=shift.shift_date,
                soundings=soundings,
            )

            vessel = db.get(Vessel, shift.vessel_id)

            results.append(
                {
                    "shift_id": shift.id,
                    "vessel_id": shift.vessel_id,
                    "vessel_name": (
                        vessel.name
                        if vessel is not None
                        else f"Vessel {shift.vessel_id}"
                    ),
                    "report_date": shift.shift_date,
                    "shift_name": shift.shift_name,
                    "status": status,
                    "deadline": deadline,
                    "sounding_count": len(soundings),
                }
            )

        return results

    @staticmethod
    def get_compliance(
        db: Session,
        report_date: date,
    ) -> dict:
        """
        Calculate sounding compliance by shift.

        Each shift is one expected sounding requirement.
        """

        shifts = list(
            db.scalars(
                select(Shift).where(
                    Shift.shift_date == report_date
                )
            ).all()
        )

        expected = len(shifts)
        submitted = 0
        late = 0
        missing = 0
        due = 0

        for shift in shifts:
            soundings = SoundingService.list_soundings(
                db=db,
                shift_id=shift.id,
            )

            status = SoundingService.get_status(
                report_date=shift.shift_date,
                soundings=soundings,
            )

            if status == "SUBMITTED":
                submitted += 1
            elif status == "LATE":
                late += 1
            elif status == "MISSING":
                missing += 1
            elif status == "DUE":
                due += 1

        compliance_percentage = (
            ((submitted + late) / expected) * 100
            if expected
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