"""The parent's circle: errands the family approves, posts from the family, contacts, the medical card, and
what the parent keeps private.

Who may do what:
- The parent asks for help, reads posts, sees their contacts and card, and sets their privacy.
- Family members see help requests with tasks.view and decide them with tasks.assign. Any member may post.
  Contacts and the card need parent_profile.view to read and parent_profile.edit to change.

Privacy: with `share_words` off, what the parent says in check-ins stays out of family notifications, the daily
email, the weekly summary and visit prep. With `share_chats` off, conversation summaries are hidden from the
family. Urgent messages and emergencies always reach the family.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_circle import CareCard, CareContact, FamilyPost, HelpRequest, ParentPrivacy
from app.models.care_profile import CareProfile
from app.models.insurance import InsurancePolicy
from app.models.medicine import Medicine
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.models.task import Task
from app.models.user import User
from app.services import family_alerts
from app.services.activity import log_activity
from app.services.errors import NotFound
from app.services.notifications import notify
from app.services.parent_context import ParentContext
from app.services.permissions import require

HELP_KINDS = ("bill", "groceries", "cab", "nurse", "physio", "other")
HELP_TITLES = {
    "bill": "Pay a bill for {name}", "groceries": "Order groceries for {name}", "cab": "Book a cab for {name}",
    "nurse": "Arrange a nurse visit for {name}", "physio": "Arrange a physio visit for {name}",
    "other": "Help {name}",
}
CONTACT_ROLES = ("doctor", "pharmacy", "hospital", "neighbour", "driver", "watchman", "nurse", "physio",
                 "friend", "other")
POST_KINDS = ("text", "photo", "voice")
MAX_POST_BYTES = 5 * 1024 * 1024
POST_TYPES = {"photo": ("image/jpeg", "image/png", "image/webp"),
              "voice": ("audio/webm", "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav")}
QUIET_DAYS = 3


def _profile_in(db: Session, family_id: str, care_profile_id: str) -> CareProfile:
    profile = db.get(CareProfile, care_profile_id)
    if profile is None or profile.family_id != family_id:
        raise NotFound("Parent not found")
    return profile


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


# ---------- privacy ----------

def privacy(db: Session, care_profile_id: str) -> ParentPrivacy:
    """The parent's choices; an unsaved row with the defaults when they never chose."""
    row = db.execute(select(ParentPrivacy).where(ParentPrivacy.care_profile_id == care_profile_id)).scalar_one_or_none()
    return row or ParentPrivacy(care_profile_id=care_profile_id, share_words=True, share_chats=True,
                                video_auto_answer=False)


def shares_words(db: Session, care_profile_id: str) -> bool:
    return privacy(db, care_profile_id).share_words


def shares_chats(db: Session, care_profile_id: str) -> bool:
    return privacy(db, care_profile_id).share_chats


def set_privacy(db: Session, ctx: ParentContext, values: dict, now: datetime) -> ParentPrivacy:
    row = privacy(db, ctx.profile.id)
    if row.id is None:
        db.add(row)
    for key in ("share_words", "share_chats", "video_auto_answer"):
        if values.get(key) is not None:
            setattr(row, key, bool(values[key]))
    row.updated_at = now
    db.commit()
    return row


# ---------- help the family approves ----------

def ask_help(db: Session, ctx: ParentContext, kind: str, note: str | None, now: datetime) -> HelpRequest:
    """The parent asks for an errand. One open task per kind: asking again returns the open request."""
    if kind not in HELP_KINDS:
        raise ValueError("Unknown kind of help")
    open_one = db.execute(
        select(HelpRequest).where(HelpRequest.care_profile_id == ctx.profile.id, HelpRequest.kind == kind,
                                  HelpRequest.status.in_(("asked", "approved")))
    ).scalars().first()
    if open_one is not None:
        return open_one
    name = ctx.profile.display_name
    title = HELP_TITLES[kind].format(name=name)
    task = Task(family_id=ctx.family_id, care_profile_id=ctx.profile.id, title=title,
                description=_clean(note) or f"{name} asked for this in the app.", due_at=now + timedelta(days=1),
                priority="high", created_by_user_id=ctx.user_id)
    db.add(task)
    db.flush()
    req = HelpRequest(family_id=ctx.family_id, care_profile_id=ctx.profile.id, kind=kind, note=_clean(note),
                      asked_by_user_id=ctx.user_id, task_id=task.id, created_at=now)
    db.add(req)
    db.flush()
    log_activity(db, ctx.family_id, ctx.user_id, "task.created", "task", task.id, {"title": title})
    payload = {"care_profile_id": ctx.profile.id, "parent_name": name, "kind": kind, "note": req.note,
               "help_id": req.id, "task_id": task.id}
    for member in family_alerts._members_except(db, ctx.family_id, ctx.user_id):
        notify(db, member.id, "help.requested", family_id=ctx.family_id, payload=payload)
    db.commit()
    return req


def parent_help(db: Session, ctx: ParentContext) -> list[HelpRequest]:
    return list(db.execute(
        select(HelpRequest).where(HelpRequest.care_profile_id == ctx.profile.id)
        .order_by(HelpRequest.created_at.desc()).limit(10)
    ).scalars())


def family_help(db: Session, user_id: str, family_id: str) -> list[HelpRequest]:
    require(db, user_id, family_id, "tasks.view")
    return list(db.execute(
        select(HelpRequest).where(HelpRequest.family_id == family_id).order_by(HelpRequest.created_at.desc())
        .limit(50)
    ).scalars())


def decide_help(db: Session, user_id: str, family_id: str, help_id: str, decision: str,
                amount, now: datetime) -> HelpRequest:
    """approve: the task is the decider's. decline: the task closes. done: errand finished."""
    require(db, user_id, family_id, "tasks.assign")
    req = db.get(HelpRequest, help_id)
    if req is None or req.family_id != family_id:
        raise NotFound("Request not found")
    if decision not in ("approved", "declined", "done"):
        raise ValueError("Decision must be approved, declined or done")
    task = db.get(Task, req.task_id) if req.task_id else None
    req.status = decision
    req.decided_by_user_id = user_id
    req.decided_at = now
    if amount is not None:
        req.amount = amount
    if task is not None:
        if decision == "approved":
            task.assigned_to_user_id = user_id
        else:
            task.status = "DONE"
    if req.asked_by_user_id:
        decider = db.get(User, user_id)
        notify(db, req.asked_by_user_id, "help.decided", family_id=family_id,
               payload={"help_id": req.id, "kind": req.kind, "status": decision,
                        "by": decider.display_name if decider else None})
    db.commit()
    return req


# ---------- posts from the family ----------

def add_post(db: Session, user_id: str, family_id: str, care_profile_id: str, kind: str, text: str | None,
             data: bytes | None, content_type: str | None, now: datetime) -> FamilyPost:
    require(db, user_id, family_id, "dashboard.view")
    _profile_in(db, family_id, care_profile_id)
    if kind not in POST_KINDS:
        raise ValueError("Unknown kind of post")
    if kind == "text":
        if not _clean(text):
            raise ValueError("Write something to send")
        data, content_type = None, None
    else:
        ctype = (content_type or "").split(";")[0].strip()
        if not data or ctype not in POST_TYPES[kind]:
            raise ValueError(f"Send a {kind} file")
        if len(data) > MAX_POST_BYTES:
            raise ValueError("The file is too big (5 MB at most)")
        content_type = ctype
    post = FamilyPost(family_id=family_id, care_profile_id=care_profile_id, author_user_id=user_id, kind=kind,
                      text=_clean(text), data=data, content_type=content_type, created_at=now)
    db.add(post)
    db.commit()
    return post


def family_posts(db: Session, user_id: str, family_id: str, care_profile_id: str) -> list[FamilyPost]:
    require(db, user_id, family_id, "dashboard.view")
    return list(db.execute(
        select(FamilyPost).where(FamilyPost.family_id == family_id, FamilyPost.care_profile_id == care_profile_id)
        .order_by(FamilyPost.created_at.desc()).limit(50)
    ).scalars())


def parent_posts(db: Session, ctx: ParentContext, now: datetime) -> list[FamilyPost]:
    """The latest 20 posts, oldest first; reading them marks them seen."""
    rows = list(db.execute(
        select(FamilyPost).where(FamilyPost.care_profile_id == ctx.profile.id)
        .order_by(FamilyPost.created_at.desc()).limit(20)
    ).scalars())
    changed = False
    for p in rows:
        if p.seen_at is None:
            p.seen_at = now
            changed = True
    if changed:
        db.commit()
    return rows[::-1]


def post_for_parent(db: Session, ctx: ParentContext, post_id: str) -> FamilyPost:
    post = db.get(FamilyPost, post_id)
    if post is None or post.care_profile_id != ctx.profile.id or post.data is None:
        raise NotFound("Post not found")
    return post


def post_for_family(db: Session, user_id: str, family_id: str, post_id: str) -> FamilyPost:
    require(db, user_id, family_id, "dashboard.view")
    post = db.get(FamilyPost, post_id)
    if post is None or post.family_id != family_id or post.data is None:
        raise NotFound("Post not found")
    return post


def author_names(db: Session, posts: list[FamilyPost]) -> dict[str, str]:
    ids = {p.author_user_id for p in posts}
    if not ids:
        return {}
    return {u.id: u.display_name for u in db.execute(select(User).where(User.id.in_(ids))).scalars()}


# ---------- contacts ----------

CONTACT_FIELDS = ("name", "role", "phone", "address", "birthday_month", "birthday_day", "sort_order")


def _check_contact(values: dict) -> dict:
    out = {k: (_clean(v) if isinstance(v, str) else v) for k, v in values.items() if k in CONTACT_FIELDS}
    if "name" in out and not out["name"]:
        raise ValueError("A contact needs a name")
    if "role" in out and out["role"] not in CONTACT_ROLES:
        raise ValueError("Unknown role")
    m, d = out.get("birthday_month"), out.get("birthday_day")
    if (m is None) != (d is None) and ("birthday_month" in out or "birthday_day" in out):
        raise ValueError("Give both the birthday month and day, or neither")
    if m is not None:
        try:
            date(2000, int(m), int(d))  # 2000 is a leap year, so 29 Feb is allowed
        except ValueError as exc:
            raise ValueError("That birthday is not a real date") from exc
    return out


def contacts(db: Session, care_profile_id: str) -> list[CareContact]:
    return list(db.execute(
        select(CareContact).where(CareContact.care_profile_id == care_profile_id)
        .order_by(CareContact.sort_order, CareContact.name)
    ).scalars())


def family_contacts(db: Session, user_id: str, family_id: str, care_profile_id: str) -> list[CareContact]:
    require(db, user_id, family_id, "parent_profile.view")
    _profile_in(db, family_id, care_profile_id)
    return contacts(db, care_profile_id)


def add_contact(db: Session, user_id: str, family_id: str, care_profile_id: str, values: dict) -> CareContact:
    require(db, user_id, family_id, "parent_profile.edit")
    _profile_in(db, family_id, care_profile_id)
    clean = _check_contact(values)
    if not clean.get("name") or not clean.get("role"):
        raise ValueError("A contact needs a name and a role")
    row = CareContact(family_id=family_id, care_profile_id=care_profile_id, **clean)
    db.add(row)
    db.commit()
    return row


def _own_contact(db: Session, family_id: str, contact_id: str) -> CareContact:
    row = db.get(CareContact, contact_id)
    if row is None or row.family_id != family_id:
        raise NotFound("Contact not found")
    return row


def update_contact(db: Session, user_id: str, family_id: str, contact_id: str, values: dict) -> CareContact:
    require(db, user_id, family_id, "parent_profile.edit")
    row = _own_contact(db, family_id, contact_id)
    for k, v in _check_contact(values).items():
        setattr(row, k, v)
    db.commit()
    return row


def delete_contact(db: Session, user_id: str, family_id: str, contact_id: str) -> None:
    require(db, user_id, family_id, "parent_profile.edit")
    db.delete(_own_contact(db, family_id, contact_id))
    db.commit()


def birthdays(db: Session, care_profile_id: str, day: date, ahead: int = 1) -> list[tuple[CareContact, date]]:
    """Contacts whose birthday falls today or within `ahead` days (29 Feb counts on 28 Feb in other years)."""
    out = []
    for c in contacts(db, care_profile_id):
        if c.birthday_month is None or c.birthday_day is None:
            continue
        for offset in range(ahead + 1):
            d = day + timedelta(days=offset)
            bday = (c.birthday_month, c.birthday_day)
            leap_fallback = bday == (2, 29) and (d.month, d.day) == (2, 28) and not _leap(d.year)
            if (d.month, d.day) == bday or leap_fallback:
                out.append((c, d))
                break
    return out


def _leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


@dataclass
class CallPerson:
    name: str
    role: str
    phone: str


def call_circle(db: Session, family_id: str, care_profile_id: str, parent_user_id: str | None) -> list[CallPerson]:
    """Everyone the parent can call with one tap: family members with a number, then saved contacts."""
    from app.services.parent_asks import _phone  # the same number "Call my son" uses

    people: list[CallPerson] = []
    for user in family_alerts._members_except(db, family_id, parent_user_id):
        phone = _phone(db, user)
        if phone:
            people.append(CallPerson(user.display_name, "family", phone))
    people += [CallPerson(c.name, c.role, c.phone) for c in contacts(db, care_profile_id) if c.phone]
    return people


# ---------- medical card ----------

CARD_FIELDS = ("blood_group", "emergency_name", "emergency_phone", "notes")


def _onboarding(db: Session, profile: CareProfile) -> ParentOnboardingProfile | None:
    if profile.linked_user_id is None:
        return None
    return db.execute(
        select(ParentOnboardingProfile).where(ParentOnboardingProfile.user_id == profile.linked_user_id)
    ).scalars().first()


def card(db: Session, profile: CareProfile) -> dict:
    """Everything the medical card and the emergency screen show, gathered from what the app keeps."""
    row = db.execute(select(CareCard).where(CareCard.care_profile_id == profile.id)).scalar_one_or_none()
    ob = _onboarding(db, profile)
    meds = db.execute(
        select(Medicine).where(Medicine.care_profile_id == profile.id).order_by(Medicine.display_name)
    ).scalars().all()
    contact = None
    if row and row.emergency_phone:
        contact = {"name": row.emergency_name or "Emergency contact", "phone": row.emergency_phone}
    elif ob and ob.caregiver_phone:
        contact = {"name": "Family", "phone": ob.caregiver_phone}
    policy = db.execute(
        select(InsurancePolicy).where(InsurancePolicy.care_profile_id == profile.id,
                                      InsurancePolicy.policy_type == "health")
        .order_by(InsurancePolicy.renewal_date.desc()).limit(1)
    ).scalar_one_or_none()
    insurance = None
    if policy:
        insurance = {"insurer": policy.insurer, "policy_number": policy.policy_number, "helpline": policy.helpline}
    return {
        "name": profile.display_name,
        "blood_group": row.blood_group if row else None,
        "allergies": ob.allergies if ob else None,
        "medicines": [m.display_name for m in meds if getattr(m, "active", True) is not False],
        "doctor": ob.primary_doctor_name if ob else None,
        "doctor_phone": ob.doctor_contact_number if ob else None,
        "hospital": ob.preferred_hospital if ob else None,
        "emergency_contact": contact,
        "emergency_name": row.emergency_name if row else None,
        "emergency_phone": row.emergency_phone if row else None,
        "notes": row.notes if row else None,
        "insurance": insurance,
    }


def family_card(db: Session, user_id: str, family_id: str, care_profile_id: str) -> dict:
    require(db, user_id, family_id, "parent_profile.view")
    return card(db, _profile_in(db, family_id, care_profile_id))


def save_card(db: Session, user_id: str, family_id: str, care_profile_id: str, values: dict,
              now: datetime) -> dict:
    require(db, user_id, family_id, "parent_profile.edit")
    profile = _profile_in(db, family_id, care_profile_id)
    row = db.execute(select(CareCard).where(CareCard.care_profile_id == profile.id)).scalar_one_or_none()
    if row is None:
        row = CareCard(care_profile_id=profile.id)
        db.add(row)
    for k in CARD_FIELDS:
        if k in values:
            setattr(row, k, _clean(values[k]))
    row.updated_at = now
    db.commit()
    return card(db, profile)


# ---------- company: a gentle nudge ----------

def nudge(db: Session, ctx: ParentContext, now: datetime) -> dict:
    """Call someone whose birthday is today, else call family when no one has posted for a few days, else walk."""
    from app.services.doses import today_for

    day = today_for(ctx.profile, now)
    for c, d in birthdays(db, ctx.profile.id, day, ahead=0):
        return {"kind": "birthday", "name": c.name, "phone": c.phone}
    last = db.execute(
        select(FamilyPost.created_at).where(FamilyPost.care_profile_id == ctx.profile.id)
        .order_by(FamilyPost.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    from app.services.doses import _aware

    if last is None or _aware(last) < now - timedelta(days=QUIET_DAYS):
        people = [p for p in call_circle(db, ctx.family_id, ctx.profile.id, ctx.user_id) if p.role == "family"]
        if people:
            return {"kind": "call", "name": people[0].name, "phone": people[0].phone}
    return {"kind": "walk", "name": None, "phone": None}
