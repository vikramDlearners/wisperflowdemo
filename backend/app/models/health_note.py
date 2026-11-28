"""What the app knows about a parent's health: allergies, conditions and readings.

Notes come from the parent's chat ("My BP is high now", "I'm allergic to peanuts"), from uploaded records
(a prescription that names a diagnosis), or from the family. Allergies and conditions are kept once per
label; every reading is its own row, so they form a history.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

ALLERGY, CONDITION, READING = "allergy", "condition", "reading"
KINDS = (ALLERGY, CONDITION, READING)
SOURCES = ("chat", "upload", "family")


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class HealthNote(Base):
    __tablename__ = "health_notes"
    __table_args__ = (Index("ix_health_notes_profile_kind", "care_profile_id", "kind", "recorded_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    # allergy, condition or reading
    kind: Mapped[str] = mapped_column(String(16))
    # Allergy: what to avoid ("peanuts"). Condition: "BP", "Diabetes", ... Reading: bp, sugar, weight or pulse.
    label: Mapped[str] = mapped_column(String(120))
    # Reading: "140/90", "180", "high" or "low". Condition: an optional detail ("high"). Allergy: none.
    value: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Reading numbers for graphs: systolic or the single value in value_num, diastolic in value_num2.
    value_num: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_num2: Mapped[float | None] = mapped_column(Float, nullable=True)
    # chat, upload or family
    source: Mapped[str] = mapped_column(String(16))
    # The words the note was read from, so the family can see why it is there.
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # False once someone removed it (an allergy that turned out wrong); kept for the history.
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    recorded_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
