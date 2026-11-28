"""Insurance policies and their renewals.

Seeing them needs reports.view (everyone in the family by default); adding, changing, renewing or deleting
needs reports.upload (managers and caregivers), like the family's other records.
"""

import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.insurance import InsurancePolicy
from app.models.membership import FamilyMember
from app.services.activity import log_activity
from app.services.errors import NotFound
from app.services.permissions import require

FREQUENCY_MONTHS = {"yearly": 12, "half_yearly": 6, "quarterly": 3, "monthly": 1}
FIELDS = (
    "care_profile_id", "policy_type", "insurer", "plan_name", "policy_number", "sum_insured", "premium",
    "premium_frequency", "start_date", "renewal_date", "agent_name", "agent_phone", "helpline", "notes",
    "responsible_user_id",
)


def next_renewal(current: date, frequency: str) -> date:
    """The renewal date one premium period later (31 Jan + 1 month = 28/29 Feb)."""
    months = FREQUENCY_MONTHS.get(frequency, 12)
    month = current.month - 1 + months
    year = current.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(current.day, calendar.monthrange(year, month)[1]))


def _clean(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _check(db: Session, family_id: str, values: dict) -> None:
    cp = values.get("care_profile_id")
    if cp:
        profile = db.get(CareProfile, cp)
        if profile is None or profile.family_id != family_id:
            raise ValueError("Pick a parent from this family")
    uid = values.get("responsible_user_id")
    if uid:
        member = db.execute(
            select(FamilyMember.id).where(
                FamilyMember.family_id == family_id, FamilyMember.user_id == uid, FamilyMember.status == "active"
            )
        ).first()
        if member is None:
            raise ValueError("The responsible person must be an active member of this family")


def _policy(db: Session, family_id: str, policy_id: str) -> InsurancePolicy:
    policy = db.get(InsurancePolicy, policy_id)
    if policy is None or policy.family_id != family_id:
        raise NotFound("Insurance policy not found")
    return policy


def list_policies(db: Session, actor_id: str, family_id: str) -> list[InsurancePolicy]:
    """Soonest renewal first."""
    require(db, actor_id, family_id, "reports.view")
    return list(
        db.execute(
            select(InsurancePolicy)
            .where(InsurancePolicy.family_id == family_id)
            .order_by(InsurancePolicy.renewal_date, InsurancePolicy.insurer)
        ).scalars()
    )


def get_policy(db: Session, actor_id: str, family_id: str, policy_id: str) -> InsurancePolicy:
    require(db, actor_id, family_id, "reports.view")
    return _policy(db, family_id, policy_id)


def create_policy(db: Session, actor_id: str, family_id: str, values: dict) -> InsurancePolicy:
    require(db, actor_id, family_id, "reports.upload")
    values = {k: _clean(values.get(k)) for k in FIELDS}
    _check(db, family_id, values)
    policy = InsurancePolicy(family_id=family_id, **{k: v for k, v in values.items() if v is not None})
    db.add(policy)
    db.flush()
    log_activity(db, family_id, actor_id, "insurance.added", "insurance", policy.id,
                 {"insurer": policy.insurer, "renewal_date": policy.renewal_date.isoformat()})
    db.commit()
    return policy


def update_policy(db: Session, actor_id: str, family_id: str, policy_id: str, changes: dict) -> InsurancePolicy:
    require(db, actor_id, family_id, "reports.upload")
    policy = _policy(db, family_id, policy_id)
    changes = {k: _clean(v) for k, v in changes.items() if k in FIELDS}
    for required in ("policy_type", "insurer", "renewal_date", "premium_frequency"):
        if required in changes and changes[required] is None:
            raise ValueError(f"{required} cannot be empty")
    _check(db, family_id, changes)
    for key, value in changes.items():
        setattr(policy, key, value)
    log_activity(db, family_id, actor_id, "insurance.updated", "insurance", policy.id, {"fields": sorted(changes)})
    db.commit()
    return policy


def renew_policy(
    db: Session, actor_id: str, family_id: str, policy_id: str,
    renewal_date: date | None = None, premium=None, today: date | None = None,
) -> InsurancePolicy:
    """Paid: the next renewal date is one premium period later (or the date the insurer gave)."""
    require(db, actor_id, family_id, "reports.upload")
    policy = _policy(db, family_id, policy_id)
    previous = policy.renewal_date
    policy.renewal_date = renewal_date or next_renewal(previous, policy.premium_frequency)
    if premium is not None:
        policy.premium = premium
    policy.last_renewed_on = today or date.today()
    log_activity(db, family_id, actor_id, "insurance.renewed", "insurance", policy.id,
                 {"insurer": policy.insurer, "from": previous.isoformat(), "to": policy.renewal_date.isoformat()})
    db.commit()
    return policy


def delete_policy(db: Session, actor_id: str, family_id: str, policy_id: str) -> None:
    require(db, actor_id, family_id, "reports.upload")
    policy = _policy(db, family_id, policy_id)
    log_activity(db, family_id, actor_id, "insurance.deleted", "insurance", policy.id, {"insurer": policy.insurer})
    db.delete(policy)
    db.commit()
