from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Integer
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.utils.time import now_ist


class FuelTransactionType(str, Enum):
    RECEIPT = "RECEIPT"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    ENGINE_CONSUMPTION = "ENGINE_CONSUMPTION"
    ADJUSTMENT = "ADJUSTMENT"

class AdjustmentDirection(str, Enum):
    IN = "IN"
    OUT = "OUT"

class FuelTransaction(Base):
    __tablename__ = "fuel_transactions"

    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="ck_fuel_transactions_quantity_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    shift_id: Mapped[int] = mapped_column(
        ForeignKey("shifts.id"),
        nullable=False,
        index=True,
    )

    vessel_id: Mapped[int] = mapped_column(
        ForeignKey("vessels.id"),
        nullable=False,
        index=True,
    )
    source_vessel_id: Mapped[int | None] = mapped_column(
        ForeignKey("vessels.id"),
        nullable=True,
        index=True,
    )
    
    fuel_source: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    transaction_type: Mapped[FuelTransactionType] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )

    adjustment_direction: Mapped[AdjustmentDirection | None] = mapped_column(
        String(10),
        nullable=True,
    )

    reference_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    reference_id: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_ist,
        index=True,
    )

    remarks: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_ist,
    )