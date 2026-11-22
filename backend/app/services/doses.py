"""Dose log and what is due today for a care profile, in the profile's local time."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.dose import MedicineDose
from app.models.medicine import Medicine
from app.services.adapters.intent import ALLOWED_DELAY_MINUTES
from app.services.reminders import list_reminder_times

ANY_SLOT = "any"


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


def doses_today(db: Session, profile: CareProfile, now: datetime) -> list[DueDose]:
    now = _aware(now)
    day = today_for(profile, now)
    tz = ZoneInfo(profile.timezone)
    logged = logged_today(db, profile, now)
    medicines = db.execute(
        select(Medicine)
        .where(Medicine.care_profile_id == profile.id, Medicine.active.is_(True))
        .order_by(Medicine.created_at, Medicine.id)
    ).scalars()
    out: list[DueDose] = []
    for med in medicines:
        for slot in list_reminder_times(db, med.id) or [ANY_SLOT]:
            due_at = None
            if slot != ANY_SLOT:
                h, m = slot.split(":")
                due_at = datetime.combine(day, time(int(h), int(m)), tzinfo=tz).astimezone(timezone.utc)
            row = logged.get((med.id, slot))
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
    now = _aware(now)
    day = today_for(profile, now)
    row = _existing(db, medicine_id, day, slot)
    if row is None:
        row = MedicineDose(
            family_id=profile.family_id, care_profile_id=profile.id, medicine_id=medicine_id,
            dose_date=day, slot=slot,
        )
        db.add(row)
    row.status = status
    row.recorded_at = now
    row.recorded_by_user_id = actor_id
    row.source = source
    row.remind_at = None
    db.commit()
    db.refresh(row)
    return row


def set_remind_later(
    db: Session, profile: CareProfile, medicine_id: str, slot: str, minutes: int, now: datetime
) -> MedicineDose:
    if minutes not in ALLOWED_DELAY_MINUTES:
        raise ValueError(f"Delay must be one of {sorted(ALLOWED_DELAY_MINUTES)} minutes")
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
