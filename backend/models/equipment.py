from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base
from backend.utils.time import now_ist


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = (
        UniqueConstraint(
            "vessel_id",
            "iot_engine_name",
            name="uq_equipment_vessel_iot_engine_name",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    vessel_id: Mapped[int] = mapped_column(
        ForeignKey("vessels.id"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    equipment_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
    )

    # The engine's name in the IoT vendor's payloads ("Port", "Starboard DG", ...).
    iot_engine_name: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_ist,
    )