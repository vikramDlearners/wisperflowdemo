import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Medicine(Base):
    __tablename__ = "medicines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    display_name: Mapped[str] = mapped_column(String(255))
    instructions_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(120), nullable=True)
    quantity_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    refill_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Last day of the course; None means the medicine is ongoing.
    take_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsible_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    image_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prescription_scan_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("prescription_scans.id"), nullable=True
    )
    # The appointment at which the doctor gave this medicine.
    appointment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    total_medicine_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # Photo of the doctor's prescription, separate from the photo of the medicine (image_data).
    prescription_image_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, deferred=True)
    prescription_image_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
