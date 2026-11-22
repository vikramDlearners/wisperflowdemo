import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MedicineDose(Base):
    __tablename__ = "medicine_doses"
    __table_args__ = (
        UniqueConstraint("medicine_id", "dose_date", "slot", name="uq_medicine_dose_slot"),
        Index("ix_medicine_doses_profile_date", "care_profile_id", "dose_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    medicine_id: Mapped[str] = mapped_column(String(36), ForeignKey("medicines.id"))
    dose_date: Mapped[date] = mapped_column(Date)
    # "HH:MM" or "any".
    slot: Mapped[str] = mapped_column(String(8))
    # Allowed values: taken, not_taken, skipped, missed ("missed" only from the missed-dose job).
    status: Mapped[str] = mapped_column(String(16))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    recorded_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    # Allowed values: chatbot, manual, system (the missed-dose job).
    source: Mapped[str] = mapped_column(String(16))
    remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    family_alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
