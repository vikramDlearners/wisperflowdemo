"""Notes a parent saves for themselves ("Take my medicines at 6 pm", "Medicines are in the drawer"),
with an optional reminder for themselves or for another family member (who then also gets a task)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParentNote(Base):
    __tablename__ = "parent_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    # When to remind; null = just a note, no reminder.
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Who the note is for; null = the parent themselves. Anyone else also gets a task (task_id).
    remind_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    # For another person: also send them a reminder message at remind_at (otherwise only the task).
    send_reminder: Mapped[bool] = mapped_column(Boolean, default=False)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=True)
    # Set once the reminder went out (or was not needed), so it is sent only once.
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
