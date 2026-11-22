"""Dose log and what is due today for a care profile, in the profile's local time."""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.dose import MedicineDose
from app.models.medicine import Medicine
from app.services.adapters.intent import ALLOWED_DELAY_MINUTES
from app.services.reminders import list_reminder_times

ANY_SLOT = "any"
# A medicine with no reminder times is counted per part of the day: an answer in the evening marks only the
# "night" dose. "any" is kept for rows written before day parts existed.
MORNING, NOON, NIGHT = "morning", "noon", "night"
DAY_PARTS = (MORNING, NOON, NIGHT)
NO_TIME_SLOTS = (*DAY_PARTS, ANY_SLOT)
# A timed dose counts as the current one from this long before its time ("I took my 8 PM tablet" at 7:30 PM).
EARLY_WINDOW = timedelta(minutes=60)
# Answers the parent or the family can record. "missed" is written only by the missed-dose job (source "system");
# a later answer from the parent or the family replaces it.
STATUSES = frozenset({"taken", "not_taken", "skipped"})
SOURCES = frozenset({"chatbot", "manual"})
MISSED = "missed"
SYSTEM_SOURCE = "system"
_SLOT_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass
class DueDose:
    medicine_id: str
    name: str
    slot: str
    due_at: datetime | None
    status: str | None


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def local_now(profile: CareProfile, now: datetime | None = None) -> datetime:
    now = _aware(now) if now is not None else datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo(profile.timezone))


def today_for(profile: CareProfile, now: datetime) -> date:
    return local_now(profile, now).date()


def logged_today(db: Session, profile: CareProfile, now: datetime) -> dict[tuple[str, str], MedicineDose]:
    day = today_for(profile, now)
    rows = db.execute(
        select(MedicineDose).where(
            MedicineDose.care_profile_id == profile.id, MedicineDose.dose_date == day
        )
    ).scalars()
    return {(r.medicine_id, r.slot): r for r in rows}


def day_part(local: datetime) -> str:
    """morning before 12:00, noon (afternoon) until 17:00, night after that, in the profile's local time."""
    if local.hour < 12:
        return MORNING
    if local.hour < 17:
        return NOON
    return NIGHT


def no_time_slots(medicine_id: str, logged_keys, fallback: str) -> list[str]:
    """Slots shown for a medicine without reminder times: the day parts already answered, else one open slot.

    How many doses such a medicine needs is unknown, so nothing is shown as owed beyond one open slot.
    """
    answered = {slot for med_id, slot in logged_keys if med_id == medicine_id}
    slots = [s for s in NO_TIME_SLOTS if s in answered]
    return slots or [fallback]


def _active_medicines(db: Session, profile: CareProfile) -> list[Medicine]:
    return list(db.execute(
        select(Medicine)
        .where(Medicine.care_profile_id == profile.id, Medicine.active.is_(True))
        .order_by(Medicine.created_at, Medicine.id)
    ).scalars())


def _due_at(day: date, slot: str, tz: ZoneInfo) -> datetime | None:
    if not _SLOT_RE.match(slot):
        return None
    h, m = slot.split(":")
    return datetime.combine(day, time(int(h), int(m)), tzinfo=tz).astimezone(timezone.utc)


def doses_today(db: Session, profile: CareProfile, now: datetime) -> list[DueDose]:
    """Today's dose slots for display: reminder times, or for a medicine without times the day parts answered
    so far ("any" when none is)."""
    now = _aware(now)
    local = local_now(profile, now)
    day = local.date()
    tz = ZoneInfo(profile.timezone)
    logged = logged_today(db, profile, now)
    out: list[DueDose] = []
    for med in _active_medicines(db, profile):
        times = list_reminder_times(db, med.id)
        for slot in times or no_time_slots(med.id, logged, ANY_SLOT):
            row = logged.get((med.id, slot))
            out.append(DueDose(med.id, med.display_name, slot, _due_at(day, slot, tz), row.status if row else None))
    return out


_ANSWERED = ("taken", "skipped")


def current_doses(db: Session, profile: CareProfile, now: datetime, volunteered: bool = False) -> list[DueDose]:
    """The one dose per medicine that an answer right now is about.

    A timed medicine: its latest reminder time that is due (or due within EARLY_WINDOW); earlier unanswered
    times stay unanswered (the missed-dose alert covers them). A medicine without times: the current day part.
    Doses already taken or skipped are left out, and so is a dose whose remind-later time has not come yet.
    When the bot asks on its own (volunteered=False), a medicine without times that was already taken earlier
    today is not asked about again; when the parent says they took something, its current day part is offered.
    """
    now = _aware(now)
    local = local_now(profile, now)
    day = local.date()
    tz = ZoneInfo(profile.timezone)
    logged = logged_today(db, profile, now)
    out: list[DueDose] = []
    for med in _active_medicines(db, profile):
        times = list_reminder_times(db, med.id)
        if times:
            due = [(t, _due_at(day, t, tz)) for t in times]
            started = [(t, at) for t, at in due if at is not None and at <= now + EARLY_WINDOW]
            if not started:
                continue
            slot, due_at = max(started, key=lambda pair: pair[1])
        else:
            if not volunteered and any(
                logged.get((med.id, s)) is not None and logged[(med.id, s)].status in _ANSWERED
                for s in NO_TIME_SLOTS
            ):
                continue
            slot, due_at = day_part(local), None
        row = logged.get((med.id, slot))
        if row is not None and row.status in _ANSWERED:
            continue
        if not volunteered and row is not None and row.remind_at is not None and _aware(row.remind_at) > now:
            continue
        out.append(DueDose(med.id, med.display_name, slot, due_at, row.status if row else None))
    return out


def due_untaken(db: Session, profile: CareProfile, now: datetime) -> list[DueDose]:
    now = _aware(now)
    logged = logged_today(db, profile, now)
    out = []
    for d in doses_today(db, profile, now):
        if d.status == "taken":
            continue
        if d.due_at is not None and d.due_at > now:
            continue
        row = logged.get((d.medicine_id, d.slot))
        if row is not None and row.remind_at is not None and _aware(row.remind_at) > now:
            continue
        out.append(d)
    return out


def _validate_slot(slot: str) -> None:
    if slot not in NO_TIME_SLOTS and not _SLOT_RE.match(slot or ""):
        raise ValueError("slot must be HH:MM, a day part (morning, noon, night) or 'any'")


def _validate_medicine(db: Session, profile: CareProfile, medicine_id: str) -> None:
    med = db.get(Medicine, medicine_id)
    if med is None or med.care_profile_id != profile.id or not med.active:
        raise ValueError("Medicine is not an active medicine of this care profile")


def _existing(db: Session, medicine_id: str, day: date, slot: str) -> MedicineDose | None:
    return db.execute(
        select(MedicineDose).where(
            MedicineDose.medicine_id == medicine_id,
            MedicineDose.dose_date == day,
            MedicineDose.slot == slot,
        )
    ).scalar_one_or_none()


def record_dose(
    db: Session,
    profile: CareProfile,
    medicine_id: str,
    slot: str,
    status: str,
    actor_id: str | None,
    source: str,
    now: datetime,
) -> MedicineDose:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {sorted(STATUSES)}")
    if source not in SOURCES:
        raise ValueError(f"source must be one of {sorted(SOURCES)}")
    _validate_slot(slot)
    _validate_medicine(db, profile, medicine_id)
    now = _aware(now)
    day = today_for(profile, now)

    def apply(row: MedicineDose) -> None:
        row.status = status
        row.recorded_at = now
        row.recorded_by_user_id = actor_id
        row.source = source
        row.remind_at = None

    row = _existing(db, medicine_id, day, slot)
    if row is None:
        row = MedicineDose(
            family_id=profile.family_id, care_profile_id=profile.id, medicine_id=medicine_id,
            dose_date=day, slot=slot,
        )
        apply(row)
        # Flush the caller's pending work first, so the savepoint below only ever undoes this one insert.
        db.flush()
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            # Another request recorded this slot first: answer it by updating that row instead. Only the
            # savepoint is rolled back; the caller's turn (messages, urgent flag, notifications) is kept.
            row = _existing(db, medicine_id, day, slot)
            if row is None:
                raise
            apply(row)
    else:
        apply(row)
    db.commit()
    db.refresh(row)
    return row


def set_remind_later(
    db: Session, profile: CareProfile, medicine_id: str, slot: str, minutes: int, now: datetime
) -> MedicineDose:
    if minutes not in ALLOWED_DELAY_MINUTES:
        raise ValueError(f"Delay must be one of {sorted(ALLOWED_DELAY_MINUTES)} minutes")
    _validate_slot(slot)
    _validate_medicine(db, profile, medicine_id)
    now = _aware(now)
    day = today_for(profile, now)
    row = _existing(db, medicine_id, day, slot)
    if row is None:
        row = MedicineDose(
            family_id=profile.family_id, care_profile_id=profile.id, medicine_id=medicine_id,
            dose_date=day, slot=slot, status="not_taken", recorded_at=now, source="chatbot",
        )
        db.add(row)
    row.remind_at = now + timedelta(minutes=minutes)
    db.commit()
    db.refresh(row)
    return row
