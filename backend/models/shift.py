from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


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

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OPEN",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )