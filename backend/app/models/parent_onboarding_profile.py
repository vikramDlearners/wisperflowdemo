import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


class ParentOnboardingProfile(Base):
    """Per-user onboarding details for a parent. Not family-scoped (see CareProfile)."""

    __tablename__ = "parent_onboarding_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=True
    )
    # Set for a parent with no linked account yet; points at that parent's care profile.
    care_profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("care_profiles.id"), nullable=True
    )

    # Section: parent
    parent_full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    preferred_name: Mapped[str | None] = mapped_column(String(60), nullable=True)
    relationship: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    approximate_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_picture_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Section: communication
    parent_mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Section: medical
    known_health_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_doctor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    doctor_contact_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    preferred_hospital: Mapped[str | None] = mapped_column(String(160), nullable=True)
    care_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    deficiencies: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Section: care
    caregiver_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    caregiver_relationship: Mapped[str | None] = mapped_column(String(60), nullable=True)
    caregiver_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    caregiver_email: Mapped[str | None] = mapped_column(String(254), nullable=True)

    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
