import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MealLog(Base):
    """What the parent said they ate, for one or more meals of a day (from the chatbot)."""

    __tablename__ = "meal_logs"
    __table_args__ = (Index("ix_meal_logs_profile_date", "care_profile_id", "log_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    checkin_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("health_checkins.id"), nullable=True)
    log_date: Mapped[date] = mapped_column(Date)
    # The meals this answer covers, comma separated: breakfast, lunch, dinner (e.g. "breakfast,lunch").
    meals: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    recorded_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
