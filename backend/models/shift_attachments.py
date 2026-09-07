from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class ShiftAttachment(Base):
    __tablename__ = "shift_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    shift_id: Mapped[int] = mapped_column(
        ForeignKey("shifts.id"),
        nullable=False,
        index=True,
    )

    attachment_id: Mapped[int] = mapped_column(
        ForeignKey("attachments.id"),
        nullable=False,
        index=True,
    )

    attachment_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )