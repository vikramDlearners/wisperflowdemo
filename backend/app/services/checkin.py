"""The parent check-in step machine: greet -> health -> medicines -> meals -> appointments -> note -> done.

One check-in per care profile per local day. Every bot and parent message is stored as a ChatMessage and every
step change writes a "checkin.updated" activity row. Medicine names only ever come from the due-dose list.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.checkin import ChatMessage, HealthCheckin
from app.models.medicine import Medicine
from app.models.membership import FamilyMember
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.services.activity import log_activity
from app.services.care_notes import care_tips
from app.services.app_settings import get_intent_mode
from app.services.doses import (
    DueDose,
    current_doses,
    dose_in_part,
    doses_today,
    local_now,
    logged_today,
    record_dose,
    set_remind_later,
    today_for,
)
from app.services.emergencies import note_emergency
from app.services.family_alerts import (
    EMERGENCY_TEXT,
    notify_family_emergency,
    notify_family_finished,
    notify_family_update,
    notify_family_urgent,
    other_members,
)
from app.services.parent_context import ParentContext
from app.services.meals import meals_due, save_meals
from app.services.permissions import role_name_for
from app.services.profile import get_care_profile_onboarding
from app.services.replies import is_photo_offer, reply, reply_list, shows_photos
from app.services.understanding import (
    ALL,
    DEFAULT_DELAY_MINUTES,
    NONE,
    MedicineAnswer,
    MedicineAnswers,
    count_scope,
    is_dose_report,
    is_medicine_question,
    named_day_part,
    is_all_well,
    is_bare_confusion,
    is_bare_no,
    is_bare_yes,
    is_medicine_confusion,
    is_photo_request,
    is_urgent,
    named_medicines,
    photo_offer_answer,
    understand_medicines,
)

GREET, HEALTH, MEDICINES, APPOINTMENTS, DONE = "greet", "health", "medicines", "appointments", "done"
MEALS_STEP = "meals"
NOTE = "note"  # "anything to tell me or note down?", the last question
MANAGER_ROLE = "Family manager"
UPCOMING_STATUSES = ("scheduled", "rescheduled")
NOT_TAKEN_REASK = timedelta(minutes=30)
# pending_medicine_id while waiting for "how many did you take?" / "which ones?" (never a medicine id).
# A trailing AFTER_DONE marks a dose the parent reported after the check-in had finished.
HOW_MANY, WHICH, AFTER_DONE = "?how-many", "?which", "!"


def _asking_count(checkin: HealthCheckin) -> bool:
    return (checkin.pending_medicine_id or "").startswith("?")


def _count_state(question: str, from_done: bool) -> str:
    return question + (AFTER_DONE if from_done else "")

# Pure closings after "done" ("ok", "thank you", "bye"): not health news, so never appended or shared.
# Longest first, so "thank you" is removed before "thank".
_CLOSINGS = tuple(sorted({
    "ok", "okay", "okey", "k", "fine", "alright", "all right", "good", "bye", "bye bye", "goodbye", "good bye",
    "see you", "good night", "thank you", "thank you so much", "thank you very much", "thanks", "thanks a lot",
    "thank u", "no", "nope", "nothing", "nothing to tell", "nothing to note", "nothing to say", "nothing else", "nothing more", "that's all", "that is all",
    "நன்றி", "ரொம்ப நன்றி", "மிக்க நன்றி", "சரி", "போதும்", "ஒன்றுமில்லை", "ஒன்னுமில்லை", "இல்லை", "வணக்கம்", "பை",
    "धन्यवाद", "शुक्रिया", "ठीक है", "ठीक", "बस", "अलविदा", "नहीं", "कुछ नहीं", "नमस्ते", "बाय",
    "ధన్యవాదాలు", "ధన్యవాదం", "సరే", "ఏమీ లేదు", "లేదు", "బై",
    "നന്ദി", "ശരി", "ഒന്നുമില്ല", "ഇല്ല", "ബൈ",
    "ಧನ್ಯವಾದ", "ಧನ್ಯವಾದಗಳು", "ಸರಿ", "ಏನೂ ಇಲ್ಲ", "ಇಲ್ಲ", "ಬೈ",
}, key=len, reverse=True))
_PUNCTUATION = re.compile(r"[.,!?;:।\"]+")


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


def _say_list(ctx: ParentContext, key: str, names: list[str], **values) -> str:
    return reply_list(key, ctx.language, names, **values)


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
    """Stage messages with the next sequence numbers of this check-in's conversation."""
    if not texts:
        return
    db.flush()  # earlier messages of this turn count too
    last = db.execute(
        select(func.max(ChatMessage.seq)).where(ChatMessage.checkin_id == checkin.id)
    ).scalar() or 0
    for i, text in enumerate(texts, start=1):
        db.add(ChatMessage(checkin_id=checkin.id, sender=sender, text=text, language=ctx.language, seq=last + i))


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


def _remaining(db: Session, ctx: ParentContext, now: datetime, volunteered: bool = False) -> list[DueDose]:
    """The current dose of each medicine still to ask about (doses.current_doses: one per medicine).

    Taken and skipped (includes "ran out") doses are answered. A plain "not taken" answer is not asked again
    until NOT_TAKEN_REASK has passed since it was recorded, so one exchange never loops. A remind-later dose
    comes back once its reminder time has passed.
    """
    logged = logged_today(db, ctx.profile, now)
    out = []
    for d in current_doses(db, ctx.profile, now, volunteered=volunteered):
        if d.status == "not_taken" and not volunteered:
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


def _with_photo(db: Session, doses: list[DueDose]) -> list[str]:
    """The names of these medicines that have a photo."""
    ids = set(db.execute(
        select(Medicine.id).where(
            Medicine.id.in_({d.medicine_id for d in doses}), Medicine.image_data.isnot(None)
        )
    ).scalars())
    return [d.name for d in _unique(doses) if d.medicine_id in ids]


def _ask_medicines(
    db: Session, ctx: ParentContext, checkin: HealthCheckin, remaining: list[DueDose]
) -> list[str]:
    """"Did you take them?" and, once per conversation, whether to show the images (if there are any)."""
    question = _medicines_question(ctx, checkin, remaining)
    said = [m.text for m in session_messages(db, checkin) if m.sender == "bot"]
    if any(is_photo_offer(t) for t in said) or not _with_photo(db, remaining):
        return [question]
    return [question, _say(ctx, "photo_offer")]


def _answer_photo_offer(
    db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str, now: datetime
) -> list[str] | None:
    """The reply when the parent's message answers the images question, else None. Then the doses are asked
    about again: a "yes" to the images must never be recorded as medicines taken."""
    if checkin.step != MEDICINES:
        return None
    bot = [m.text for m in conversation(db, checkin) if m.sender == "bot"]
    if not bot or not is_photo_offer(bot[-1]):
        return None
    answer = photo_offer_answer(text)
    remaining = _remaining(db, ctx, now)
    if answer is None or not remaining:
        return None
    msgs: list[str] = []
    if answer:
        have = _with_photo(db, remaining)
        missing = [d.name for d in _unique(remaining) if d.name not in have]
        if have:
            msgs.append(_say(ctx, "photo_here", names=_names(have)))
        if missing:
            msgs.append(_say(ctx, "photo_missing", names=_names(missing)))
    return msgs + [_medicines_question(ctx, checkin, remaining)]


def _medicines_question(ctx: ParentContext, checkin: HealthCheckin, remaining: list[DueDose]) -> str:
    meds = _unique(remaining)
    if len(meds) == 1:
        checkin.pending_medicine_id = meds[0].medicine_id
        return _say(ctx, "meds_one", name=meds[0].name)
    checkin.pending_medicine_id = None
    return _say_list(ctx, "meds_list", [d.name for d in meds], count=len(meds))


def _continue_medicines(
    db: Session, ctx: ParentContext, checkin: HealthCheckin, now: datetime, announce_none: bool,
    from_done: bool = False,
) -> list[str]:
    remaining = _remaining(db, ctx, now)
    if remaining:
        return _ask_medicines(db, ctx, checkin, remaining)
    if from_done:
        # A dose the parent reported after the check-in finished: no need to repeat appointments and goodbye.
        checkin.pending_medicine_id = None
        _set_step(db, ctx, checkin, DONE, now)
        return [_say(ctx, "anything_else")]
    msgs = [_say(ctx, "meds_none")] if announce_none else []
    return msgs + _meals_or_done(db, ctx, checkin, now)


def _names(items: list[str]) -> str:
    return ", ".join(dict.fromkeys(items))  # unique, in order


def _local_clock(ctx: ParentContext, now: datetime) -> str:
    return format_time(local_now(ctx.profile, now).strftime("%H:%M"))


def _handle_medicines(
    db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str, now: datetime,
    remaining: list[DueDose] | None = None, from_done: bool = False,
) -> list[str]:
    if _asking_count(checkin):
        # Answering "how many?" / "which ones?": the doses on offer are the current ones the parent reported.
        from_done = from_done or checkin.pending_medicine_id.endswith(AFTER_DONE)
        remaining = _remaining(db, ctx, now, volunteered=True) if remaining is None else remaining
    remaining = _remaining(db, ctx, now) if remaining is None else remaining
    if not remaining:
        checkin.pending_medicine_id = None
        if from_done:
            return _continue_medicines(db, ctx, checkin, now, announce_none=False, from_done=True)
        return _meals_or_done(db, ctx, checkin, now)
    asked = _unique(remaining)
    if _asking_count(checkin):
        return _handle_count_answer(db, ctx, checkin, text, now, remaining, asked, from_done)
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

    if len(asked) > 1 and all(a.outcome == "taken" for a in answers.items):
        scope = count_scope(text, asked)
        if scope is None:
            # "I took my medicine" with several due: ask how many before marking anything.
            checkin.pending_medicine_id = _count_state(HOW_MANY, from_done)
            return [_say_list(ctx, "meds_how_many", [d.name for d in asked], count=len(asked))]
        if isinstance(scope, int) and 0 < scope < len(asked):
            checkin.pending_medicine_id = _count_state(WHICH, from_done)
            return [_say_list(ctx, "meds_which", [d.name for d in asked])]
        if isinstance(scope, list):
            answers = MedicineAnswers(items=[MedicineAnswer(m, "taken") for m in scope])
    return _apply_answers(db, ctx, checkin, answers, remaining, now, from_done)


def _handle_count_answer(
    db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str, now: datetime,
    remaining: list[DueDose], asked: list[DueDose], from_done: bool,
) -> list[str]:
    """The reply to "how many did you take?" or "which ones?"."""
    scope = count_scope(text, asked)
    ids = [d.medicine_id for d in asked]
    if scope == ALL or (isinstance(scope, int) and scope >= len(asked)):
        answers = MedicineAnswers(items=[MedicineAnswer(m, "taken") for m in ids])
    elif scope == NONE or scope == 0:
        answers = MedicineAnswers(items=[MedicineAnswer(m, "not_taken") for m in ids])
    elif isinstance(scope, list):
        answers = MedicineAnswers(items=[MedicineAnswer(m, "taken") for m in scope])
    elif isinstance(scope, int):
        checkin.pending_medicine_id = _count_state(WHICH, from_done)
        return [_say_list(ctx, "meds_which", [d.name for d in asked])]
    else:
        plain = understand_medicines(text, asked, get_intent_mode(db))
        if not plain.unclear and plain.items and all(a.outcome == "not_taken" for a in plain.items):
            answers = plain
        else:
            key = "meds_which" if checkin.pending_medicine_id.startswith(WHICH) else "meds_how_many"
            return [_say(ctx, "not_understood"),
                    _say_list(ctx, key, [d.name for d in asked], count=len(asked))]
    checkin.pending_medicine_id = None
    return _apply_answers(db, ctx, checkin, answers, remaining, now, from_done)


def _apply_answers(
    db: Session, ctx: ParentContext, checkin: HealthCheckin, answers: MedicineAnswers,
    remaining: list[DueDose], now: datetime, from_done: bool,
) -> list[str]:
    checkin.pending_medicine_id = None
    by_medicine: dict[str, list[DueDose]] = {}
    for d in remaining:
        by_medicine.setdefault(d.medicine_id, []).append(d)
    taken: list[str] = []
    not_taken = False
    remind_minutes: int | None = None
    finished: list[DueDose] = []
    for answer in answers.items:
        doses = by_medicine.get(answer.medicine_id, [])
        recorded_finished = False
        for dose in doses:
            try:
                if answer.outcome in ("taken", "not_taken"):
                    record_dose(db, ctx.profile, dose.medicine_id, dose.slot, answer.outcome, ctx.user_id, "chatbot", now)
                    if answer.outcome == "taken":
                        taken.append(dose.name)
                    else:
                        not_taken = True
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
    if taken:
        msgs.append(_say(ctx, "meds_logged_at", names=_names(taken), time=_local_clock(ctx, now)))
    if not_taken:
        msgs.append(_say(ctx, "meds_logged"))
    if remind_minutes is not None:
        msgs.append(_say(ctx, "meds_remind", minutes=remind_minutes))
    if finished:
        family = _family_names(db, ctx)
        has_family = bool(other_members(db, ctx))
        for dose in finished:
            notify_family_finished(db, ctx, dose)
            if has_family:
                msgs.append(_say(ctx, "meds_finished", family=family, name=dose.name))
            else:
                msgs.append(_say(ctx, "meds_finished_alone", name=dose.name))
    return msgs + _continue_medicines(db, ctx, checkin, now, announce_none=False, from_done=from_done)


# ---------- meals ----------

def _meal_question(ctx: ParentContext, meals: list[str]) -> str:
    names = [_say(ctx, f"meal_{m}") for m in meals]
    joined = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} {_say(ctx, 'word_and')} {names[-1]}"
    return _say(ctx, "meal_ask", meals=joined)


def _meals_or_done(db: Session, ctx: ParentContext, checkin: HealthCheckin, now: datetime) -> list[str]:
    """Ask about the meals eaten so far today that were not told yet; otherwise finish with appointments."""
    due = meals_due(db, ctx.profile, now)
    if due:
        checkin.pending_medicine_id = None
        _set_step(db, ctx, checkin, MEALS_STEP, now)
        return [_meal_question(ctx, due)]
    return _appointments_and_done(db, ctx, checkin, now)


def _handle_meals(db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str, now: datetime) -> list[str]:
    """Save what the parent ate for the meals asked about (whatever they say, "nothing" included)."""
    due = meals_due(db, ctx.profile, now)
    if not due:
        return _appointments_and_done(db, ctx, checkin, now)
    save_meals(db, ctx.profile, due, text, ctx.user_id, now, checkin.id)
    return [_say(ctx, "meal_saved")] + _appointments_and_done(db, ctx, checkin, now)


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
    already_said = {m.text for m in conversation(db, checkin) if m.sender == "bot"}
    for a in _upcoming_appointments(db, ctx, now):
        key = "appt_today" if a.scheduled_date == today else "appt_tomorrow"
        line = _say(ctx, key, time=format_time(a.start_time), reason=a.reason, provider=a.provider)
        if line not in already_said:  # each appointment is reminded once a day, not on every reopen
            msgs.append(line)
    _set_step(db, ctx, checkin, NOTE, now)
    note = _care_note(db, ctx, checkin)
    if note:
        msgs.append(note)
    msgs.append(_say(ctx, "note_ask"))
    return msgs


def _handle_note(db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str, now: datetime) -> list[str]:
    """The answer to the last question: kept with today's health notes, then goodbye (or newly due doses)."""
    urgent = is_urgent(text)
    nothing = is_closing(text) or is_bare_no(text)
    if not urgent and is_bare_yes(text) and not nothing:
        return [_say(ctx, "note_listening")]
    msgs: list[str] = []
    if urgent or not nothing:
        checkin.health_text = f"{checkin.health_text}\n{text}" if checkin.health_text else text
        msgs.append(_share_health(db, ctx, checkin, text, now))
        if is_bare_confusion(text):
            msgs += [_say(ctx, "confused_help"), *_schedule_answer(db, ctx, now)]
    if urgent:
        return msgs + [_say(ctx, "note_ask")]  # no cheerful goodbye in an emergency
    _set_step(db, ctx, checkin, DONE, now)
    return msgs + _reopen_or(db, ctx, checkin, now, _say(ctx, "goodbye", name=ctx.greeting_name))


def _care_note(db: Session, ctx: ParentContext, checkin: HealthCheckin) -> str | None:
    """A soft note from what the family wrote on the parent profile (deficiencies, notes, allergies), said at
    most once a day, just before goodbye."""
    tips = care_tips(get_care_profile_onboarding(db, ctx.profile))
    if not tips:
        return None
    intro = _say(ctx, "care_intro", name=ctx.greeting_name)
    if any(m.sender == "bot" and m.text.startswith(intro) for m in conversation(db, checkin)):
        return None
    return " ".join([intro, *(_say(ctx, key, **values) for key, values in tips)])


# ---------- health ----------

def _urgent(db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str, now: datetime) -> str:
    """Mark the check-in urgent, alert the family once, and say only what is true: who was alerted and
    whether a Call button exists (call_number) at all."""
    checkin.urgent = True
    note_emergency(db, ctx, checkin, text, "chat", now)
    notify_family_urgent(db, ctx, checkin, text)
    has_family = bool(other_members(db, ctx))
    has_phone = call_number(db, ctx) is not None
    if has_family:
        key = "health_urgent" if has_phone else "health_urgent_no_phone"
        return _say(ctx, key, family=_family_names(db, ctx))
    return _say(ctx, "health_urgent_call_only" if has_phone else "health_urgent_alone")


def _share_health(db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str, now: datetime) -> str:
    if is_urgent(text):
        return _urgent(db, ctx, checkin, text, now)
    notify_family_update(db, ctx, checkin)
    if is_all_well(text):
        return _say(ctx, "health_ok")  # nothing the family needs to act on, so no "I've shared it"
    if not other_members(db, ctx):
        return _say(ctx, "health_noted_alone")  # nobody to share it with: do not claim it was shared
    return _say(ctx, "health_noted", family=_family_names(db, ctx))


def is_closing(text: str) -> bool:
    """True for pure closings ("ok", "thank you, bye", "நன்றி") that carry no health news."""
    words = _PUNCTUATION.sub(" ", (text or "").lower().replace("’", "'")).split()
    if not words:
        return False
    rest = f" {' '.join(words)} "
    for phrase in _CLOSINGS:
        while f" {phrase} " in rest:  # also adjacent repeats ("ok ok")
            rest = rest.replace(f" {phrase} ", " ")
    return not rest.strip()


# ---------- "which medicine do I take?" ----------

_INSTRUCTIONS_MAX = 60


def _with_instructions(name: str, med: Medicine | None) -> str:
    text = " ".join(((med.instructions_text if med else None) or "").split())
    if not text:
        return name
    if len(text) > _INSTRUCTIONS_MAX:
        text = text[: _INSTRUCTIONS_MAX - 1].rstrip() + "…"
    return f"{name} ({text})"


def _schedule_answer(
    db: Session, ctx: ParentContext, now: datetime, only: list[str] | None = None, part: str | None = None
) -> list[str]:
    """Today's medicines, from the database only: taken, due now, later at a time, or any time today.
    `only` limits the answer to these medicine ids (nothing is said when none of them is due today).
    `part` narrows it to a part of the day the parent named; a named part with no dose falls back to the
    whole day rather than wrongly claim there are no medicines."""
    doses = doses_today(db, ctx.profile, now)
    if only is not None:
        doses = [d for d in doses if d.medicine_id in only]
        if not doses:
            return []
    if part is not None:
        in_part = [d for d in doses if dose_in_part(d, part, ctx.profile)]
        if in_part:
            doses = in_part
    if not doses:
        return [_say(ctx, "sched_none")]
    meds = {m.id: m for m in db.execute(
        select(Medicine).where(Medicine.id.in_({d.medicine_id for d in doses}))
    ).scalars()}
    now = _aware(now)
    taken: list[str] = []
    due_now: list[str] = []
    later: dict[str, list[str]] = {}
    anytime: list[str] = []
    for d in doses:
        label = _with_instructions(d.name, meds.get(d.medicine_id))
        if d.status == "taken":
            taken.append(d.name)
        elif d.status == "skipped":
            continue  # ran out today: nothing to take
        elif d.due_at is None:
            anytime.append(label)
        elif d.due_at <= now:
            due_now.append(label)
        else:
            later.setdefault(d.slot, []).append(label)
    msgs = []
    if taken:
        msgs.append(_say_list(ctx, "sched_taken", taken))
    if due_now:
        msgs.append(_say_list(ctx, "sched_now", due_now))
    for slot in sorted(later):
        msgs.append(_say_list(ctx, "sched_at", later[slot], time=format_time(slot)))
    if anytime:
        msgs.append(_say_list(ctx, "sched_anytime", anytime))
    if only is None and not (due_now or later or anytime):
        msgs.append(_say(ctx, "sched_all_done"))
    return msgs


def _medicine_help(
    db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str, now: datetime
) -> list[str] | None:
    """The answer to "send me the photo of my vitamin D3" or "I'm confused which tablet to take", or None when the
    text asks for neither. The chat shows the photos of the medicines a "photo_here" message names."""
    rows = db.execute(
        select(Medicine.id, Medicine.display_name, Medicine.image_data.isnot(None))
        .where(Medicine.care_profile_id == ctx.profile.id, Medicine.active.is_(True))
        .order_by(Medicine.created_at, Medicine.id)
    ).all()
    named = named_medicines(text, {mid: name for mid, name, _ in rows})
    wants_photo = is_photo_request(text, bool(named), checkin.step == MEDICINES)
    confused = is_medicine_confusion(text, bool(named)) or (
        # "I'm confused" as the answer to "How are you feeling?" is health news, which the family must hear.
        checkin.step in (MEDICINES, MEALS_STEP, APPOINTMENTS) and is_bare_confusion(text)
    )
    if not (wants_photo or confused):
        return None
    if not rows:
        return [_say(ctx, "sched_none")]
    if named:
        have = [name for mid, name, photo in rows if mid in named and photo]
        missing = [name for mid, name, photo in rows if mid in named and not photo]
        parts = []
        if have:
            parts.append(_say(ctx, "photo_here", names=_names(have)))
        if missing:
            parts.append(_say(ctx, "photo_missing", names=_names(missing)))
        # One message, so each photo appears once.
        schedule = _schedule_answer(db, ctx, now, only=named)
        if any("\n" in s for s in schedule):  # a bulleted list starts on its own line
            return ["\n".join([" ".join(parts), *schedule])]
        return [" ".join(parts + schedule)]
    intro = _say(ctx, "photo_which" if wants_photo else "confused_help")
    schedule = _schedule_answer(db, ctx, now)
    due = {d.medicine_id for d in doses_today(db, ctx.profile, now)}
    if not due:
        return schedule
    msgs = [intro, *schedule]
    # Only offer the photos that exist. The parent named no medicine, so listing every one that lacks a photo
    # ("ask your family to add one") is noise; that prompt is kept for a specifically named medicine above.
    have = [name for mid, name, photo in rows if mid in due and photo]
    if have:
        msgs.append(_say(ctx, "photo_here", names=_names(have)))
    return msgs


def _after_question(db: Session, ctx: ParentContext, checkin: HealthCheckin, now: datetime) -> list[str]:
    """After answering a question, ask again whatever the current step was waiting for."""
    if checkin.step == HEALTH:
        return [_say(ctx, "ask_health")]
    if checkin.step == MEDICINES:
        remaining = _remaining(db, ctx, now)
        if remaining:
            return _ask_medicines(db, ctx, checkin, remaining)
        return _meals_or_done(db, ctx, checkin, now)
    if checkin.step == MEALS_STEP:
        return _meals_or_done(db, ctx, checkin, now)
    if checkin.step == NOTE:
        return [_say(ctx, "note_ask")]
    return _reopen_or(db, ctx, checkin, now, _say(ctx, "anything_else"))


# ---------- public API ----------

def _cap_messages(msgs: list[str]) -> list[str]:
    """At most two bubbles per turn: the answer in one bubble, the step's next question in the other.

    An answer is built as one short line per category (taken, due now, each later time, any time), and every
    new bot line becomes its own bubble that the voice reads on its own. Many such lines read as a wall of
    bubbles all speaking at once. Join the answer into a single bubble and keep only the last line, the
    follow-up question, apart. A "here is the photo" line leads the joined bubble so its photos still show
    (shows_photos matches that text at the start of the bubble)."""
    if len(msgs) <= 2:
        return msgs
    answer, question = msgs[:-1], msgs[-1]
    answer.sort(key=lambda text: not shows_photos(text))  # photo line first; sort is stable, so the rest keep order
    return ["\n".join(answer), question]


def _turn(db: Session, ctx: ParentContext, checkin: HealthCheckin, msgs: list[str]) -> Turn:
    msgs = _cap_messages(msgs)
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
        return _ask_medicines(db, ctx, checkin, remaining)
    due = meals_due(db, ctx.profile, now)
    if due:
        _set_step(db, ctx, checkin, MEALS_STEP, now)
        return [_meal_question(ctx, due)]
    return [otherwise]


def conversation(db: Session, checkin: HealthCheckin) -> list[ChatMessage]:
    """The check-in's stored messages, oldest first (by sequence number; timestamp and id only break ties)."""
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.checkin_id == checkin.id)
        .order_by(ChatMessage.seq, ChatMessage.created_at, ChatMessage.id)
    )
    return list(db.execute(stmt).scalars())


def _bot_texts_since_parent(history: list[ChatMessage]) -> list[str]:
    out: list[str] = []
    for m in reversed(history):
        if m.sender == "parent":
            break
        out.append(m.text)
    return out


def _resume(
    db: Session, ctx: ParentContext, checkin: HealthCheckin, history: list[ChatMessage], now: datetime
) -> Turn:
    msgs: list[str] = []
    if checkin.step in (NOTE, DONE, MEDICINES):
        remaining = _remaining(db, ctx, now)
        if checkin.step in (NOTE, DONE) and remaining:
            _set_step(db, ctx, checkin, MEDICINES, now)
            msgs = _ask_medicines(db, ctx, checkin, remaining)
        elif checkin.step == MEDICINES and remaining:
            asked = _bot_texts_since_parent(history)
            if any(not any(d.name in t for t in asked) for d in _unique(remaining)):
                msgs = _ask_medicines(db, ctx, checkin, remaining)
    if not msgs and checkin.step in (NOTE, DONE, MEALS_STEP):
        due = meals_due(db, ctx.profile, now)
        if due:
            question = _meal_question(ctx, due)
            if question not in _bot_texts_since_parent(history):
                _set_step(db, ctx, checkin, MEALS_STEP, now)
                msgs = [question]
    if msgs:
        return _turn(db, ctx, checkin, msgs)
    number = call_number(db, ctx) if checkin.urgent else None
    return Turn(checkin=checkin, bot_messages=[], call_number=number, urgent=bool(checkin.urgent))


# A second "open" this soon after a new conversation started, with nothing said yet, is the same opening
# (a double page load), not another conversation.
SAME_OPENING = timedelta(seconds=15)


def _next_seq(db: Session, checkin: HealthCheckin) -> int:
    db.flush()
    last = db.execute(select(func.max(ChatMessage.seq)).where(ChatMessage.checkin_id == checkin.id)).scalar()
    return (last or 0) + 1


def current_checkin(db: Session, ctx: ParentContext, now: datetime) -> HealthCheckin | None:
    """Today's check-in, or None when the chat has not been opened today."""
    return _today(db, ctx, now)


def session_messages(db: Session, checkin: HealthCheckin) -> list[ChatMessage]:
    """The messages of the conversation on screen now (from the latest opening of the chat)."""
    history = conversation(db, checkin)
    if checkin.session_seq is None:
        return history
    return [m for m in history if m.seq >= checkin.session_seq]


def _just_opened(db: Session, checkin: HealthCheckin, now: datetime) -> bool:
    shown = session_messages(db, checkin)
    if checkin.session_seq is None or not shown or any(m.sender == "parent" for m in shown):
        return False
    started = _aware(checkin.updated_at)  # set when this conversation was opened (nothing said since)
    return started is not None and _aware(now) - started < SAME_OPENING


def _opening_questions(db: Session, ctx: ParentContext, checkin: HealthCheckin, now: datetime) -> list[str]:
    """What to ask after a greeting: whatever today's check-in is still waiting for."""
    if checkin.step in (GREET, HEALTH):
        _set_step(db, ctx, checkin, HEALTH, now)
        return [_say(ctx, "ask_health")]
    if checkin.step == MEDICINES:
        return _continue_medicines(db, ctx, checkin, now, announce_none=True)
    if checkin.step == MEALS_STEP:
        return _meals_or_done(db, ctx, checkin, now)
    if checkin.step == APPOINTMENTS:
        return _appointments_and_done(db, ctx, checkin, now)
    return _reopen_or(db, ctx, checkin, now, _say(ctx, "note_ask" if checkin.step == NOTE else "anything_else"))


def start_new_session(db: Session, ctx: ParentContext, now: datetime, force: bool = False) -> Turn:
    """The parent opened the chat: start a new conversation on screen with a greeting and today's open question.
    Answers already saved today are kept, so nothing answered is asked again. force: also when the chat was opened a moment ago (the language changed)."""
    checkin = _get_or_create(db, ctx, now)
    if not force and _just_opened(db, checkin, now):
        number = call_number(db, ctx) if checkin.urgent else None
        return Turn(checkin=checkin, bot_messages=[], call_number=number, urgent=bool(checkin.urgent))
    checkin.pending_medicine_id = None  # questions from an earlier opening are asked afresh below
    checkin.session_seq = _next_seq(db, checkin)
    checkin.updated_at = now
    msgs = [_greeting(ctx, now)] + _opening_questions(db, ctx, checkin, now)
    return _turn(db, ctx, checkin, msgs)


def start_or_resume(db: Session, ctx: ParentContext, now: datetime) -> Turn:
    """Open today's check-in. Greets only while the conversation has no stored messages.

    After that a resume stores nothing unless a question is newly needed: from "done" when doses are due
    again, or in "medicines" when a due dose has not been asked about since the parent's last message.
    Turn.bot_messages holds only the messages this call added (possibly none).
    """
    checkin = _get_or_create(db, ctx, now)
    history = conversation(db, checkin)
    if history:
        return _resume(db, ctx, checkin, history, now)
    checkin.session_seq = _next_seq(db, checkin)
    msgs = [_greeting(ctx, now)]
    if checkin.step in (GREET, HEALTH):
        _set_step(db, ctx, checkin, HEALTH, now)
        msgs.append(_say(ctx, "ask_health"))
    elif checkin.step == MEDICINES:
        msgs += _continue_medicines(db, ctx, checkin, now, announce_none=True)
    elif checkin.step == MEALS_STEP:
        msgs += _meals_or_done(db, ctx, checkin, now)
    elif checkin.step == APPOINTMENTS:
        msgs += _appointments_and_done(db, ctx, checkin, now)
    else:
        msgs += _reopen_or(db, ctx, checkin, now, _say(ctx, "note_ask" if checkin.step == NOTE else "anything_else"))
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

    if not is_urgent(text):
        # "Send me the photo of my vitamin D3": show it; record and share nothing.
        offer_reply = _answer_photo_offer(db, ctx, checkin, text, now)
        if offer_reply is not None:
            return _turn(db, ctx, checkin, offer_reply)
        medicine_help = _medicine_help(db, ctx, checkin, text, now)
        if medicine_help is not None:
            return _turn(db, ctx, checkin, medicine_help + _after_question(db, ctx, checkin, now))

    if is_medicine_question(text) and not is_urgent(text):
        # A question about today's medicines: answer it from the database; record and share nothing.
        # If the parent named a part of the day ("the morning medicine"), narrow the answer to it.
        part = named_day_part(text)
        return _turn(db, ctx, checkin,
                     _schedule_answer(db, ctx, now, part=part) + _after_question(db, ctx, checkin, now))

    if checkin.step == HEALTH:
        checkin.health_text = text
        msgs = [_share_health(db, ctx, checkin, text, now)]
        _set_step(db, ctx, checkin, MEDICINES, now)
        msgs += _continue_medicines(db, ctx, checkin, now, announce_none=True)
    elif checkin.step in (MEDICINES, MEALS_STEP, APPOINTMENTS):
        # Urgent words are acted on in every step; the current step then carries on with the same text.
        msgs = []
        urgent = is_urgent(text)
        if urgent:
            checkin.health_text = f"{checkin.health_text}\n{text}" if checkin.health_text else text
            msgs.append(_urgent(db, ctx, checkin, text, now))
        if checkin.step == MEDICINES:
            msgs += _handle_medicines(db, ctx, checkin, text, now)
        elif checkin.step == MEALS_STEP:
            # An urgent message is not a meal answer: ask the meal question again after the alert.
            msgs += _meals_or_done(db, ctx, checkin, now) if urgent else _handle_meals(db, ctx, checkin, text, now)
        else:
            msgs += _appointments_and_done(db, ctx, checkin, now)
    elif is_dose_report(text) and not is_urgent(text) and _remaining(db, ctx, now, volunteered=True):
        # "I took my evening tablets" after the check-in finished: record the current dose (asking how many
        # first if several are due), not a health note.
        _set_step(db, ctx, checkin, MEDICINES, now)
        msgs = _handle_medicines(db, ctx, checkin, text, now,
                                 remaining=_remaining(db, ctx, now, volunteered=True), from_done=True)
    elif checkin.step == NOTE:
        msgs = _handle_note(db, ctx, checkin, text, now)
    elif is_closing(text) and not is_urgent(text):
        msgs = _reopen_or(db, ctx, checkin, now, _say(ctx, "goodbye", name=ctx.greeting_name))
    else:
        checkin.health_text = f"{checkin.health_text}\n{text}" if checkin.health_text else text
        msgs = [_share_health(db, ctx, checkin, text, now)]
        if is_bare_confusion(text):  # how they feel, or the medicines: cover both
            msgs += [_say(ctx, "confused_help"), *_schedule_answer(db, ctx, now)]
        msgs += _reopen_or(db, ctx, checkin, now, _say(ctx, "anything_else"))
    return _turn(db, ctx, checkin, msgs)

# ---------- emergency button ----------

def raise_emergency(db: Session, ctx: ParentContext, now: datetime) -> list[str]:
    """Help -> "Yes, it's an emergency": mark today urgent, alert the family, note it in the chat.
    Returns the names of the family members alerted."""
    checkin = _get_or_create(db, ctx, now)
    checkin.urgent = True
    checkin.updated_at = now
    note_emergency(db, ctx, checkin, EMERGENCY_TEXT, "button", now)
    users = notify_family_emergency(db, ctx, checkin)
    log_activity(db, ctx.family_id, ctx.user_id, "checkin.emergency", "health_checkin", checkin.id, {})
    _store(db, ctx, checkin, "bot", [_say(ctx, "emergency_logged" if users else "health_urgent_alone")])
    db.commit()
    return [u.display_name or u.email for u in users]
