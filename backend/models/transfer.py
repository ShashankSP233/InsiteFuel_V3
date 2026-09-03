from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class TransferStatus(str, Enum):
    INITIATED = "INITIATED"
    RECEIVING_CONFIRMED = "RECEIVING_CONFIRMED"
    MANAGER_REVIEW = "MANAGER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    BALANCES_UPDATED = "BALANCES_UPDATED"


class FuelTransfer(Base):
    __tablename__ = "transfers"

    __table_args__ = (
        CheckConstraint(
            "from_vessel_id <> to_vessel_id",
            name="ck_transfers_different_vessels",
        ),
        CheckConstraint(
            "initiated_quantity > 0",
            name="ck_transfers_initiated_quantity_positive",
        ),
        CheckConstraint(
            "received_quantity IS NULL OR received_quantity >= 0",
            name="ck_transfers_received_quantity_nonnegative",
        ),
        CheckConstraint(
            "loss_quantity IS NULL OR loss_quantity >= 0",
            name="ck_transfers_loss_quantity_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    from_vessel_id: Mapped[int] = mapped_column(
        ForeignKey("vessels.id"),
        nullable=False,
        index=True,
    )

    to_vessel_id: Mapped[int] = mapped_column(
        ForeignKey("vessels.id"),
        nullable=False,
        index=True,
    )

    initiated_quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        nullable=False,
    )

    received_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3),
        nullable=True,
    )

    loss_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3),
        nullable=True,
    )

    status: Mapped[TransferStatus] = mapped_column(
        String(30),
        nullable=False,
        default=TransferStatus.INITIATED,
        index=True,
    )

    transfer_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    initiated_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    received_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    manager_remark: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )