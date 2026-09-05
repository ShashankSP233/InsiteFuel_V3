from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Sounding(Base):
    __tablename__ = "soundings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    vessel_id: Mapped[int] = mapped_column(
        ForeignKey("vessels.id"),
        nullable=False,
        index=True,
    )

    report_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )

    attachment_id: Mapped[int] = mapped_column(
        ForeignKey("attachments.id"),
        nullable=False,
        index=True,
    )

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    submitted_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )