import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    scheduled_date: Mapped[date] = mapped_column(Date)
    # Stored as "HH:MM" text, matching the frontend Appointment type.
    start_time: Mapped[str] = mapped_column(String(8))
    provider: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str] = mapped_column(Text, default="")
    # Allowed values: scheduled, completed, cancelled, rescheduled.
    status: Mapped[str] = mapped_column(String(16), default="scheduled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
