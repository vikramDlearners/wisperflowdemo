"""Family alerts from the parent check-in: in-app notifications and emails.

Immediate alerts (notify_family_*) stage notifications; the caller commits.
Scheduled jobs (send_daily_summaries, alert_missed_doses) commit themselves, then email. Each send is claimed
first with a conditional UPDATE (or a unique insert), so several workers never send the same thing twice.
Only care profiles with a linked chatbot parent get scheduled alerts and summaries.
The parent never alerts themselves.
"""

import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.models.checkin import ChatMessage, HealthCheckin
from app.models.dose import MedicineDose
from app.models.medicine import Medicine
from app.models.membership import FamilyMember
from app.models.prescription_scan import MedicineReminder
from app.models.user import User
from app.services.adapters.messaging import get_email_provider
from app.services.doses import (
    ANY_SLOT,
    MISSED,
    SYSTEM_SOURCE,
    DueDose,
    _aware,
    doses_today,
    local_now,
    logged_today,
    today_for,
)
from app.services.notifications import notify
from app.services.parent_context import ParentContext
from app.services.reminders import list_reminder_times

logger = logging.getLogger(__name__)

MISSED_AFTER = timedelta(minutes=60)
SUMMARY_LOCAL_HOUR = 20  # a finished ("done") check-in is summarised from 20:00 local time
END_OF_DAY = time(23, 30)  # any other day is summarised at the first run on or after 23:30 local time
DONE_STEP = "done"
UPCOMING_STATUSES = ("scheduled", "rescheduled")


def family_recipients(db: Session, family_id: str) -> list[User]:
    """All active members of the family, ordered by display name."""
    return list(
        db.execute(
            select(User)
            .join(FamilyMember, FamilyMember.user_id == User.id)
            .where(FamilyMember.family_id == family_id, FamilyMember.status == "active")
            .order_by(User.display_name, User.id)
        ).scalars()
    )


def _members_except(db: Session, family_id: str, parent_user_id: str | None) -> list[User]:
    return [u for u in family_recipients(db, family_id) if u.id != parent_user_id]


def other_members(db: Session, ctx: ParentContext) -> list[User]:
    """Active family members except the parent."""
    return _members_except(db, ctx.family_id, ctx.user_id)


def _payload(ctx: ParentContext, checkin: HealthCheckin, text: str | None) -> dict:
    return {
        "checkin_id": checkin.id,
        "care_profile_id": ctx.profile.id,
        "parent_name": ctx.profile.display_name,
        "text": text,
    }


def _email(users: list[User], subject: str, body: str) -> None:
    """Send one email per member that has an address; a failed send is logged and the rest still go."""
    provider = get_email_provider()
    for user in users:
        if not user.email:
            continue
        try:
            provider.send(user.email, subject, body)
        except Exception:  # noqa: BLE001 - one bad address must not stop the others
            logger.exception("Could not email user %s: %s", user.id, subject)


def notify_family_update(db: Session, ctx: ParentContext, checkin: HealthCheckin) -> None:
    for user in other_members(db, ctx):
        notify(db, user.id, "checkin.update", family_id=ctx.family_id,
               payload=_payload(ctx, checkin, checkin.health_text))


def notify_family_urgent(db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str) -> None:
    users = other_members(db, ctx)
    for user in users:
        notify(db, user.id, "checkin.urgent", family_id=ctx.family_id, payload=_payload(ctx, checkin, text))
    name = ctx.profile.display_name
    _email(
        users,
        f"Needs attention now: {name}",
        f"{name} said during today's check-in:\n\n\"{text}\"\n\nPlease contact {name} as soon as you can.",
    )


def notify_family_finished(db: Session, ctx: ParentContext, medicine: DueDose) -> None:
    users = other_members(db, ctx)
    payload = {
        "care_profile_id": ctx.profile.id,
        "parent_name": ctx.profile.display_name,
        "medicine_id": medicine.medicine_id,
        "medicine_name": medicine.name,
    }
    for user in users:
        notify(db, user.id, "medicine.finished", family_id=ctx.family_id, payload=payload)
    name = ctx.profile.display_name
    _email(
        users,
        f"{name}'s medicine has run out: {medicine.name}",
        f"{name} said during today's check-in that {medicine.name} has run out. Please arrange a refill.",
    )


# ---------- scheduled jobs ----------

def _slot_label(slot: str) -> str:
    return "any time" if slot == ANY_SLOT else slot


def _dose_lines(db: Session, profile: CareProfile, day: date) -> list[str]:
    rows = db.execute(
        select(MedicineDose).where(MedicineDose.care_profile_id == profile.id, MedicineDose.dose_date == day)
    ).scalars()
    status = {(r.medicine_id, r.slot): r.status for r in rows}
    medicines = db.execute(
        select(Medicine)
        .where(Medicine.care_profile_id == profile.id, Medicine.active.is_(True))
        .order_by(Medicine.created_at, Medicine.id)
    ).scalars()
    keys: list[tuple[str, str]] = []
    names: dict[str, str] = {}
    for med in medicines:
        names[med.id] = med.display_name
        keys += [(med.id, slot) for slot in list_reminder_times(db, med.id) or [ANY_SLOT]]
    for key in status:  # doses logged for a medicine that has since been stopped or re-timed
        if key not in keys:
            keys.append(key)
            if key[0] not in names:
                med = db.get(Medicine, key[0])
                names[key[0]] = med.display_name if med else "Unknown medicine"
    if not keys:
        return ["No medicines were scheduled."]
    groups: dict[str, list[str]] = {"taken": [], "not_taken": [], "skipped": []}
    for med_id, slot in keys:
        group = status.get((med_id, slot))
        group = group if group in groups else "not_taken"  # unanswered and "missed" read as not taken
        groups[group].append(f"{names[med_id]} ({_slot_label(slot)})")
    lines = [
        f"Taken: {', '.join(groups['taken']) or 'none'}",
        f"Not taken: {', '.join(groups['not_taken']) or 'none'}",
    ]
    if groups["skipped"]:
        lines.append(f"Skipped: {', '.join(groups['skipped'])}")
    return lines


def _appointment_lines(db: Session, profile: CareProfile, day: date) -> list[str]:
    from app.services.checkin import format_time  # local import: checkin imports this module

    appts = db.execute(
        select(Appointment)
        .where(
            Appointment.care_profile_id == profile.id,
            Appointment.scheduled_date.in_((day, day + timedelta(days=1))),
            Appointment.status.in_(UPCOMING_STATUSES),
        )
        .order_by(Appointment.scheduled_date, Appointment.start_time)
    ).scalars()
    lines = [
        f"- {a.scheduled_date.strftime('%d %b %Y')} at {format_time(a.start_time)}: {a.reason} with {a.provider}"
        for a in appts
    ]
    return lines or ["None"]


def _parent_spoke(db: Session, checkin: HealthCheckin) -> bool:
    return bool(db.execute(
        select(exists().where(ChatMessage.checkin_id == checkin.id, ChatMessage.sender == "parent"))
    ).scalar())


def _no_checkin(db: Session, checkin: HealthCheckin) -> bool:
    return not checkin.health_text and not _parent_spoke(db, checkin)


def _summary_body(db: Session, checkin: HealthCheckin, profile: CareProfile) -> str:
    name = profile.display_name
    parts = [f"Check-in summary for {name} on {checkin.checkin_date.strftime('%d %b %Y')}.", ""]
    if _no_checkin(db, checkin):
        parts.append(f"No check-in today: {name} did not talk to the assistant on this day.")
    else:
        parts += [
            f"How {name} is feeling:",
            f'"{checkin.health_text}"' if checkin.health_text else f"{name} did not answer this today.",
        ]
    if checkin.urgent:
        parts.append(f"{name} reported something that needed attention today.")
    parts += ["", "Medicines:", *_dose_lines(db, profile, checkin.checkin_date)]
    parts += ["", "Appointments reminded:", *_appointment_lines(db, profile, checkin.checkin_date)]
    return "\n".join(parts)


def _ensure_day_rows(db: Session, now: datetime) -> None:
    """Give a linked profile's day without a check-in an empty check-in row, so it still gets a summary.

    Covers today once it is END_OF_DAY local time, and yesterday (a run missed at the end of the day is caught
    up the next day). Older days and days before the profile existed are left alone.
    """
    profiles = db.execute(
        select(CareProfile).where(CareProfile.linked_user_id.is_not(None)).order_by(CareProfile.id)
    ).scalars().all()
    for profile in profiles:
        try:
            local = local_now(profile, now)
            days = [local.date() - timedelta(days=1)] + ([local.date()] if local.time() >= END_OF_DAY else [])
            first_day = local_now(profile, _aware(profile.created_at)).date() if profile.created_at else None
            for day in days:
                if first_day is not None and day < first_day:
                    continue
                found = db.execute(select(HealthCheckin.id).where(
                    HealthCheckin.care_profile_id == profile.id, HealthCheckin.checkin_date == day
                )).first()
                if found is not None:
                    continue
                db.add(HealthCheckin(
                    family_id=profile.family_id, care_profile_id=profile.id, parent_user_id=profile.linked_user_id,
                    checkin_date=day, step="greet", urgent=False, started_at=now, updated_at=now,
                ))
                try:
                    db.commit()
                except IntegrityError:  # the parent (or another worker) created it first
                    db.rollback()
        except Exception:  # noqa: BLE001 - one bad profile must not block every later one
            db.rollback()
            logger.exception("Could not prepare the daily summary for care profile %s", profile.id)


def send_daily_summaries(db: Session, now: datetime) -> int:
    """Email each family member except the parent one summary per unsent check-in; returns check-ins summarised.

    Linked profiles only. A day with no check-in gets an empty check-in row first ("No check-in today").
    A finished check-in is due from 20:00 local time on its own day; any other day is due at the first run on
    or after 23:30 local time, or on any later run once the day is over.
    """
    now = _aware(now)
    _ensure_day_rows(db, now)
    pending_ids = list(db.execute(
        select(HealthCheckin.id)
        .where(HealthCheckin.summary_sent_at.is_(None))
        .order_by(HealthCheckin.checkin_date, HealthCheckin.id)
    ).scalars())
    sent = 0
    for checkin_id in pending_ids:
        try:
            sent += _summarise(db, checkin_id, now)
        except Exception:  # noqa: BLE001 - one bad check-in must not block every later one
            db.rollback()
            logger.exception("Daily summary failed for check-in %s", checkin_id)
    return sent


def _summarise(db: Session, checkin_id: str, now: datetime) -> int:
    checkin = db.get(HealthCheckin, checkin_id)
    if checkin is None or checkin.summary_sent_at is not None:
        return 0
    profile = db.get(CareProfile, checkin.care_profile_id)
    if profile is None or profile.linked_user_id is None:
        return 0
    local = local_now(profile, now)
    if checkin.checkin_date > local.date():
        return 0
    if checkin.checkin_date == local.date():
        finished = checkin.step == DONE_STEP and local.hour >= SUMMARY_LOCAL_HOUR
        if not finished and local.time() < END_OF_DAY:
            return 0
    name = profile.display_name
    subject = f"No check-in today with {name}" if _no_checkin(db, checkin) else f"Today's check-in with {name}"
    body = _summary_body(db, checkin, profile)
    users = _members_except(db, checkin.family_id, checkin.parent_user_id)
    # Claim the summary before emailing: only the run whose conditional UPDATE marks it sends it, and a crash
    # mid-send can never repeat it.
    claimed = db.execute(
        update(HealthCheckin)
        .where(HealthCheckin.id == checkin.id, HealthCheckin.summary_sent_at.is_(None))
        .values(summary_sent_at=now)
    ).rowcount
    db.commit()
    if claimed != 1:
        return 0
    _email(users, subject, body)
    return 1


def alert_missed_doses(db: Session, now: datetime) -> int:
    """Alert the family (in-app + email) once per timed dose slot still not taken 60 min after it was due,
    or after the reminder the parent asked for. Skipped doses count as answered. Returns slots alerted.
    """
    now = _aware(now)
    profile_ids = list(db.execute(select(CareProfile.id).order_by(CareProfile.created_at, CareProfile.id)).scalars())
    total = 0
    for profile_id in profile_ids:
        try:
            total += _alert_profile(db, profile_id, now)
        except Exception:  # noqa: BLE001 - one bad profile must not block every later one
            db.rollback()
            logger.exception("Missed-dose check failed for care profile %s", profile_id)
    return total


def _slot_since(db: Session, medicine_id: str, slot: str) -> datetime | None:
    """When this medicine's slot started to exist: the later of the medicine's creation and the FIRST reminder
    row ever made for this time. Inactive rows count too: set_reminder_times recreates every row on each edit,
    so re-saving the times later in the day must not hide an earlier slot that existed all along."""
    med = db.get(Medicine, medicine_id)
    reminder_at = db.execute(
        select(func.min(MedicineReminder.created_at))
        .where(MedicineReminder.medicine_id == medicine_id, MedicineReminder.time_of_day == slot)
    ).scalar()
    times = [_aware(t) for t in (med.created_at if med else None, reminder_at) if t is not None]
    return max(times) if times else None


def _claim_missed(db: Session, profile: CareProfile, dose: DueDose, row: MedicineDose | None, now: datetime) -> bool:
    """Mark one dose slot as alerted; True only for the run that marked it.

    A slot nobody answered gets a new "missed" row from the system (the unique slot constraint stops a second
    worker); an answered slot keeps its answer and is claimed with a conditional UPDATE.
    """
    if row is None:
        db.add(MedicineDose(
            family_id=profile.family_id, care_profile_id=profile.id, medicine_id=dose.medicine_id,
            dose_date=today_for(profile, now), slot=dose.slot, status=MISSED, recorded_at=now,
            source=SYSTEM_SOURCE, family_alerted_at=now,
        ))
        try:
            db.flush()
        except IntegrityError:
            return False
        return True
    result = db.execute(
        update(MedicineDose)
        .where(MedicineDose.id == row.id, MedicineDose.family_alerted_at.is_(None))
        .values(family_alerted_at=now)
    )
    return result.rowcount == 1


def _alert_profile(db: Session, profile_id: str, now: datetime) -> int:
    profile = db.get(CareProfile, profile_id)
    if profile is None or profile.linked_user_id is None:
        return 0  # no chatbot parent: nobody is asked, so nothing is "missed"
    logged = logged_today(db, profile, now)
    missed: list[tuple[DueDose, MedicineDose | None]] = []
    for dose in doses_today(db, profile, now):
        if dose.due_at is None or dose.status in ("taken", "skipped"):
            continue
        row = logged.get((dose.medicine_id, dose.slot))
        if row is not None and row.family_alerted_at is not None:
            continue
        since = _slot_since(db, dose.medicine_id, dose.slot)
        if since is not None and dose.due_at < since:
            continue  # the medicine or this reminder time was added after the slot was due
        deadline = _aware(row.remind_at) if row is not None and row.remind_at is not None else dose.due_at
        if now < deadline + MISSED_AFTER:
            continue
        missed.append((dose, row))
    if not missed:
        return 0
    users = _members_except(db, profile.family_id, profile.linked_user_id)
    name = profile.display_name
    alerted: list[DueDose] = []
    for dose, row in missed:
        if not _claim_missed(db, profile, dose, row, now):
            db.rollback()
            continue  # another run alerted this slot
        payload = {
            "care_profile_id": profile.id,
            "parent_name": name,
            "medicine_id": dose.medicine_id,
            "medicine_name": dose.name,
            "slot": dose.slot,
        }
        for user in users:
            notify(db, user.id, "medicine.missed", family_id=profile.family_id, payload=payload)
        # Commit the claim and its notifications before emailing, so a crash mid-send never repeats the alert.
        db.commit()
        alerted.append(dose)
    for dose in alerted:
        _email(
            users,
            f"Medicine not taken: {name} - {dose.name}",
            f"{name} has not taken {dose.name} (due at {dose.slot}) today. Please check in with {name}.",
        )
    return len(alerted)
