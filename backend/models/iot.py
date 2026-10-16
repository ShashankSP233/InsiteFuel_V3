from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.utils.time import now_ist


class IotPayloadStatus:
    PROCESSED = "PROCESSED"
    AWAITING_MAPPING = "AWAITING_MAPPING"
    READY = "READY"
    DUPLICATE = "DUPLICATE"
    REJECTED = "REJECTED"


class IotPayload(Base):
    """
    Inbox of every payload received from the IoT vendor.

    The raw JSON is always stored first, so nothing the vendor sends is lost
    even when it is rejected (unknown vessel, bad data, ...).  A rejected
    payload can be re-run with the reprocess endpoint once the cause is fixed.
    """

    __tablename__ = "iot_payloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    external_vessel_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    vessel_id: Mapped[int | None] = mapped_column(
        ForeignKey("vessels.id"), nullable=True, index=True
    )
    shift_id: Mapped[int | None] = mapped_column(
        ForeignKey("shifts.id"), nullable=True, index=True
    )

    window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shift_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shift_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_payload: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    errors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=now_ist
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
