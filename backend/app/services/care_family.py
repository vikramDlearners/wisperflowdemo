"""The work a family shares around one parent: costs and visits split between siblings, dated paperwork,
and the live-in helper's day.

Siblings. Every expense is split equally between the "sharers": active members who are not the parent and
not a caregiver. A member's balance is what they paid minus their share, so the balances add up to nothing;
a positive balance is owed to that member. Visits are counted per member for the month, and the last
appointment shows who took the parent (a logged visit for it, else the appointment's responsible member).

Paperwork. Dated chores such as the pension life certificate, the income tax return, bank KYC and property
tax, plus the parent's insurance renewals read from the insurance policies. Marking a yearly chore done adds
next year's.

Carer. A helper ticks off today's meals and medicines and flags a concern; a concern is put in every other
member's notifications.

Viewing needs dashboard.view; changing money, visits and paperwork needs tasks.create; the carer's day needs
medicine_quantity.update, which caregivers and managers have and viewers do not.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.care_circle import CareExpense, CarerReport, CareVisit, PaperworkItem
from app.models.insurance import InsurancePolicy
from app.models.membership import FamilyMember
from app.models.role import Role
from app.models.user import User
from app.services import doses as doses_svc
from app.services.activity import log_activity
from app.services.care_circle import _clean, _profile_in
from app.services.errors import NotFound
from app.services.meals import MEALS, answered_meals, save_meals
from app.services.notifications import notify
from app.services.permissions import require

NOT_SHARERS = {"Parent", "Caregiver"}
CENT = Decimal("0.01")


@dataclass
class Member:
    user_id: str
    name: str
    role: str


def members(db: Session, family_id: str) -> list[Member]:
    rows = db.execute(
        select(FamilyMember.user_id, User.display_name, Role.name)
        .join(User, User.id == FamilyMember.user_id)
        .join(Role, Role.id == FamilyMember.role_id)
        .where(FamilyMember.family_id == family_id, FamilyMember.status == "active")
        .order_by(FamilyMember.created_at)
    ).all()
    return [Member(user_id, name, role) for user_id, name, role in rows]


def _month_start(day: date) -> date:
    return day.replace(day=1)


# ---------- siblings ----------

def add_expense(db: Session, actor_id: str, family_id: str, care_profile_id: str, amount: Decimal, what: str,
                spent_on: date, paid_by_user_id: str | None) -> CareExpense:
    require(db, actor_id, family_id, "tasks.create")
    profile = _profile_in(db, family_id, care_profile_id)
    payer = paid_by_user_id or actor_id
    if payer not in {m.user_id for m in members(db, family_id)}:
        raise ValueError("The payer is not in this family")
    if amount <= 0:
        raise ValueError("Amount must be more than zero")
    what = _clean(what) or ""
    if not what:
        raise ValueError("Say what the money was for")
    row = CareExpense(family_id=family_id, care_profile_id=profile.id, paid_by_user_id=payer,
                      amount=amount.quantize(CENT), what=what[:160], spent_on=spent_on)
    db.add(row)
    db.flush()
    log_activity(db, family_id, actor_id, "care.expense_added", "care_expense", row.id, {"amount": str(row.amount)})
    db.commit()
    return row


def delete_expense(db: Session, actor_id: str, family_id: str, expense_id: str) -> None:
    require(db, actor_id, family_id, "tasks.create")
    row = db.get(CareExpense, expense_id)
    if row is None or row.family_id != family_id:
        raise NotFound("Expense not found")
    db.delete(row)
    log_activity(db, family_id, actor_id, "care.expense_deleted", "care_expense", expense_id, {})
    db.commit()


def add_visit(db: Session, actor_id: str, family_id: str, care_profile_id: str, visit_date: date,
              appointment_id: str | None, note: str | None) -> CareVisit:
    require(db, actor_id, family_id, "tasks.create")
    profile = _profile_in(db, family_id, care_profile_id)
    if appointment_id:
        appt = db.get(Appointment, appointment_id)
        if appt is None or appt.care_profile_id != profile.id:
            raise NotFound("Appointment not found")
    row = CareVisit(family_id=family_id, care_profile_id=profile.id, user_id=actor_id, visit_date=visit_date,
                    appointment_id=appointment_id or None, note=(_clean(note or "") or None))
    db.add(row)
    db.flush()
    log_activity(db, family_id, actor_id, "care.visit_logged", "care_visit", row.id, {})
    db.commit()
    return row


def _last_appointment(db: Session, care_profile_id: str, today: date) -> tuple[Appointment | None, str | None]:
    appt = db.execute(
        select(Appointment)
        .where(Appointment.care_profile_id == care_profile_id, Appointment.scheduled_date <= today,
               Appointment.status != "cancelled")
        .order_by(Appointment.scheduled_date.desc(), Appointment.start_time.desc())
        .limit(1)
    ).scalar_one_or_none()
    if appt is None:
        return None, None
    went = db.execute(
        select(CareVisit.user_id).where(CareVisit.appointment_id == appt.id).order_by(CareVisit.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return appt, went or appt.responsible_user_id


def sharing(db: Session, actor_id: str, family_id: str, care_profile_id: str, today: date) -> dict:
    require(db, actor_id, family_id, "dashboard.view")
    profile = _profile_in(db, family_id, care_profile_id)
    people = members(db, family_id)
    names = {m.user_id: m.name for m in people}
    expenses = list(db.execute(
        select(CareExpense).where(CareExpense.care_profile_id == profile.id)
        .order_by(CareExpense.spent_on.desc(), CareExpense.created_at.desc())
    ).scalars())
    total = sum((e.amount for e in expenses), Decimal(0))
    paid: dict[str, Decimal] = {}
    for e in expenses:
        paid[e.paid_by_user_id] = paid.get(e.paid_by_user_id, Decimal(0)) + e.amount
    sharers = [m for m in people if m.role not in NOT_SHARERS]
    share = (total / len(sharers)).quantize(CENT, ROUND_HALF_UP) if sharers else Decimal(0)
    sharer_ids = {m.user_id for m in sharers}
    balances = [
        {"user_id": m.user_id, "name": m.name, "paid": float(paid.get(m.user_id, 0)),
         "share": float(share if m.user_id in sharer_ids else 0),
         "balance": float(paid.get(m.user_id, Decimal(0)) - (share if m.user_id in sharer_ids else 0))}
        for m in people if m.user_id in sharer_ids or m.user_id in paid
    ]

    month = _month_start(today)
    visits = list(db.execute(
        select(CareVisit).where(CareVisit.care_profile_id == profile.id, CareVisit.visit_date >= month)
        .order_by(CareVisit.visit_date.desc())
    ).scalars())
    counts: dict[str, int] = {}
    for v in visits:
        counts[v.user_id] = counts.get(v.user_id, 0) + 1
    appt, went = _last_appointment(db, profile.id, today)
    return {
        "total": float(total),
        "share": float(share),
        "balances": balances,
        "expenses": [{"id": e.id, "what": e.what, "amount": float(e.amount), "spent_on": e.spent_on,
                      "paid_by": names.get(e.paid_by_user_id, "Someone")} for e in expenses[:50]],
        "visits_this_month": [{"user_id": m.user_id, "name": m.name, "count": counts.get(m.user_id, 0)}
                              for m in people if m.role != "Parent"],
        "visits": [{"id": v.id, "name": names.get(v.user_id, "Someone"), "visit_date": v.visit_date,
                    "note": v.note, "appointment_id": v.appointment_id} for v in visits],
        "last_appointment": None if appt is None else {
            "id": appt.id, "date": appt.scheduled_date, "provider": appt.provider, "reason": appt.reason,
            "went": names.get(went) if went else None,
        },
        "members": [{"user_id": m.user_id, "name": m.name} for m in people if m.role != "Parent"],
    }


# ---------- paperwork ----------

PAPER_KINDS = ("life_certificate", "income_tax", "bank_kyc", "property_tax", "insurance", "other")
YEARLY = {"life_certificate", "income_tax", "property_tax"}


def _next_year(day: date) -> date:
    try:
        return day.replace(year=day.year + 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year + 1, day=28)


def _next_on(today: date, month: int, day: int) -> date:
    this_year = date(today.year, month, day)
    return this_year if this_year >= today else date(today.year + 1, month, day)


def usual_paperwork(today: date) -> list[dict]:
    """The yearly chores most Indian pensioners have. Property tax dates differ by city."""
    return [
        {"kind": "life_certificate", "title": "Pension life certificate (Jeevan Pramaan)",
         "due_date": _next_on(today, 11, 30), "note": "November, or from 1 October at 80 and over"},
        {"kind": "income_tax", "title": "Income tax return", "due_date": _next_on(today, 7, 31),
         "note": "Form 15H to the bank in April stops tax being cut from interest"},
        {"kind": "property_tax", "title": "Property tax", "due_date": _next_on(today, 6, 30),
         "note": "Check your city's date and early-payment rebate"},
    ]


def add_paperwork(db: Session, actor_id: str, family_id: str, care_profile_id: str, kind: str, title: str | None,
                  due_date: date, note: str | None) -> PaperworkItem:
    require(db, actor_id, family_id, "tasks.create")
    profile = _profile_in(db, family_id, care_profile_id)
    if kind not in PAPER_KINDS:
        raise ValueError("Unknown paperwork kind")
    title = _clean(title or "") or kind.replace("_", " ").capitalize()
    row = PaperworkItem(family_id=family_id, care_profile_id=profile.id, kind=kind, title=title[:160],
                        due_date=due_date, note=_clean(note or "") or None, created_by_user_id=actor_id)
    db.add(row)
    db.flush()
    log_activity(db, family_id, actor_id, "paperwork.added", "paperwork_item", row.id, {"kind": kind})
    db.commit()
    return row


def add_usual(db: Session, actor_id: str, family_id: str, care_profile_id: str, today: date) -> list[PaperworkItem]:
    """Add the usual yearly chores that the parent does not have open yet."""
    require(db, actor_id, family_id, "tasks.create")
    _profile_in(db, family_id, care_profile_id)
    open_kinds = set(db.execute(
        select(PaperworkItem.kind).where(PaperworkItem.care_profile_id == care_profile_id,
                                         PaperworkItem.done_on.is_(None))
    ).scalars())
    return [add_paperwork(db, actor_id, family_id, care_profile_id, **item)
            for item in usual_paperwork(today) if item["kind"] not in open_kinds]


def paperwork(db: Session, actor_id: str, family_id: str, care_profile_id: str, today: date) -> list[dict]:
    """Open chores and insurance renewals, soonest first, then the ten most recently done."""
    require(db, actor_id, family_id, "dashboard.view")
    profile = _profile_in(db, family_id, care_profile_id)
    items = list(db.execute(
        select(PaperworkItem).where(PaperworkItem.care_profile_id == profile.id)
    ).scalars())
    rows = [{"id": p.id, "kind": p.kind, "title": p.title, "due_date": p.due_date, "note": p.note,
             "done_on": p.done_on, "source": "paperwork"} for p in items]
    policies = db.execute(
        select(InsurancePolicy).where(InsurancePolicy.family_id == family_id,
                                      or_(InsurancePolicy.care_profile_id == profile.id,
                                          InsurancePolicy.care_profile_id.is_(None)))
    ).scalars()
    rows += [{"id": p.id, "kind": "insurance", "title": f"Renew {p.insurer} {p.policy_type.replace('_', ' ')}",
              "due_date": p.renewal_date, "note": p.policy_number, "done_on": None, "source": "insurance"}
             for p in policies]
    open_rows = sorted((r for r in rows if r["done_on"] is None), key=lambda r: r["due_date"])
    done = sorted((r for r in rows if r["done_on"] is not None), key=lambda r: r["done_on"], reverse=True)[:10]
    for r in open_rows:
        r["days_left"] = (r["due_date"] - today).days
    return open_rows + done


def done_paperwork(db: Session, actor_id: str, family_id: str, item_id: str, today: date) -> PaperworkItem | None:
    """Mark a chore done. A yearly one gets next year's in its place, which is returned."""
    require(db, actor_id, family_id, "tasks.create")
    row = db.get(PaperworkItem, item_id)
    if row is None or row.family_id != family_id:
        raise NotFound("Paperwork not found")
    if row.done_on is not None:
        return None
    row.done_on = today
    nxt = None
    if row.kind in YEARLY:
        nxt = PaperworkItem(family_id=family_id, care_profile_id=row.care_profile_id, kind=row.kind,
                            title=row.title, due_date=_next_year(row.due_date), note=row.note,
                            created_by_user_id=actor_id)
        db.add(nxt)
    log_activity(db, family_id, actor_id, "paperwork.done", "paperwork_item", row.id, {"kind": row.kind})
    db.commit()
    return nxt


def delete_paperwork(db: Session, actor_id: str, family_id: str, item_id: str) -> None:
    require(db, actor_id, family_id, "tasks.create")
    row = db.get(PaperworkItem, item_id)
    if row is None or row.family_id != family_id:
        raise NotFound("Paperwork not found")
    db.delete(row)
    db.commit()


# ---------- carer ----------

def carer_day(db: Session, actor_id: str, family_id: str, care_profile_id: str, now: datetime) -> dict:
    require(db, actor_id, family_id, "medicine_quantity.update")
    profile = _profile_in(db, family_id, care_profile_id)
    reports = db.execute(
        select(CarerReport).where(CarerReport.care_profile_id == profile.id)
        .order_by(CarerReport.created_at.desc()).limit(20)
    ).scalars()
    names = {m.user_id: m.name for m in members(db, family_id)}
    return {
        "name": profile.display_name,
        "meals": [{"meal": m, "done": m in answered_meals(db, profile, now)} for m in MEALS],
        "doses": [{"medicine_id": d.medicine_id, "name": d.name, "slot": d.slot, "status": d.status,
                   "due_at": d.due_at} for d in doses_svc.doses_today(db, profile, now)],
        "reports": [{"id": r.id, "kind": r.kind, "text": r.text, "by": names.get(r.user_id, "Someone"),
                     "created_at": r.created_at} for r in reports],
    }


def carer_meal(db: Session, actor_id: str, family_id: str, care_profile_id: str, meal: str, note: str | None,
               now: datetime) -> None:
    require(db, actor_id, family_id, "medicine_quantity.update")
    profile = _profile_in(db, family_id, care_profile_id)
    if meal not in MEALS:
        raise ValueError("Unknown meal")
    save_meals(db, profile, [meal], _clean(note or "") or f"{meal} eaten", actor_id, now)
    db.commit()


def carer_dose(db: Session, actor_id: str, family_id: str, care_profile_id: str, medicine_id: str, slot: str,
               status: str, now: datetime) -> None:
    require(db, actor_id, family_id, "medicine_quantity.update")
    profile = _profile_in(db, family_id, care_profile_id)
    doses_svc.record_family_dose(db, profile, medicine_id, slot, status, actor_id, now)


def carer_report(db: Session, actor_id: str, family_id: str, care_profile_id: str, kind: str, text: str,
                 now: datetime) -> CarerReport:
    require(db, actor_id, family_id, "medicine_quantity.update")
    profile = _profile_in(db, family_id, care_profile_id)
    if kind not in ("concern", "note"):
        raise ValueError("A report is a concern or a note")
    text = _clean(text) or ""
    if not text:
        raise ValueError("Say what happened")
    row = CarerReport(family_id=family_id, care_profile_id=profile.id, user_id=actor_id, kind=kind,
                      text=text[:2000], created_at=now)
    db.add(row)
    db.flush()
    if kind == "concern":
        for m in members(db, family_id):
            if m.user_id != actor_id and m.role != "Parent":
                notify(db, m.user_id, "carer_concern", family_id,
                       {"care_profile_id": profile.id, "name": profile.display_name, "text": text[:300]})
    log_activity(db, family_id, actor_id, f"carer.{kind}", "carer_report", row.id, {})
    db.commit()
    return row
