"""Insurance policies the family keeps track of (health, life, ...), each with its renewal date."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InsurancePolicy(Base):
    __tablename__ = "insurance_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = mapped_column(String(36), ForeignKey("families.id", ondelete="CASCADE"), index=True)
    # Whose cover it is; empty for a family policy.
    care_profile_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("care_profiles.id", ondelete="SET NULL"), nullable=True
    )
    policy_type: Mapped[str] = mapped_column(String(32))  # health | life | accident | critical_illness | ...
    insurer: Mapped[str] = mapped_column(String(120))
    plan_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    policy_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sum_insured: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    premium: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    premium_frequency: Mapped[str] = mapped_column(String(16), default="yearly")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    renewal_date: Mapped[date] = mapped_column(Date)
    last_renewed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    agent_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    helpline: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The family member who pays / renews it.
    responsible_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
