"""Family alerts from the parent check-in: in-app notifications and emails.

Immediate alerts (notify_family_*) stage notifications; the caller commits.
Scheduled jobs (send_daily_summaries, alert_missed_doses) commit themselves, then email.
The parent never alerts themselves.
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.models.checkin import HealthCheckin
from app.models.dose import MedicineDose
from app.models.medicine import Medicine
from app.models.membership import FamilyMember
from app.models.user import User
from app.services.adapters.messaging import get_email_provider
from app.services.doses import ANY_SLOT, DueDose, _aware, doses_today, local_now, logged_today, today_for
from app.services.notifications import notify
from app.services.parent_context import ParentContext
from app.services.reminders import list_reminder_times

logger = logging.getLogger(__name__)

MISSED_AFTER = timedelta(minutes=60)
SUMMARY_LOCAL_HOUR = 20
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


def other_members(db: Session, ctx: ParentContext) -> list[User]:
    """Active family members except the parent."""
    return [u for u in family_recipients(db, ctx.family_id) if u.id != ctx.user_id]


def _payload(ctx: ParentContext, checkin: HealthCheckin, text: str | None) -> dict:
    return {
        "checkin_id": checkin.id,
        "care_profile_id": ctx.profile.id,
        "parent_name": ctx.profile.display_name,
        "text": text,
    }


def _email(users: list[User], subject: str, body: str) -> None:
    provider = get_email_provider()
    for user in users:
        if user.email:
            provider.send(user.email, subject, body)


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

def _members_except(db: Session, family_id: str, parent_user_id: str | None) -> list[User]:
    return [u for u in family_recipients(db, family_id) if u.id != parent_user_id]


def _email_each(users: list[User], subject: str, body: str) -> None:
    """Like _email, but a failed send is logged and does not stop the others (jobs email after committing)."""
    provider = get_email_provider()
    for user in users:
        if not user.email:
            continue
        try:
            provider.send(user.email, subject, body)
        except Exception:  # noqa: BLE001 - a background job must not die on one bad address
            logger.exception("Could not email user %s: %s", user.id, subject)


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
        groups[status.get((med_id, slot)) or "not_taken"].append(f"{names[med_id]} ({_slot_label(slot)})")
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


def _summary_body(db: Session, checkin: HealthCheckin, profile: CareProfile) -> str:
    name = profile.display_name
    parts = [
        f"Check-in summary for {name} on {checkin.checkin_date.strftime('%d %b %Y')}.",
        "",
        f"How {name} is feeling:",
        f'"{checkin.health_text}"' if checkin.health_text else f"{name} did not answer this today.",
    ]
    if checkin.urgent:
        parts.append(f"{name} reported something that needed attention today.")
    parts += ["", "Medicines:", *_dose_lines(db, profile, checkin.checkin_date)]
    parts += ["", "Appointments reminded:", *_appointment_lines(db, profile, checkin.checkin_date)]
    return "\n".join(parts)


def send_daily_summaries(db: Session, now: datetime) -> int:
    """Email each family member except the parent one summary per unsent check-in; returns check-ins summarised.

    A check-in is due once its local day is over, or on its own day from 20:00 local time.
    """
    now = _aware(now)
    pending = db.execute(
        select(HealthCheckin)
        .where(HealthCheckin.summary_sent_at.is_(None))
        .order_by(HealthCheckin.checkin_date, HealthCheckin.id)
    ).scalars().all()
    sent = 0
    for checkin in pending:
        profile = db.get(CareProfile, checkin.care_profile_id)
        if profile is None:
            continue
        local = local_now(profile, now)
        if checkin.checkin_date > local.date():
            continue
        if checkin.checkin_date == local.date() and local.hour < SUMMARY_LOCAL_HOUR:
            continue
        subject = f"Today's check-in with {profile.display_name}"
        body = _summary_body(db, checkin, profile)
        users = _members_except(db, checkin.family_id, checkin.parent_user_id)
        # Mark sent before emailing, so a crash mid-send can never repeat the summary.
        checkin.summary_sent_at = now
        db.commit()
        _email_each(users, subject, body)
        sent += 1
    return sent


def alert_missed_doses(db: Session, now: datetime) -> int:
    """Alert the family (in-app + email) once per timed dose slot still not taken 60 min after it was due,
    or after the reminder the parent asked for. Skipped doses count as answered. Returns slots alerted.
    """
    now = _aware(now)
    total = 0
    for profile in db.execute(select(CareProfile)).scalars().all():
        logged = logged_today(db, profile, now)
        missed: list[tuple[DueDose, MedicineDose | None]] = []
        for dose in doses_today(db, profile, now):
            if dose.due_at is None or dose.status in ("taken", "skipped"):
                continue
            row = logged.get((dose.medicine_id, dose.slot))
            if row is not None and row.family_alerted_at is not None:
                continue
            deadline = _aware(row.remind_at) if row is not None and row.remind_at is not None else dose.due_at
            if now < deadline + MISSED_AFTER:
                continue
            missed.append((dose, row))
        if not missed:
            continue
        users = _members_except(db, profile.family_id, profile.linked_user_id)
        name = profile.display_name
        for dose, row in missed:
            if row is None:
                row = MedicineDose(
                    family_id=profile.family_id, care_profile_id=profile.id, medicine_id=dose.medicine_id,
                    dose_date=today_for(profile, now), slot=dose.slot, status="not_taken",
                    recorded_at=now, source="chatbot",
                )
                db.add(row)
            row.family_alerted_at = now
            payload = {
                "care_profile_id": profile.id,
                "parent_name": name,
                "medicine_id": dose.medicine_id,
                "medicine_name": dose.name,
                "slot": dose.slot,
            }
            for user in users:
                notify(db, user.id, "medicine.missed", family_id=profile.family_id, payload=payload)
        # Mark alerted before emailing, so a crash mid-send can never repeat the alert.
        db.commit()
        for dose, _ in missed:
            _email_each(
                users,
                f"Medicine not taken: {name} - {dose.name}",
                f"{name} has not taken {dose.name} (due at {dose.slot}) today. Please check in with {name}.",
            )
            total += 1
    return total
