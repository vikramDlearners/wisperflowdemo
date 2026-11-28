"""The family's weekly summary and early warnings.

`build_week` reads one care profile's last seven days: doses, check-ins, "I'm fine" taps, BP and sugar
readings, appointments and tasks. It also names patterns the family should know about early: the same
dose missed again and again, BP rising day after day, sugar high several times, and a parent who has
not used the app since yesterday.

Two jobs send them. `send_weekly_summaries` sends the week once, on Sunday evening in the parent's time
zone. `send_pattern_warnings` sends each kind of warning at most once a week. Both claim the send in
care_alerts_sent first, so two workers or two runs never repeat it. Sleep is not tracked anywhere, so the
summary does not mention it.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.care_alert import CareAlertSent
from app.models.care_profile import CareProfile
from app.models.checkin import ChatMessage, HealthCheckin
from app.models.daily_fine import DailyFine
from app.models.dose import MedicineDose
from app.models.health_note import HealthNote
from app.models.task import Task
from app.services import care_circle, family_alerts
from app.services.doses import _aware, local_now
from app.services.notifications import notify

logger = logging.getLogger(__name__)

SEND_DAY = 6  # Sunday
SEND_AT = time(19, 0)
MISSED_SLOT_LIMIT = 3
HIGH_SUGAR = 180
HIGH_SUGAR_LIMIT = 3
BP_RISE_DAYS = 3
BP_RISE_MMHG = 10
QUIET_FOR = timedelta(hours=24)


@dataclass
class Reading:
    day: date
    value: str


@dataclass
class Warning:
    kind: str
    text: str


@dataclass
class Week:
    start: date
    end: date
    taken: int = 0
    skipped: int = 0
    missed: int = 0
    missed_by_slot: dict[str, int] = field(default_factory=dict)
    checkin_days: int = 0
    fine_days: int = 0
    parent_messages: int = 0
    unwell_days: int = 0
    health_words: list[str] = field(default_factory=list)
    bp: list[Reading] = field(default_factory=list)
    sugar: list[Reading] = field(default_factory=list)
    visits_done: list[str] = field(default_factory=list)
    visits_next: list[str] = field(default_factory=list)
    tasks_done: int = 0
    tasks_open: int = 0
    warnings: list[Warning] = field(default_factory=list)


def _local_day(profile: CareProfile, dt: datetime) -> date:
    return local_now(profile, _aware(dt)).date()


def _doses(db: Session, profile: CareProfile, week: Week) -> None:
    rows = db.execute(
        select(MedicineDose.status, MedicineDose.slot).where(
            MedicineDose.care_profile_id == profile.id,
            MedicineDose.dose_date >= week.start,
            MedicineDose.dose_date <= week.end,
        )
    ).all()
    for status, slot in rows:
        if status == "taken":
            week.taken += 1
        elif status == "skipped":
            week.skipped += 1
        elif status in ("missed", "not_taken"):
            week.missed += 1
            week.missed_by_slot[slot] = week.missed_by_slot.get(slot, 0) + 1


def _checkins(db: Session, profile: CareProfile, week: Week) -> None:
    checkins = db.execute(
        select(HealthCheckin).where(
            HealthCheckin.care_profile_id == profile.id,
            HealthCheckin.checkin_date >= week.start,
            HealthCheckin.checkin_date <= week.end,
        ).order_by(HealthCheckin.checkin_date)
    ).scalars().all()
    ids = [c.id for c in checkins]
    spoke: set[str] = set()
    if ids:
        for checkin_id, count in db.execute(
            select(ChatMessage.checkin_id, func.count()).where(
                ChatMessage.checkin_id.in_(ids), ChatMessage.sender == "parent"
            ).group_by(ChatMessage.checkin_id)
        ):
            spoke.add(checkin_id)
            week.parent_messages += count
    week.checkin_days = len(spoke)
    week.unwell_days = sum(1 for c in checkins if c.urgent)
    if care_circle.shares_words(db, profile.id):
        week.health_words = [c.health_text for c in checkins if c.health_text][-3:]
    week.fine_days = db.execute(
        select(func.count()).select_from(DailyFine).where(
            DailyFine.care_profile_id == profile.id, DailyFine.day >= week.start, DailyFine.day <= week.end,
            DailyFine.fine_at.is_not(None),
        )
    ).scalar_one()


def _readings(db: Session, profile: CareProfile, week: Week, now: datetime) -> None:
    notes = db.execute(
        select(HealthNote).where(
            HealthNote.care_profile_id == profile.id, HealthNote.kind == "reading",
            HealthNote.label.in_(("bp", "sugar")), HealthNote.recorded_at >= now - timedelta(days=8),
        ).order_by(HealthNote.recorded_at)
    ).scalars().all()
    for note in notes:
        day = _local_day(profile, note.recorded_at)
        if week.start <= day <= week.end:
            (week.bp if note.label == "bp" else week.sugar).append(Reading(day, note.value or ""))
    week.warnings += _reading_warnings(profile, [n for n in notes if week.start <= _local_day(profile, n.recorded_at)])


def _reading_warnings(profile: CareProfile, notes: list[HealthNote]) -> list[Warning]:
    found = []
    top_by_day: dict[date, float] = {}
    for n in notes:
        if n.label == "bp" and n.value_num is not None:
            day = _local_day(profile, n.recorded_at)
            top_by_day[day] = max(top_by_day.get(day, 0), n.value_num)
    tops = [top_by_day[d] for d in sorted(top_by_day)][-BP_RISE_DAYS - 2:]
    if (len(tops) >= BP_RISE_DAYS and all(a <= b for a, b in zip(tops, tops[1:]))
            and tops[-1] - tops[0] >= BP_RISE_MMHG):
        found.append(Warning("bp_rising", f"BP has gone up {len(tops)} readings in a row, "
                                          f"from {tops[0]:.0f} to {tops[-1]:.0f}."))
    high = [n for n in notes if n.label == "sugar" and
            ((n.value_num is not None and n.value_num >= HIGH_SUGAR) or n.value == "high")]
    if len(high) >= HIGH_SUGAR_LIMIT:
        found.append(Warning("sugar_high", f"Sugar was high {len(high)} times this week."))
    return found


def _visits(db: Session, profile: CareProfile, week: Week) -> None:
    rows = db.execute(
        select(Appointment).where(
            Appointment.care_profile_id == profile.id,
            Appointment.scheduled_date >= week.start,
            Appointment.scheduled_date <= week.end + timedelta(days=14),
            Appointment.status != "cancelled",
        ).order_by(Appointment.scheduled_date, Appointment.start_time)
    ).scalars().all()
    for a in rows:
        line = f"{a.scheduled_date:%a %d %b} {a.start_time} with {a.provider}"
        if a.scheduled_date <= week.end and a.status == "completed":
            week.visits_done.append(line)
        elif a.scheduled_date > week.end:
            week.visits_next.append(line)


def _tasks(db: Session, profile: CareProfile, week: Week, now: datetime) -> None:
    since = now - timedelta(days=7)
    tasks = db.execute(select(Task).where(Task.care_profile_id == profile.id)).scalars().all()
    week.tasks_done = sum(1 for t in tasks if t.status == "DONE" and _aware(t.updated_at) >= since)
    week.tasks_open = sum(1 for t in tasks if t.status != "DONE")


def _last_seen(db: Session, profile: CareProfile) -> datetime | None:
    spoke = db.execute(
        select(func.max(ChatMessage.created_at)).join(HealthCheckin, HealthCheckin.id == ChatMessage.checkin_id)
        .where(HealthCheckin.care_profile_id == profile.id, ChatMessage.sender == "parent")
    ).scalar_one()
    fine = db.execute(
        select(func.max(DailyFine.fine_at)).where(DailyFine.care_profile_id == profile.id)
    ).scalar_one()
    seen = [_aware(t) for t in (spoke, fine) if t is not None]
    return max(seen) if seen else None


def build_week(db: Session, profile: CareProfile, now: datetime, end: date | None = None) -> Week:
    now = _aware(now)
    end = end or local_now(profile, now).date()
    week = Week(start=end - timedelta(days=6), end=end)
    _doses(db, profile, week)
    _checkins(db, profile, week)
    _readings(db, profile, week, now)
    _visits(db, profile, week)
    _tasks(db, profile, week, now)
    name = profile.display_name
    for slot, count in sorted(week.missed_by_slot.items()):
        if count >= MISSED_SLOT_LIMIT:
            week.warnings.insert(0, Warning(f"missed_{slot}", f"{name} missed the {slot} dose {count} times "
                                                              f"this week."))
    if profile.linked_user_id:
        seen = _last_seen(db, profile)
        if seen is not None and now - seen >= QUIET_FOR:
            week.warnings.append(Warning("quiet", f"{name} hasn't used the app since "
                                                  f"{local_now(profile, seen):%a %d %b, %H:%M}."))
    return week


def summary_lines(profile: CareProfile, week: Week) -> list[str]:
    doses = week.taken + week.skipped + week.missed
    lines = [f"Medicines: {week.taken} of {doses} doses taken" + (f", {week.missed} missed" if week.missed else "")
             if doses else "Medicines: none logged this week",
             f"Check-ins: spoke on {week.checkin_days} of 7 days, tapped \"I'm fine\" on {week.fine_days}"]
    if week.unwell_days:
        lines.append(f"Felt unwell on {week.unwell_days} day(s)")
    if week.bp:
        lines.append("BP: " + ", ".join(r.value for r in week.bp[-4:]))
    if week.sugar:
        lines.append("Sugar: " + ", ".join(r.value for r in week.sugar[-4:]))
    if week.visits_done:
        lines.append("Doctor visits: " + "; ".join(week.visits_done))
    if week.visits_next:
        lines.append("Coming up: " + "; ".join(week.visits_next[:3]))
    lines.append(f"Tasks: {week.tasks_done} done, {week.tasks_open} still open")
    return lines


def _claim(db: Session, profile: CareProfile, kind: str, period: str, now: datetime) -> bool:
    try:
        with db.begin_nested():
            db.add(CareAlertSent(care_profile_id=profile.id, kind=kind, period=period, sent_at=now))
        return True
    except IntegrityError:
        return False


def _family(db: Session, profile: CareProfile):
    return family_alerts._members_except(db, profile.family_id, profile.linked_user_id)


def send_weekly_summaries(db: Session, now: datetime) -> int:
    sent = 0
    for profile in db.execute(select(CareProfile)).scalars().all():
        try:
            sent += _send_week(db, profile, now)
        except Exception:  # noqa: BLE001 - one bad profile must not stop the rest
            db.rollback()
            logger.exception("Weekly summary failed for %s", profile.id)
    return sent


def _send_week(db: Session, profile: CareProfile, now: datetime) -> int:
    local = local_now(profile, now)
    if local.weekday() != SEND_DAY or local.time() < SEND_AT:
        return 0
    if not _claim(db, profile, "weekly", local.date().isoformat(), now):
        return 0
    week = build_week(db, profile, now)
    lines = summary_lines(profile, week) + [f"Watch: {w.text}" for w in week.warnings]
    members = _family(db, profile)
    for user in members:
        notify(db, user.id, "summary.weekly", family_id=profile.family_id, payload={
            "care_profile_id": profile.id, "parent_name": profile.display_name,
            "week_end": week.end.isoformat(), "warnings": len(week.warnings)})
    db.commit()
    family_alerts._email(members, f"{profile.display_name}'s week", "\n".join(lines))
    return 1


def send_pattern_warnings(db: Session, now: datetime) -> int:
    sent = 0
    for profile in db.execute(select(CareProfile)).scalars().all():
        try:
            sent += _warn(db, profile, now)
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Pattern warnings failed for %s", profile.id)
    return sent


def _warn(db: Session, profile: CareProfile, now: datetime) -> int:
    week = build_week(db, profile, now)
    year, number, _ = local_now(profile, now).date().isocalendar()
    new = [w for w in week.warnings if _claim(db, profile, f"warn:{w.kind}", f"{year}-W{number:02d}", now)]
    if not new:
        return 0
    members = _family(db, profile)
    for w in new:
        for user in members:
            notify(db, user.id, "pattern.warning", family_id=profile.family_id, payload={
                "care_profile_id": profile.id, "parent_name": profile.display_name, "kind": w.kind,
                "text": w.text})
    db.commit()
    family_alerts._email(members, f"Something to watch: {profile.display_name}", "\n".join(w.text for w in new))
    return len(new)
