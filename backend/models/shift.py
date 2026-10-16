from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.utils.time import now_ist


class Shift(Base):
    __tablename__ = "shifts"
    __table_args__ = (
        UniqueConstraint(
            "vessel_id",
            "shift_date",
            "shift_name",
            name="uq_shifts_vessel_date_name",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)

    vessel_id: Mapped[int] = mapped_column(
        ForeignKey("vessels.id"),
        nullable=False,
        index=True,
    )

    shift_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    shift_name: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    opening_fuel: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )

    calculated_closing_fuel: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3),
        nullable=True,
    )

    advancement_m: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    dredging_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OPEN",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_ist,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Where the shift came from: "MANUAL" (created by a user) or "IOT"
    # (created from vendor data by the IoT ingestion API).
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MANUAL",
        server_default="MANUAL",
    )

    # IoT shifts only: when the scheduler should close the shift if nobody
    # has closed it manually first.  Cleared when the shift is reopened.
    auto_close_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # "MANUAL" or "AUTO_IOT"; NULL while the shift is open.
    close_source: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )