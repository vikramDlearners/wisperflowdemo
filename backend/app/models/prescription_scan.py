import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PrescriptionScan(Base):
    __tablename__ = "prescription_scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    uploaded_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    # 'prescription' | 'invoice' | 'other'
    document_type: Mapped[str] = mapped_column(String(32))
    # 'pending_review' | 'confirmed' | 'rejected'
    status: Mapped[str] = mapped_column(String(32))
    proposed: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class MedicineReminder(Base):
    __tablename__ = "medicine_reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    medicine_id: Mapped[str] = mapped_column(String(36), ForeignKey("medicines.id"))
    # 24-hour "HH:MM"
    time_of_day: Mapped[str] = mapped_column(String(5))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
