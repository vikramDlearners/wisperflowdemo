"""A parent's "yes, ask them to order it" for a medicine that is running low. It keeps the task it made, and
stops the app asking again until the family records a new tablet count."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RefillRequest(Base):
    __tablename__ = "refill_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    medicine_id: Mapped[str] = mapped_column(String(36), ForeignKey("medicines.id"), index=True)
    tablets_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    asked_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
