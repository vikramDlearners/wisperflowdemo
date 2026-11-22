"""The parent check-in step machine: greet -> health -> medicines -> appointments -> done.

One check-in per care profile per local day. Every bot and parent message is stored as a ChatMessage and every
step change writes a "checkin.updated" activity row. Medicine names only ever come from the due-dose list.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.checkin import ChatMessage, HealthCheckin
from app.models.membership import FamilyMember
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.services.activity import log_activity
from app.services.app_settings import get_intent_mode
from app.services.doses import (
    DueDose,
    due_untaken,
    local_now,
    logged_today,
    record_dose,
    set_remind_later,
    today_for,
)
from app.services.family_alerts import (
    notify_family_finished,
    notify_family_update,
    notify_family_urgent,
    other_members,
)
from app.services.parent_context import ParentContext
from app.services.permissions import role_name_for
from app.services.replies import reply
from app.services.understanding import DEFAULT_DELAY_MINUTES, is_urgent, understand_medicines

GREET, HEALTH, MEDICINES, APPOINTMENTS, DONE = "greet", "health", "medicines", "appointments", "done"
MANAGER_ROLE = "Family manager"
UPCOMING_STATUSES = ("scheduled", "rescheduled")
NOT_TAKEN_REASK = timedelta(minutes=30)


@dataclass
class Turn:
    checkin: HealthCheckin
    bot_messages: list[str]
    call_number: str | None
    urgent: bool


# ---------- small helpers ----------

def format_time(hhmm: str) -> str:
    """"10:00" -> "10:00 AM", "14:30" -> "2:30 PM". Unreadable values are returned unchanged."""
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except (ValueError, AttributeError):
        return hhmm
    suffix = "AM" if h < 12 else "PM"
    return f"{h % 12 or 12}:{m:02d} {suffix}"


def _say(ctx: ParentContext, key: str, **values) -> str:
    return reply(key, ctx.language, **values)


def _family_names(db: Session, ctx: ParentContext) -> str:
    names = [u.display_name for u in other_members(db, ctx) if u.display_name]
    if not names:
        return _say(ctx, "your_family")
    if ctx.language == "en" and len(names) > 1:
        return f"{', '.join(names[:-1])} and {names[-1]}"
    return ", ".join(names)


def _greeting(ctx: ParentContext, now: datetime) -> str:
    hour = local_now(ctx.profile, now).hour
    key = "greet_morning" if hour < 12 else "greet_afternoon" if hour < 17 else "greet_evening"
    return _say(ctx, key, name=ctx.greeting_name)


def _set_step(db: Session, ctx: ParentContext, checkin: HealthCheckin, step: str, now: datetime) -> None:
    if checkin.step == step:
        return
    checkin.step = step
    checkin.updated_at = now
    log_activity(db, ctx.family_id, ctx.user_id, "checkin.updated", "health_checkin", checkin.id, {"step": step})


def _store(db: Session, ctx: ParentContext, checkin: HealthCheckin, sender: str, texts: list[str]) -> None:
    for text in texts:
        db.add(ChatMessage(checkin_id=checkin.id, sender=sender, text=text, language=ctx.language))


def _today(db: Session, ctx: ParentContext, now: datetime) -> HealthCheckin | None:
    return db.execute(
        select(HealthCheckin).where(
            HealthCheckin.care_profile_id == ctx.profile.id,
            HealthCheckin.checkin_date == today_for(ctx.profile, now),
        )
    ).scalar_one_or_none()


def _get_or_create(db: Session, ctx: ParentContext, now: datetime) -> HealthCheckin:
    checkin = _today(db, ctx, now)
    if checkin is not None:
        return checkin
    checkin = HealthCheckin(
        family_id=ctx.family_id, care_profile_id=ctx.profile.id, parent_user_id=ctx.user_id,
        checkin_date=today_for(ctx.profile, now), step=GREET, urgent=False, started_at=now, updated_at=now,
    )
    db.add(checkin)
    try:
        db.commit()
    except IntegrityError:
        # Another request created today's check-in first.
        db.rollback()
        return _today(db, ctx, now)
    return checkin


def call_number(db: Session, ctx: ParentContext) -> str | None:
    """The family manager's caregiver phone, else their doctor's number (first manager that has one)."""
    members = db.execute(
        select(FamilyMember)
        .where(FamilyMember.family_id == ctx.family_id, FamilyMember.status == "active")
        .order_by(FamilyMember.created_at, FamilyMember.id)
    ).scalars()
    profiles = []
    for m in members:
        if role_name_for(db, m) != MANAGER_ROLE:
            continue
        p = db.execute(
            select(ParentOnboardingProfile).where(ParentOnboardingProfile.user_id == m.user_id)
        ).scalar_one_or_none()
        if p is not None:
            profiles.append(p)
    for p in profiles:
        if p.caregiver_phone and p.caregiver_phone.strip():
            return p.caregiver_phone.strip()
    for p in profiles:
        if p.doctor_contact_number and p.doctor_contact_number.strip():
            return p.doctor_contact_number.strip()
    return None


# ---------- medicines ----------

def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _remaining(db: Session, ctx: ParentContext, now: datetime) -> list[DueDose]:
    """Due doses still to ask about now.

    Taken and skipped (includes "ran out") doses are answered for the day. A plain "not taken" answer is not
    asked again until NOT_TAKEN_REASK has passed since it was recorded, so one exchange never loops. A
    remind-later dose comes back once its reminder time has passed (due_untaken hides it until then).
    """
    logged = logged_today(db, ctx.profile, now)
    out = []
    for d in due_untaken(db, ctx.profile, now):
        if d.status == "skipped":
            continue
        if d.status == "not_taken":
            row = logged.get((d.medicine_id, d.slot))
            if row is not None and row.remind_at is None:
                recorded = _aware(row.recorded_at)
                if recorded is not None and _aware(now) - recorded < NOT_TAKEN_REASK:
                    continue
        out.append(d)
    return out


def _unique(doses: list[DueDose]) -> list[DueDose]:
    seen: set[str] = set()
    out = []
    for d in doses:
        if d.medicine_id not in seen:
            seen.add(d.medicine_id)
            out.append(d)
    return out


def _ask_medicines(ctx: ParentContext, checkin: HealthCheckin, remaining: list[DueDose]) -> str:
    meds = _unique(remaining)
    if len(meds) == 1:
        checkin.pending_medicine_id = meds[0].medicine_id
        return _say(ctx, "meds_one", name=meds[0].name)
    checkin.pending_medicine_id = None
    return _say(ctx, "meds_list", count=len(meds), names=", ".join(d.name for d in meds))


def _continue_medicines(
    db: Session, ctx: ParentContext, checkin: HealthCheckin, now: datetime, announce_none: bool
) -> list[str]:
    remaining = _remaining(db, ctx, now)
    if remaining:
        return [_ask_medicines(ctx, checkin, remaining)]
    msgs = [_say(ctx, "meds_none")] if announce_none else []
    return msgs + _appointments_and_done(db, ctx, checkin, now)


def _handle_medicines(db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str, now: datetime) -> list[str]:
    remaining = _remaining(db, ctx, now)
    if not remaining:
        return _appointments_and_done(db, ctx, checkin, now)
    asked = _unique(remaining)
    narrowed = False
    if checkin.pending_medicine_id and any(d.medicine_id == checkin.pending_medicine_id for d in asked):
        asked = [d for d in asked if d.medicine_id == checkin.pending_medicine_id]
        narrowed = True
    answers = understand_medicines(text, asked, get_intent_mode(db))
    if answers.unclear or not answers.items:
        first = asked[0]
        checkin.pending_medicine_id = first.medicine_id
        msgs = [_say(ctx, "not_understood")] if narrowed else []
        return msgs + [_say(ctx, "meds_one", name=first.name)]

    by_medicine: dict[str, list[DueDose]] = {}
    for d in remaining:
        by_medicine.setdefault(d.medicine_id, []).append(d)
    logged = False
    remind_minutes: int | None = None
    finished: list[DueDose] = []
    for answer in answers.items:
        doses = by_medicine.get(answer.medicine_id, [])
        recorded_finished = False
        for dose in doses:
            try:
                if answer.outcome in ("taken", "not_taken"):
                    record_dose(db, ctx.profile, dose.medicine_id, dose.slot, answer.outcome, ctx.user_id, "chatbot", now)
                    logged = True
                elif answer.outcome == "remind_later":
                    remind_minutes = answers.delay_minutes or DEFAULT_DELAY_MINUTES
                    set_remind_later(db, ctx.profile, dose.medicine_id, dose.slot, remind_minutes, now)
                elif answer.outcome == "finished":
                    # Ran out: answered for the day (skipped), never asked again; the family is told once.
                    record_dose(db, ctx.profile, dose.medicine_id, dose.slot, "skipped", ctx.user_id, "chatbot", now)
                    recorded_finished = True
            except ValueError:
                # The medicine was removed or deactivated during the conversation; nothing to record.
                continue
        if recorded_finished:
            finished.append(doses[0])

    msgs: list[str] = []
    if logged:
        msgs.append(_say(ctx, "meds_logged"))
    if remind_minutes is not None:
        msgs.append(_say(ctx, "meds_remind", minutes=remind_minutes))
    if finished:
        family = _family_names(db, ctx)
        for dose in finished:
            notify_family_finished(db, ctx, dose)
            msgs.append(_say(ctx, "meds_finished", family=family, name=dose.name))
    return msgs + _continue_medicines(db, ctx, checkin, now, announce_none=False)


# ---------- appointments ----------

def _upcoming_appointments(db: Session, ctx: ParentContext, now: datetime) -> list[Appointment]:
    today = today_for(ctx.profile, now)
    return list(
        db.execute(
            select(Appointment)
            .where(
                Appointment.care_profile_id == ctx.profile.id,
                Appointment.scheduled_date.in_((today, today + timedelta(days=1))),
                Appointment.status.in_(UPCOMING_STATUSES),
            )
            .order_by(Appointment.scheduled_date, Appointment.start_time)
        ).scalars()
    )


def _appointments_and_done(db: Session, ctx: ParentContext, checkin: HealthCheckin, now: datetime) -> list[str]:
    checkin.pending_medicine_id = None
    _set_step(db, ctx, checkin, APPOINTMENTS, now)
    today = today_for(ctx.profile, now)
    msgs = []
    for a in _upcoming_appointments(db, ctx, now):
        key = "appt_today" if a.scheduled_date == today else "appt_tomorrow"
        msgs.append(_say(ctx, key, time=format_time(a.start_time), reason=a.reason, provider=a.provider))
    _set_step(db, ctx, checkin, DONE, now)
    msgs.append(_say(ctx, "goodbye", name=ctx.greeting_name))
    return msgs


# ---------- health ----------

def _share_health(db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str) -> str:
    family = _family_names(db, ctx)
    if is_urgent(text):
        checkin.urgent = True
        notify_family_urgent(db, ctx, checkin, text)
        return _say(ctx, "health_urgent", family=family)
    notify_family_update(db, ctx, checkin)
    return _say(ctx, "health_noted", family=family)


# ---------- public API ----------

def _turn(db: Session, ctx: ParentContext, checkin: HealthCheckin, msgs: list[str]) -> Turn:
    _store(db, ctx, checkin, "bot", msgs)
    db.commit()
    db.refresh(checkin)
    number = call_number(db, ctx) if checkin.urgent else None
    return Turn(checkin=checkin, bot_messages=msgs, call_number=number, urgent=bool(checkin.urgent))


def _reopen_or(db: Session, ctx: ParentContext, checkin: HealthCheckin, now: datetime, otherwise: str) -> list[str]:
    """From "done": newly due or reminder-due doses send the check-in back to the medicines step."""
    remaining = _remaining(db, ctx, now)
    if remaining:
        _set_step(db, ctx, checkin, MEDICINES, now)
        return [_ask_medicines(ctx, checkin, remaining)]
    return [otherwise]


def start_or_resume(db: Session, ctx: ParentContext, now: datetime) -> Turn:
    checkin = _get_or_create(db, ctx, now)
    msgs = [_greeting(ctx, now)]
    if checkin.step in (GREET, HEALTH):
        _set_step(db, ctx, checkin, HEALTH, now)
        msgs.append(_say(ctx, "ask_health"))
    elif checkin.step == MEDICINES:
        msgs += _continue_medicines(db, ctx, checkin, now, announce_none=True)
    elif checkin.step == APPOINTMENTS:
        msgs += _appointments_and_done(db, ctx, checkin, now)
    else:
        msgs += _reopen_or(db, ctx, checkin, now, _say(ctx, "anything_else"))
    return _turn(db, ctx, checkin, msgs)


def handle_parent_text(db: Session, ctx: ParentContext, text: str, now: datetime) -> Turn:
    text = (text or "").strip()
    checkin = _get_or_create(db, ctx, now)
    if checkin.step == GREET:
        _set_step(db, ctx, checkin, HEALTH, now)
    if not text:
        return _turn(db, ctx, checkin, [_say(ctx, "not_understood")])
    _store(db, ctx, checkin, "parent", [text])
    checkin.updated_at = now

    if checkin.step == HEALTH:
        checkin.health_text = text
        msgs = [_share_health(db, ctx, checkin, text)]
        _set_step(db, ctx, checkin, MEDICINES, now)
        msgs += _continue_medicines(db, ctx, checkin, now, announce_none=True)
    elif checkin.step == MEDICINES:
        msgs = _handle_medicines(db, ctx, checkin, text, now)
    elif checkin.step == APPOINTMENTS:
        msgs = _appointments_and_done(db, ctx, checkin, now)
    else:
        checkin.health_text = f"{checkin.health_text}\n{text}" if checkin.health_text else text
        msgs = [_share_health(db, ctx, checkin, text)]
        msgs += _reopen_or(db, ctx, checkin, now, _say(ctx, "anything_else"))
    return _turn(db, ctx, checkin, msgs)
