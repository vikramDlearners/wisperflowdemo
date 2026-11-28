"""One row per parent per local day for the "I'm fine" button: when it was pressed, when the app asked the
parent because it was not pressed by 11, and when the family was told it was still not pressed."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


class DailyFine(Base):
    __tablename__ = "daily_fine"
    __table_args__ = (UniqueConstraint("care_profile_id", "day", name="uq_daily_fine_profile_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id"))
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    day: Mapped[date] = mapped_column(Date)
    fine_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    family_told_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
