"""The daily "I'm fine" button.

The parent taps it once a day and the family hears that all is well. If it is not tapped by 11:00 local time,
the app asks the parent first. Only if the parent still has not tapped it 30 minutes later is the family
told, in the app and by email. Each send is claimed with a conditional UPDATE so two workers never repeat it.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.daily_fine import DailyFine
from app.services import family_alerts
from app.services.doses import _aware, local_now
from app.services.notifications import notify
from app.services.parent_context import ParentContext

logger = logging.getLogger(__name__)

ASK_AT = time(11, 0)
GRACE = timedelta(minutes=30)


@dataclass
class FineStatus:
    day: date
    fine_at: datetime | None
    asked: bool
    family_told: bool


def _row(db: Session, profile: CareProfile, day: date) -> DailyFine:
    row = db.execute(
        select(DailyFine).where(DailyFine.care_profile_id == profile.id, DailyFine.day == day)
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = DailyFine(family_id=profile.family_id, care_profile_id=profile.id, day=day)
    try:
        with db.begin_nested():
            db.add(row)
    except IntegrityError:
        return db.execute(
            select(DailyFine).where(DailyFine.care_profile_id == profile.id, DailyFine.day == day)
        ).scalar_one()
    return row


def status(db: Session, ctx: ParentContext, now: datetime) -> FineStatus:
    day = local_now(ctx.profile, now).date()
    row = db.execute(
        select(DailyFine).where(DailyFine.care_profile_id == ctx.profile.id, DailyFine.day == day)
    ).scalar_one_or_none()
    if row is None:
        return FineStatus(day, None, False, False)
    return FineStatus(day, row.fine_at, row.asked_at is not None and row.fine_at is None,
                      row.family_told_at is not None)


def press_fine(db: Session, ctx: ParentContext, now: datetime) -> FineStatus:
    """The parent tapped "I'm fine". The first tap of the day tells the family; later taps change nothing."""
    now = _aware(now)
    row = _row(db, ctx.profile, local_now(ctx.profile, now).date())
    claimed = db.execute(
        update(DailyFine).where(DailyFine.id == row.id, DailyFine.fine_at.is_(None)).values(fine_at=now)
    ).rowcount == 1
    if claimed:
        late = row.family_told_at is not None
        for user in family_alerts.other_members(db, ctx):
            notify(db, user.id, "checkin.fine", family_id=ctx.family_id,
                   payload={"care_profile_id": ctx.profile.id, "parent_name": ctx.profile.display_name,
                            "after_alert": late})
    db.commit()
    db.refresh(row)
    return status(db, ctx, now)


def nudge_fine_checkins(db: Session, now: datetime) -> int:
    """Scheduler job: ask parents who have not tapped by 11:00, then tell the family after the grace period.
    Returns how many asks and family alerts it sent."""
    now = _aware(now)
    sent = 0
    profiles = db.execute(
        select(CareProfile).where(CareProfile.linked_user_id.is_not(None)).order_by(CareProfile.id)
    ).scalars().all()
    for profile in profiles:
        try:
            sent += _nudge_one(db, profile, now)
            db.commit()
        except Exception:  # noqa: BLE001 - one bad profile must not block the rest
            db.rollback()
            logger.exception("I'm fine check failed for care profile %s", profile.id)
    return sent


def _nudge_one(db: Session, profile: CareProfile, now: datetime) -> int:
    local = local_now(profile, now)
    if local.time() < ASK_AT:
        return 0
    row = _row(db, profile, local.date())
    if row.fine_at is not None:
        return 0
    if row.asked_at is None:
        asked = db.execute(
            update(DailyFine).where(DailyFine.id == row.id, DailyFine.asked_at.is_(None)).values(asked_at=now)
        ).rowcount == 1
        if asked:
            notify(db, profile.linked_user_id, "checkin.fine_ask", family_id=profile.family_id,
                   payload={"care_profile_id": profile.id, "parent_name": profile.display_name})
        return int(asked)
    if row.family_told_at is not None or now < _aware(row.asked_at) + GRACE:
        return 0
    told = db.execute(
        update(DailyFine)
        .where(DailyFine.id == row.id, DailyFine.family_told_at.is_(None), DailyFine.fine_at.is_(None))
        .values(family_told_at=now)
    ).rowcount == 1
    if not told:
        return 0
    users = family_alerts._members_except(db, profile.family_id, profile.linked_user_id)
    for user in users:
        notify(db, user.id, "checkin.fine_missed", family_id=profile.family_id,
               payload={"care_profile_id": profile.id, "parent_name": profile.display_name})
    db.commit()
    family_alerts._email(
        users, f"{profile.display_name} has not tapped \"I'm fine\" today",
        f"{profile.display_name} has not tapped \"I'm fine\" today, and did not answer when CareCircle asked at "
        f"11:00. You may want to call to check on them.",
    )
    return 1
