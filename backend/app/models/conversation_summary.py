import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConversationSummary(Base):
    """A summary of one finished part of a parent's chat (messages from_seq..to_seq of a check-in)."""

    __tablename__ = "conversation_summaries"
    __table_args__ = (UniqueConstraint("checkin_id", "from_seq", name="uq_conversation_summary_part"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    checkin_id: Mapped[str] = mapped_column(String(36), ForeignKey("health_checkins.id"), index=True)
    from_seq: Mapped[int] = mapped_column(Integer)
    to_seq: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    # Important points found: [{"title", "detail", "priority"}]; each became a task for caretakers and managers.
    important: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # gemini, or rules when Gemini is not configured or failed.
    source: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
