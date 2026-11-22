"""Meals the parent tells the chatbot about: which meals are due to ask about now, and saving the answer.

Morning asks about breakfast, the afternoon about lunch, the night about dinner. Earlier meals of the day that
were not answered are asked about together with the current one ("breakfast, lunch and dinner" at night when
nothing was answered all day).
"""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.meal import MealLog
from app.services.doses import MORNING, NIGHT, NOON, day_part, local_now

BREAKFAST, LUNCH, DINNER = "breakfast", "lunch", "dinner"
MEALS = (BREAKFAST, LUNCH, DINNER)
# The meals that have happened by each part of the day.
_MEALS_BY_PART = {MORNING: (BREAKFAST,), NOON: (BREAKFAST, LUNCH), NIGHT: (BREAKFAST, LUNCH, DINNER)}


def meals_on(db: Session, care_profile_id: str, day: date) -> list[MealLog]:
    return list(db.execute(
        select(MealLog)
        .where(MealLog.care_profile_id == care_profile_id, MealLog.log_date == day)
        .order_by(MealLog.recorded_at, MealLog.id)
    ).scalars())


def answered_meals(db: Session, profile: CareProfile, now: datetime) -> set[str]:
    day = local_now(profile, now).date()
    return {m for row in meals_on(db, profile.id, day) for m in row.meals.split(",") if m}


def meals_due(db: Session, profile: CareProfile, now: datetime) -> list[str]:
    """The day's meals so far that the parent has not told us about yet, in day order."""
    eaten_by_now = _MEALS_BY_PART[day_part(local_now(profile, now))]
    answered = answered_meals(db, profile, now)
    return [m for m in eaten_by_now if m not in answered]


def save_meals(
    db: Session, profile: CareProfile, meals: list[str], text: str, user_id: str | None,
    now: datetime, checkin_id: str | None = None,
) -> MealLog:
    """Stage one answer covering `meals`. The caller commits."""
    row = MealLog(
        family_id=profile.family_id, care_profile_id=profile.id, checkin_id=checkin_id,
        log_date=local_now(profile, now).date(), meals=",".join(meals), text=text.strip(),
        recorded_at=now, recorded_by_user_id=user_id,
    )
    db.add(row)
    return row
