"""A record of each one-off family message the app sends for a care profile: the weekly summary
("weekly", keyed by the week's last day) and each early warning ("warn:<kind>", keyed by its week).
The unique key stops two workers, or two runs, from sending the same message twice."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CareAlertSent(Base):
    __tablename__ = "care_alerts_sent"
    __table_args__ = (UniqueConstraint("care_profile_id", "kind", "period", name="uq_care_alert_once"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    care_profile_id: Mapped[str] = mapped_column(String(36), ForeignKey("care_profiles.id"))
    kind: Mapped[str] = mapped_column(String(40))
    period: Mapped[str] = mapped_column(String(20))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
