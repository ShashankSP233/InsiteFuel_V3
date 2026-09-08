from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal
from backend.database import Base
from backend.utils.time import now_ist


class Vessel(Base):
    __tablename__ = "vessels"

    id: Mapped[int] = mapped_column(primary_key=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_ist,
    )

    fuel_threshold_litres: Mapped[Decimal] = mapped_column(
        Numeric(12, 3),
        nullable=False,
        default=Decimal("0"),
    )