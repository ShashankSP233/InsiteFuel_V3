"""
IoT shift-data ingestion.

Flow for one payload (one vessel, one 12-hour window):

1. Parse / validate (``iot_parser``).  Problems => payload stored as REJECTED.
2. Same content already processed => DUPLICATE, nothing happens.
3. Map the vendor ``vesselId`` and engine names onto our vessel / equipment.
4. Assign the payload to MORNING or EVENING on the reporting window's start
   date, then create/populate it through normal ``FuelService`` chain rules;
   mark it ``source = IOT`` and set
   ``auto_close_at``.  The vessel's first shift is always created manually.
5. Post engine runs as engine events (+ ledger consumption) and, optionally,
   refills / drains as ledger entries, all through the existing services so
   every ledger and audit rule still applies.
6. Everything above happens in ONE transaction.  If any step fails, the whole
   thing is rolled back and only the REJECTED inbox row is kept.

``IotService.close_due_shifts`` is the auto-close sweep: it closes IoT shifts
whose ``auto_close_at`` has passed and that nobody closed manually.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.equipment import Equipment
from backend.models.fuel import AdjustmentDirection, FuelTransactionType
from backend.models.iot import IotPayload, IotPayloadStatus
from backend.models.shift import Shift
from backend.models.user import User, UserRole
from backend.models.vessel import Vessel
from backend.services.audit_service import AuditService
from backend.services.auth_service import hash_password
from backend.services.engine_service import EngineService
from backend.services.fuel_service import FuelService
from backend.services.iot_parser import ParsedWindow, parse_payload
from backend.utils.time import now_ist

logger = logging.getLogger(__name__)

DUPLICATE = "DUPLICATE"
PROCESSED = IotPayloadStatus.PROCESSED
REJECTED = IotPayloadStatus.REJECTED
AWAITING_MAPPING = IotPayloadStatus.AWAITING_MAPPING

# ROB reported by the sensors vs. our ledger: only mention it above this.
ROB_VARIANCE_WARN_LITRES = Decimal("1")
_Q3 = Decimal("0.001")
# Gap between consecutive windows above which we warn about a missing window.
MAX_WINDOW_GAP = timedelta(minutes=30)


def naive_ist(value: datetime) -> datetime:
    """Compare datetimes safely whether the database returned them aware or naive."""
    return value.replace(tzinfo=None)


class IotRejection(ValueError):
    """The payload cannot be applied; ``errors`` explains why."""

    def __init__(self, errors: list[str] | str):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


@dataclass
class IngestOutcome:
    status: str  # PROCESSED | REJECTED | DUPLICATE
    payload_id: int | None = None
    shift_id: int | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    result: dict | None = None
    internal_error: bool = False


class IotService:
    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def payload_hash(raw) -> str:
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def get_service_user(db: Session) -> User:
        """The system account that owns every IoT-created record."""
        user = db.scalar(select(User).where(User.username == settings.iot_service_username))
        if user is None:
            user = User(
                username=settings.iot_service_username,
                # Random, never shown to anyone: this account cannot be logged into.
                password_hash=hash_password(secrets.token_urlsafe(48)),
                role=UserRole.OPERATOR.value,
                full_name="IoT Integration (system)",
                is_active=True,
            )
            db.add(user)
            db.flush()
        return user

    # ------------------------------------------------------------------
    # ingest
    # ------------------------------------------------------------------
    @staticmethod
    def ingest(
        db: Session,
        raw,
        *,
        existing: IotPayload | None = None,
    ) -> IngestOutcome:
        """
        Process one payload.  Owns the transaction (commits on success, rolls
        back and records a REJECTED inbox row on failure).

        ``existing`` is a previously REJECTED inbox row being re-run.
        """
        digest = IotService.payload_hash(raw)
        parsed = parse_payload(raw)

        already = db.scalar(
            select(IotPayload).where(
                IotPayload.payload_hash == digest,
                IotPayload.status == PROCESSED,
            )
        )
        if already is not None:
            warning = "This exact payload was already processed; nothing was changed."
            if existing is not None:
                row = existing
                row.status = DUPLICATE
                row.vessel_id = already.vessel_id
                row.shift_id = already.shift_id
                row.errors = None
                row.warnings = [warning]
                row.result = already.result
                row.processed_at = now_ist()
            else:
                row = IotPayload(
                    external_vessel_id=already.external_vessel_id,
                    vessel_id=already.vessel_id,
                    shift_id=already.shift_id,
                    window_start=already.window_start,
                    window_end=already.window_end,
                    shift_date=already.shift_date,
                    shift_name=already.shift_name,
                    payload_hash=digest,
                    raw_payload=raw,
                    status=DUPLICATE,
                    warnings=[warning],
                    result=already.result,
                    processed_at=now_ist(),
                )
                db.add(row)
            db.commit()
            return IngestOutcome(status=DUPLICATE, payload_id=row.id, shift_id=already.shift_id,
                                 warnings=list(row.warnings), result=already.result)

        if parsed.errors:
            return IotService._store_rejected(db, raw, digest, parsed, parsed.errors, existing)

        mapping_errors = IotService._mapping_errors(db, parsed)
        if mapping_errors:
            return IotService._store_pending_mapping(db, raw, digest, parsed, mapping_errors, existing)

        try:
            outcome = IotService._process(db, raw, digest, parsed, existing)
            db.commit()
            return outcome
        except ValueError as exc:  # includes IotRejection and service-layer rule violations
            db.rollback()
            errors = exc.errors if isinstance(exc, IotRejection) else [str(exc)]
            return IotService._store_rejected(db, raw, digest, parsed, errors, existing)
        except Exception:  # noqa: BLE001 - never lose a vendor payload
            logger.exception("Unexpected error while processing IoT payload")
            db.rollback()
            outcome = IotService._store_rejected(
                db, raw, digest, parsed,
                ["Unexpected server error while processing; see the server log."],
                existing,
            )
            outcome.internal_error = True
            return outcome

    @staticmethod
    def _store_rejected(
        db: Session,
        raw,
        digest: str,
        parsed: ParsedWindow,
        errors: list[str],
        existing: IotPayload | None,
    ) -> IngestOutcome:
        vessel = None
        if parsed.external_vessel_id:
            vessel = db.scalar(
                select(Vessel).where(Vessel.iot_vessel_id == parsed.external_vessel_id)
            )
        row = existing if existing is not None else IotPayload()
        row.external_vessel_id = parsed.external_vessel_id
        row.vessel_id = vessel.id if vessel else None
        row.shift_id = None
        row.window_start, row.window_end = parsed.window_start, parsed.window_end
        row.shift_date, row.shift_name = None, None
        row.payload_hash = digest
        row.raw_payload = raw
        row.status = REJECTED
        row.errors = errors
        row.warnings = parsed.warnings
        row.result = None
        row.processed_at = now_ist()
        if existing is None:
            db.add(row)
        db.commit()
        return IngestOutcome(
            status=REJECTED,
            payload_id=row.id,
            errors=list(errors),
            warnings=list(parsed.warnings),
        )

    @staticmethod
    def _mapping_errors(db: Session, parsed: ParsedWindow) -> list[str]:
        vessel = db.scalar(select(Vessel).where(Vessel.iot_vessel_id == parsed.external_vessel_id))
        if vessel is None:
            return [f"No vessel is mapped to IoT vesselId '{parsed.external_vessel_id}'" +
                    (f" ({parsed.vessel_name})" if parsed.vessel_name else "") + "."]
        equipment_names = {
            (eq.iot_engine_name or "").strip().lower()
            for eq in db.scalars(select(Equipment).where(
                Equipment.vessel_id == vessel.id,
                Equipment.is_active.is_(True),
                Equipment.iot_engine_name.is_not(None),
            )).all()
        }
        measured_names = sorted({r.engine for r in parsed.runs if r.fuel_litres is not None and r.fuel_litres > 0
                                 and r.engine.strip().lower() not in equipment_names})
        if measured_names:
            return [f"Map vendor engine name(s) to active equipment on '{vessel.name}': {', '.join(measured_names)}."]
        return []

    @staticmethod
    def refresh_mapping_status(db: Session) -> None:
        """Apply validated queued payloads in window order after mappings are completed."""
        rows = db.scalars(select(IotPayload).where(IotPayload.status == AWAITING_MAPPING)).all()
        for row in rows:
            parsed = parse_payload(row.raw_payload)
            if not parsed.errors and not IotService._mapping_errors(db, parsed):
                row.status = IotPayloadStatus.READY
                row.errors = None
        db.commit()

        IotService.process_ready_payloads(db)

    @staticmethod
    def process_ready_payloads(db: Session) -> list[IngestOutcome]:
        """Apply READY payloads in window order, stopping if one needs correction."""

        ready_rows = db.scalars(
            select(IotPayload)
            .where(IotPayload.status == IotPayloadStatus.READY)
            .order_by(IotPayload.window_start, IotPayload.id)
        ).all()
        outcomes = []
        for row in ready_rows:
            outcome = IotService.ingest(db, row.raw_payload, existing=row)
            outcomes.append(outcome)
            if outcome.status not in (PROCESSED, DUPLICATE):
                break
        return outcomes

    @staticmethod
    def _store_pending_mapping(db: Session, raw, digest: str, parsed: ParsedWindow,
                               errors: list[str], existing: IotPayload | None) -> IngestOutcome:
        vessel = db.scalar(select(Vessel).where(Vessel.iot_vessel_id == parsed.external_vessel_id)) if parsed.external_vessel_id else None
        row = existing if existing is not None else IotPayload()
        row.external_vessel_id = parsed.external_vessel_id
        row.vessel_id = vessel.id if vessel else None
        row.shift_id = None
        row.window_start, row.window_end = parsed.window_start, parsed.window_end
        row.shift_date = row.shift_name = None
        row.payload_hash = digest
        row.raw_payload = raw
        row.status = AWAITING_MAPPING
        row.errors = errors
        row.warnings = parsed.warnings
        row.result = None
        row.processed_at = None
        if existing is None:
            db.add(row)
        db.commit()
        return IngestOutcome(status=AWAITING_MAPPING, payload_id=row.id, errors=list(errors), warnings=list(parsed.warnings))

    @staticmethod
    def _process(
        db: Session,
        raw,
        digest: str,
        parsed: ParsedWindow,
        existing: IotPayload | None,
    ) -> IngestOutcome:
        # -- vessel ------------------------------------------------------
        vessel = db.scalar(
            select(Vessel).where(Vessel.iot_vessel_id == parsed.external_vessel_id)
        )
        if vessel is None:
            raise IotRejection(
                f"No vessel is mapped to IoT vesselId '{parsed.external_vessel_id}'"
                + (f" ({parsed.vessel_name})" if parsed.vessel_name else "")
                + ". An administrator must set the vessel's IoT id first."
            )
        if not vessel.is_active:
            raise IotRejection(f"Vessel '{vessel.name}' is not active.")

        # Serialise everything for this vessel from here on.
        FuelService.lock_vessels(db, [vessel.id])

        # -- same window already ingested with different content ----------
        conflicting = db.scalar(
            select(IotPayload).where(
                IotPayload.vessel_id == vessel.id,
                IotPayload.window_start == parsed.window_start,
                IotPayload.window_end == parsed.window_end,
                IotPayload.status == PROCESSED,
                IotPayload.payload_hash != digest,
            )
        )
        if conflicting is not None:
            raise IotRejection(
                f"Data for this vessel and window was already ingested (payload "
                f"#{conflicting.id}) with different content. Correct the shift with the "
                "admin editing tools instead of re-sending."
            )

        # -- engine mapping ----------------------------------------------
        equipment_by_name = {
            eq.iot_engine_name.strip().lower(): eq
            for eq in db.scalars(
                select(Equipment).where(
                    Equipment.vessel_id == vessel.id,
                    Equipment.is_active.is_(True),
                    Equipment.iot_engine_name.is_not(None),
                )
            ).all()
        }
        measured = [r for r in parsed.runs if r.fuel_litres is not None and r.fuel_litres > 0]
        skipped = [r for r in parsed.runs if r not in measured]
        unmapped = sorted({r.engine for r in measured if r.engine.lower() not in equipment_by_name})
        if unmapped:
            raise IotRejection(
                f"No active equipment on '{vessel.name}' is mapped to IoT engine name(s): "
                f"{', '.join(unmapped)}. An administrator must set the equipment's IoT engine name."
            )

        warnings = list(parsed.warnings)
        if skipped:
            engines = ", ".join(sorted({r.engine for r in skipped}))
            warnings.append(
                f"{len(skipped)} run(s) had no measured fuel (N/A or 0) and were not "
                f"recorded as engine events (engines: {engines})."
            )

        user = IotService.get_service_user(db)

        # -- windows must arrive in order -----------------------------------
        last = db.scalar(
            select(IotPayload)
            .where(
                IotPayload.vessel_id == vessel.id,
                IotPayload.status == PROCESSED,
                IotPayload.window_end.is_not(None),
            )
            .order_by(IotPayload.window_start.desc(), IotPayload.id.desc())
            .limit(1)
        )
        if last is not None:
            if naive_ist(parsed.window_start) <= naive_ist(last.window_start):
                raise IotRejection(
                    f"This window starts at or before the last ingested window "
                    f"(payload #{last.id}, {last.window_start:%Y-%m-%d %H:%M}). "
                    "Windows must arrive oldest first."
                )
            processed_for_last_date = db.scalars(
                select(IotPayload)
                .where(
                    IotPayload.vessel_id == vessel.id,
                    IotPayload.status == PROCESSED,
                    IotPayload.window_end.is_not(None),
                )
                .order_by(IotPayload.window_start, IotPayload.id)
            ).all()
            same_day = [
                row for row in processed_for_last_date
                if naive_ist(row.window_start).date() == naive_ist(last.window_start).date()
            ]
            expected_last_name = "MORNING" if same_day and same_day[0].id == last.id else "EVENING"
            if (last.shift_date, last.shift_name) != (last.window_start.date(), expected_last_name):
                raise IotRejection(
                    f"Previously processed payload #{last.id} was applied to "
                    f"{last.shift_date} {last.shift_name}, but its reporting window belongs to "
                    f"{last.window_start.date()} {expected_last_name}. Correct that earlier shift "
                    "before applying later payloads so the fuel balance is carried forward correctly."
                )
            gap = naive_ist(parsed.window_start) - naive_ist(last.window_end)
            if gap > MAX_WINDOW_GAP:
                warnings.append(
                    f"There is a gap of {gap} since the previous ingested window; "
                    "a window may be missing."
                )

        # -- target the shift represented by this reporting window --------------
        # For each vessel and reporting date, the earliest window is MORNING
        # and the next later window is EVENING, independent of clock time.
        shift_date = parsed.window_start.date()
        processed_for_date = db.scalars(
            select(IotPayload)
            .where(
                IotPayload.vessel_id == vessel.id,
                IotPayload.status == PROCESSED,
                IotPayload.window_end.is_not(None),
            )
            .order_by(IotPayload.window_start, IotPayload.id)
        ).all()
        same_day = [
            row for row in processed_for_date
            if naive_ist(row.window_start).date() == shift_date
        ]
        if len(same_day) >= 2:
            raise IotRejection(
                f"Two reporting windows have already been applied for {shift_date}. "
                "Only one MORNING and one EVENING window are supported per vessel per date."
            )
        shift_name = "MORNING" if not same_day else "EVENING"
        IotService._close_superseded_iot_shifts(db, vessel, shift_date, shift_name, user)

        target_shift = db.scalar(
            select(Shift).where(
                Shift.vessel_id == vessel.id,
                Shift.shift_date == shift_date,
                Shift.shift_name == shift_name,
            )
        )
        if target_shift is not None and target_shift.source != "IOT":
            raise IotRejection(
                f"A manually managed {shift_name} shift already exists for {shift_date}. "
                "The IoT payload was not applied to the manual shift."
            )

        received_at = now_ist()
        shift = FuelService.get_or_create_shift(
            db,
            vessel_id=vessel.id,
            shift_date=shift_date,
            shift_name=shift_name,
            created_by_user_id=user.id,
        )
        shift.source = "IOT"
        # The vendor's dredging metrics have no agreed calculation yet. Keep
        # IoT-created shifts explicit and neutral until that is defined.
        shift.advancement_m = Decimal("0")
        shift.dredging_hours = Decimal("0")
        shift.auto_close_at = received_at + timedelta(hours=settings.iot_shift_auto_close_hours)

        # -- inbox row (needs an id to reference from the ledger) ----------
        row = existing if existing is not None else IotPayload()
        row.external_vessel_id = parsed.external_vessel_id
        row.vessel_id = vessel.id
        row.shift_id = shift.id
        row.window_start, row.window_end = parsed.window_start, parsed.window_end
        row.shift_date, row.shift_name = shift.shift_date, shift.shift_name
        row.payload_hash = digest
        row.raw_payload = raw
        row.status = PROCESSED
        row.errors = None
        if existing is None:
            row.received_at = received_at
            db.add(row)
        db.flush()

        # -- engine runs -> engine events + ledger consumption -------------
        for run in sorted(measured, key=lambda r: (r.start, r.engine)):
            equipment = equipment_by_name[run.engine.lower()]
            fuel = run.fuel_litres.quantize(_Q3)
            EngineService.create_engine_event(
                db,
                equipment_id=equipment.id,
                shift_id=shift.id,
                start_time=run.start,
                stop_time=run.stop,
                lph_rate=(run.fuel_litres / run.hours).quantize(_Q3),
                created_by_user_id=user.id,
                consumption=fuel,
                remarks=f"[IoT] {run.engine} (payload #{row.id})",
            )

        # -- refills / drains -> ledger ------------------------------------
        refills = drains = 0
        if settings.iot_post_refills_to_ledger:
            for stock in parsed.stock:
                if stock.refill > 0:
                    FuelService.add_transaction(
                        db,
                        vessel_id=vessel.id,
                        shift_date=shift.shift_date,
                        shift_name=shift.shift_name,
                        transaction_type=FuelTransactionType.RECEIPT,
                        quantity=stock.refill.quantize(_Q3),
                        created_by_user_id=user.id,
                        reference_type="IOT_PAYLOAD",
                        reference_id=row.id,
                        remarks=f"[IoT] refill reported for {stock.engine}",
                        fuel_source="IoT sensor refill",
                    )
                    refills += 1
                if stock.drain > 0:
                    FuelService.add_transaction(
                        db,
                        vessel_id=vessel.id,
                        shift_date=shift.shift_date,
                        shift_name=shift.shift_name,
                        transaction_type=FuelTransactionType.ADJUSTMENT,
                        quantity=stock.drain.quantize(_Q3),
                        created_by_user_id=user.id,
                        adjustment_direction=AdjustmentDirection.OUT,
                        reference_type="IOT_PAYLOAD",
                        reference_id=row.id,
                        remarks=f"[IoT] drain reported for {stock.engine}",
                    )
                    drains += 1

        # -- reconcile with the sensors' reported stock ---------------------
        FuelService.recalculate_shift(db, shift.id)
        closing = Decimal(str(shift.calculated_closing_fuel))
        iot_rob = sum((s.rob for s in parsed.stock), Decimal(0))
        variance = iot_rob - closing
        if parsed.stock and abs(variance) > ROB_VARIANCE_WARN_LITRES:
            warnings.append(
                f"IoT reported total ROB {iot_rob} L but the ledger closing fuel is "
                f"{closing} L (difference {variance} L). Nothing was adjusted automatically."
            )

        result = {
            "shift_id": shift.id,
            "shift_date": shift.shift_date.isoformat(),
            "shift_name": shift.shift_name,
            "engine_events_created": len(measured),
            "runs_without_fuel_skipped": len(skipped),
            "refills_posted": refills,
            "drains_posted": drains,
            "calculated_closing_fuel": str(closing),
            "iot_reported_rob_total": str(iot_rob) if parsed.stock else None,
            "rob_variance": str(variance) if parsed.stock else None,
            "auto_close_at": shift.auto_close_at.isoformat(),
        }
        row.warnings = warnings
        row.result = result
        row.processed_at = now_ist()

        AuditService.log(
            db=db,
            user_id=user.id,
            action="INGEST_IOT_PAYLOAD",
            entity="iot_payloads",
            entity_id=row.id,
            old_values=None,
            new_values=result,
            details="Shift created and populated from IoT vendor data.",
        )
        return IngestOutcome(
            status=PROCESSED,
            payload_id=row.id,
            shift_id=shift.id,
            warnings=warnings,
            result=result,
        )

    @staticmethod
    @staticmethod
    def _close_superseded_iot_shifts(
        db: Session, vessel: Vessel, shift_date: date, shift_name: str, user: User
    ) -> None:
        """
        The new window has arrived, so an earlier IoT shift that is still open
        is over: close it (the shift chain forbids a new shift while an earlier
        one is open).  An earlier shift a person created is never closed for
        them.
        """
        earlier = [Shift.shift_date < shift_date]
        if shift_name == "EVENING":
            earlier.append(
                and_(Shift.shift_date == shift_date, Shift.shift_name == "MORNING")
            )
        open_earlier = db.scalars(
            select(Shift)
            .where(Shift.vessel_id == vessel.id, or_(*earlier), Shift.status == "OPEN")
            .order_by(
                Shift.shift_date,
                case((Shift.shift_name == "EVENING", 1), else_=0),
                Shift.id,
            )
        ).all()
        for older in open_earlier:
            if older.source != "IOT":
                raise IotRejection(
                    f"The earlier {older.shift_name} shift of {older.shift_date} is still open "
                    "and was created manually. Close it first, then re-process this payload."
                )
            FuelService.close_shift(
                db,
                older.id,
                closed_by_user_id=user.id,
                reason="Closed automatically: the next IoT reporting window arrived.",
                system_close=True,
            )

    # ------------------------------------------------------------------
    # auto-close sweep
    # ------------------------------------------------------------------
    @staticmethod
    def close_due_shifts(db: Session, now: datetime | None = None) -> dict:
        """
        Close every IoT shift whose ``auto_close_at`` has passed and that is
        still open.  Safe to run from several workers: ``close_shift`` locks the
        shift and is a no-op if it is already closed.
        """
        now = now or now_ist()
        due_ids = list(
            db.scalars(
                select(Shift.id)
                .where(
                    Shift.source == "IOT",
                    Shift.status == "OPEN",
                    Shift.auto_close_at.is_not(None),
                    Shift.auto_close_at <= now,
                )
                .order_by(Shift.auto_close_at, Shift.id)
            ).all()
        )
        closed: list[int] = []
        failed: list[dict] = []
        if not due_ids:
            return {"closed": closed, "failed": failed}

        user = IotService.get_service_user(db)
        db.commit()
        for shift_id in due_ids:
            try:
                FuelService.close_shift(
                    db,
                    shift_id,
                    closed_by_user_id=user.id,
                    reason=(
                        f"Closed automatically {settings.iot_shift_auto_close_hours} hours "
                        "after IoT data arrived."
                    ),
                    system_close=True,
                )
                db.commit()
                closed.append(shift_id)
            except ValueError as exc:
                db.rollback()
                failed.append({"shift_id": shift_id, "error": str(exc)})
                logger.warning("IoT auto-close of shift %s failed: %s", shift_id, exc)
        return {"closed": closed, "failed": failed}
