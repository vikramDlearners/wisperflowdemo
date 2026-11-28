"""The parent's plan for today: tablets, doctor visits and tasks, plus medicines running low and what to tell
the doctor before a visit.

Tablet stock is an estimate. The family records a count (`Medicine.quantity_remaining`) and nothing lowers it,
so we take away the doses marked taken since that count was saved. A medicine is low when about
LOW_TABLETS or fewer are left, or when its refill date is REFILL_DAYS away or closer.

When the parent says yes to a refill, `ask_refill` makes a task for the person who looks after that medicine
(else the first other member) and tells the family. It is recorded in refill_requests, so asking twice does
nothing until the family saves a new count.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.errors import NotFound
from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.models.checkin import HealthCheckin
from app.models.dose import MedicineDose
from app.models.health_note import HealthNote
from app.models.medicine import Medicine
from app.models.refill_request import RefillRequest
from app.models.task import Task
from app.models.user import User
from app.services import family_alerts
from app.services.activity import log_activity
from app.services.doses import _aware, doses_today, local_now, today_for
from app.services.notifications import notify
from app.services.parent_context import ParentContext

LOW_TABLETS = 7
REFILL_DAYS = 3
PREP_DAYS = 2
LOOK_BACK_DAYS = 14
HIGH_BP = 140
HIGH_SUGAR = 180
FINE_WORDS = ("fine", "good", "ok", "okay", "well", "nothing", "no problem", "all good")


@dataclass
class Dose:
    medicine_id: str
    name: str
    time: str
    status: str


@dataclass
class Visit:
    id: str
    day: date
    time: str
    provider: str
    reason: str
    location: str | None


@dataclass
class Refill:
    medicine_id: str
    name: str
    left: int | None
    refill_date: date | None
    ask_name: str | None
    asked: bool


@dataclass
class Point:
    """One thing to tell the doctor. `kind` is bp_high, sugar_high, missed, said or allergy."""

    kind: str
    count: int = 0
    value: str | None = None


@dataclass
class Birthday:
    name: str
    phone: str | None
    today: bool


@dataclass
class TodayPlan:
    day: date
    doses: list[Dose] = field(default_factory=list)
    visits: list[Visit] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    refills: list[Refill] = field(default_factory=list)
    visit_points: list[Point] = field(default_factory=list)
    birthdays: list[Birthday] = field(default_factory=list)


def _local_clock(profile: CareProfile, dt: datetime) -> str:
    return local_now(profile, _aware(dt)).strftime("%H:%M")


def tablets_left(db: Session, medicine: Medicine) -> int | None:
    if medicine.quantity_remaining is None:
        return None
    since = _aware(medicine.updated_at)
    taken = db.execute(
        select(func.count()).select_from(MedicineDose).where(
            MedicineDose.medicine_id == medicine.id, MedicineDose.status == "taken",
            MedicineDose.recorded_at > since,
        )
    ).scalar_one()
    return max(medicine.quantity_remaining - taken, 0)


def _asker(db: Session, medicine: Medicine, family_id: str, parent_user_id: str | None) -> User | None:
    if medicine.responsible_user_id and medicine.responsible_user_id != parent_user_id:
        user = db.get(User, medicine.responsible_user_id)
        if user is not None:
            return user
    others = family_alerts._members_except(db, family_id, parent_user_id)
    return others[0] if others else None


def _open_request(db: Session, medicine: Medicine) -> RefillRequest | None:
    since = _aware(medicine.updated_at)
    rows = db.execute(
        select(RefillRequest).where(RefillRequest.medicine_id == medicine.id)
        .order_by(RefillRequest.created_at.desc())
    ).scalars().all()
    return next((r for r in rows if _aware(r.created_at) >= since), None)


def refills(db: Session, profile: CareProfile, now: datetime, parent_user_id: str | None) -> list[Refill]:
    today = today_for(profile, now)
    found = []
    medicines = db.execute(
        select(Medicine).where(Medicine.care_profile_id == profile.id, Medicine.active.is_(True))
        .order_by(Medicine.display_name)
    ).scalars().all()
    for m in medicines:
        left = tablets_left(db, m)
        low = left is not None and left <= LOW_TABLETS
        due = m.refill_date is not None and m.refill_date <= today + timedelta(days=REFILL_DAYS)
        if not (low or due):
            continue
        asker = _asker(db, m, profile.family_id, parent_user_id)
        found.append(Refill(m.id, m.display_name, left, m.refill_date, asker.display_name if asker else None,
                            _open_request(db, m) is not None))
    return found


def _said(text: str) -> bool:
    words = text.strip().lower()
    return bool(words) and not any(words == w or words.startswith(w + " ") or words.startswith(w + ",")
                                   for w in FINE_WORDS)


def visit_points(db: Session, profile: CareProfile, now: datetime) -> list[Point]:
    """What to tell the doctor, from the last two weeks."""
    since = now - timedelta(days=LOOK_BACK_DAYS)
    points: list[Point] = []
    notes = db.execute(
        select(HealthNote).where(
            HealthNote.care_profile_id == profile.id, HealthNote.kind == "reading",
            HealthNote.label.in_(("bp", "sugar")), HealthNote.recorded_at >= since,
        ).order_by(HealthNote.recorded_at)
    ).scalars().all()
    for label, kind, limit in (("bp", "bp_high", HIGH_BP), ("sugar", "sugar_high", HIGH_SUGAR)):
        high = [n for n in notes if n.label == label and
                ((n.value_num is not None and n.value_num >= limit) or n.value == "high")]
        days = {local_now(profile, _aware(n.recorded_at)).date() for n in high}
        if days:
            points.append(Point(kind, len(days), high[-1].value))

    start = today_for(profile, now) - timedelta(days=LOOK_BACK_DAYS)
    said = db.execute(
        select(HealthCheckin.health_text).where(
            HealthCheckin.care_profile_id == profile.id, HealthCheckin.checkin_date >= start,
            HealthCheckin.health_text.is_not(None),
        ).order_by(HealthCheckin.checkin_date.desc())
    ).scalars().all()
    for text in [t for t in said if _said(t)][:3]:
        points.append(Point("said", value=text.strip()))

    missed = db.execute(
        select(Medicine.display_name, func.count()).select_from(MedicineDose)
        .join(Medicine, Medicine.id == MedicineDose.medicine_id)
        .where(MedicineDose.care_profile_id == profile.id, MedicineDose.dose_date >= start,
               MedicineDose.status.in_(("missed", "not_taken")))
        .group_by(Medicine.display_name).order_by(func.count().desc())
    ).all()
    for name, count in missed:
        points.append(Point("missed", count, name))

    allergies = db.execute(
        select(HealthNote.label).where(
            HealthNote.care_profile_id == profile.id, HealthNote.kind == "allergy", HealthNote.active.is_(True),
        ).order_by(HealthNote.label)
    ).scalars().all()
    if allergies:
        points.append(Point("allergy", len(allergies), ", ".join(allergies)))
    return points


def today(db: Session, ctx: ParentContext, now: datetime) -> TodayPlan:
    profile = ctx.profile
    day = today_for(profile, now)
    plan = TodayPlan(day)
    plan.doses = [
        Dose(d.medicine_id, d.name, _local_clock(profile, d.due_at) if d.due_at else d.slot, d.status)
        for d in doses_today(db, profile, now)
    ]
    plan.doses.sort(key=lambda d: d.time)
    visits = db.execute(
        select(Appointment).where(
            Appointment.care_profile_id == profile.id, Appointment.scheduled_date >= day,
            Appointment.scheduled_date <= day + timedelta(days=PREP_DAYS),
            Appointment.status.in_(("scheduled", "rescheduled")),
        ).order_by(Appointment.scheduled_date, Appointment.start_time)
    ).scalars().all()
    plan.visits = [Visit(a.id, a.scheduled_date, a.start_time, a.provider, a.reason, a.location) for a in visits]
    tz_end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=local_now(profile, now).tzinfo)
    plan.tasks = list(db.execute(
        select(Task.title).where(
            Task.care_profile_id == profile.id, Task.status != "DONE", Task.due_at.is_not(None),
            Task.due_at < tz_end, Task.assigned_to_user_id == ctx.user_id,
        ).order_by(Task.due_at)
    ).scalars())
    plan.refills = refills(db, profile, now, ctx.user_id)
    if plan.visits:
        plan.visit_points = visit_points(db, profile, now)
    from app.services.care_circle import birthdays  # care_circle imports doses and family_alerts

    plan.birthdays = [Birthday(c.name, c.phone, d == day) for c, d in birthdays(db, profile.id, day)]
    return plan


def ask_refill(db: Session, ctx: ParentContext, medicine_id: str, now: datetime) -> Refill:
    """The parent said yes: make one task to order this medicine and tell the family. Safe to repeat."""
    medicine = db.get(Medicine, medicine_id)
    if medicine is None or medicine.care_profile_id != ctx.profile.id:
        raise NotFound("Medicine not found")
    asker = _asker(db, medicine, ctx.family_id, ctx.user_id)
    left = tablets_left(db, medicine)
    if _open_request(db, medicine) is None:
        parent = ctx.profile.display_name
        title = f"Order {medicine.display_name} for {parent}"
        detail = f"{parent} asked for a refill." + (f" About {left} tablets left." if left is not None else "")
        task = Task(family_id=ctx.family_id, care_profile_id=ctx.profile.id, title=title, description=detail,
                    assigned_to_user_id=asker.id if asker else None, due_at=now + timedelta(days=1),
                    priority="high", created_by_user_id=ctx.user_id)
        db.add(task)
        db.flush()
        db.add(RefillRequest(family_id=ctx.family_id, care_profile_id=ctx.profile.id, medicine_id=medicine.id,
                             tablets_left=left, asked_user_id=asker.id if asker else None, task_id=task.id,
                             created_at=now))
        log_activity(db, ctx.family_id, ctx.user_id, "task.created", "task", task.id, {"title": title})
        payload = {"care_profile_id": ctx.profile.id, "parent_name": parent, "medicine": medicine.display_name,
                   "left": left, "task_id": task.id, "asked_name": asker.display_name if asker else None}
        for member in family_alerts._members_except(db, ctx.family_id, ctx.user_id):
            notify(db, member.id, "refill.requested", family_id=ctx.family_id, payload=payload)
        db.commit()
    return Refill(medicine.id, medicine.display_name, left, medicine.refill_date,
                  asker.display_name if asker else None, True)
