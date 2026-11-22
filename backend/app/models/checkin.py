import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HealthCheckin(Base):
    """One parent check-in conversation per care profile per local day."""

    __tablename__ = "health_checkins"
    __table_args__ = (
        UniqueConstraint("care_profile_id", "checkin_date", name="uq_health_checkin_profile_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    parent_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    checkin_date: Mapped[date] = mapped_column(Date)
    # Allowed values: greet, health, medicines, appointments, done.
    step: Mapped[str] = mapped_column(String(16), default="greet")
    health_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    summary_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The medicine the bot last asked about by name ("Did you take X?"), so the next answer applies to it.
    pending_medicine_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # Sequence number of the first message of the conversation on screen now: each time the parent opens
    # the chat a new one starts (earlier messages stay stored but are not shown).
    session_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_checkin_id", "checkin_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    checkin_id: Mapped[str] = mapped_column(String(36), ForeignKey("health_checkins.id"))
    # Allowed values: bot, parent.
    sender: Mapped[str] = mapped_column(String(8))
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Position in the check-in's conversation (1, 2, 3, ...): the display order on every database.
    seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
