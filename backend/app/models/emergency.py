import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Emergency(Base):
    """An emergency the parent raised, by what they said in the chat or with the emergency button."""

    __tablename__ = "emergencies"
    __table_args__ = (Index("ix_emergencies_family_status", "family_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id", ondelete="CASCADE"))
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id", ondelete="CASCADE"))
    checkin_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("health_checkins.id", ondelete="CASCADE"), nullable=True)
    reported_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16))  # "chat" or "button"
    status: Mapped[str] = mapped_column(String(16), default="open")  # "open" or "completed"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
