"""Parent notes: a parent saves a note, optionally with a reminder.

* For themselves (the default): at `remind_at` the parent gets the note back in the app and on WhatsApp/SMS.
* For another family member: the note also becomes a task assigned to that person (notified now, as for any
  assigned task). If the parent also asked to "send them a reminder", that person gets the note at
  `remind_at` too (or right away when no time was chosen).

The parent's role has no tasks.* or members.* permission, so this module creates the task on their behalf
and only ever exposes members' names and relationships to them.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.membership import FamilyMember
from app.models.parent_note import ParentNote
from app.models.task import Task
from app.models.user import User
from app.services.activity import log_activity
from app.services.adapters.messaging import get_sms_provider, get_whatsapp_provider
from app.services.errors import NotFound
from app.services.notifications import notify
from app.services.parent_context import ParentContext

MAX_NOTE_LENGTH = 1000


@dataclass
class Person:
    user_id: str
    display_name: str
    relationship: str | None


def _aware(value: datetime | None) -> datetime | None:
    # SQLite hands back naive datetimes; they were stored as UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _parent_user_id(profile: CareProfile, note_author_id: str) -> str:
    """Who "myself" is: the profile's linked account, else whoever is using the parent chat."""
    return profile.linked_user_id or note_author_id


def people(db: Session, ctx: ParentContext) -> list[Person]:
    """Family members the parent can hand a note to (everyone active except the parent themselves)."""
    rows = db.execute(
        select(FamilyMember, User)
        .join(User, User.id == FamilyMember.user_id)
        .where(FamilyMember.family_id == ctx.family_id, FamilyMember.status == "active")
        .order_by(User.display_name)
    ).all()
    me = _parent_user_id(ctx.profile, ctx.user_id)
    return [
        Person(user_id=user.id, display_name=user.display_name, relationship=member.relationship)
        for member, user in rows
        if user.id != me and user.status == "active"
    ]


def list_notes(db: Session, ctx: ParentContext) -> list[ParentNote]:
    stmt = (
        select(ParentNote)
        .where(ParentNote.care_profile_id == ctx.profile.id)
        .order_by(ParentNote.created_at.desc(), ParentNote.id)
    )
    return list(db.execute(stmt).scalars())


def create_note(
    db: Session,
    ctx: ParentContext,
    text: str,
    remind_at: datetime | None = None,
    remind_user_id: str | None = None,
    send_reminder: bool = False,
    now: datetime | None = None,
) -> ParentNote:
    now = now or datetime.now(timezone.utc)
    text = (text or "").strip()
    if not text:
        raise ValueError("Please write your note first.")
    if len(text) > MAX_NOTE_LENGTH:
        raise ValueError(f"Please keep the note under {MAX_NOTE_LENGTH} characters.")
    remind_at = _aware(remind_at)
    if remind_at is not None and remind_at <= now:
        raise ValueError("Please choose a reminder time in the future.")

    me = _parent_user_id(ctx.profile, ctx.user_id)
    if remind_user_id == me:
        remind_user_id = None  # "remind me" chosen by picking their own name
    person: Person | None = None
    if remind_user_id is not None:
        person = next((p for p in people(db, ctx) if p.user_id == remind_user_id), None)
        if person is None:
            raise ValueError("That person isn't an active member of your family.")

    note = ParentNote(
        family_id=ctx.family_id,
        care_profile_id=ctx.profile.id,
        created_by_user_id=ctx.user_id,
        text=text,
        remind_at=remind_at,
        remind_user_id=remind_user_id,
        send_reminder=bool(person and send_reminder),
    )
    db.add(note)

    if person is not None:
        parent_name = ctx.profile.display_name
        task = Task(
            family_id=ctx.family_id,
            care_profile_id=ctx.profile.id,
            title=text if len(text) <= 255 else text[:252] + "...",
            description=f"Note from {parent_name}: {text}",
            due_at=remind_at,
            assigned_to_user_id=person.user_id,
            status="OPEN",
            priority="normal",
            created_by_user_id=ctx.user_id,
        )
        db.add(task)
        db.flush()
        note.task_id = task.id
        notify(db, person.user_id, "task.assigned", ctx.family_id, {"task_id": task.id, "title": task.title})
        # Nothing more is due later unless they also asked for a timed reminder.
        if not note.send_reminder:
            note.reminded_at = now
        elif remind_at is None:
            _deliver(db, note, now)
    elif remind_at is None:
        note.reminded_at = now  # a plain note: there is no reminder to send

    db.flush()
    log_activity(
        db, ctx.family_id, ctx.user_id, "parent_note.created", "parent_note", note.id,
        {"for": "self" if person is None else person.display_name, "task_id": note.task_id,
         "remind_at": remind_at.isoformat() if remind_at else None},
    )
    db.commit()
    db.refresh(note)
    return note


def delete_note(db: Session, ctx: ParentContext, note_id: str) -> None:
    """Delete one of this profile's notes. A task it created stays: it already belongs to that person."""
    note = db.get(ParentNote, note_id)
    if note is None or note.care_profile_id != ctx.profile.id:
        raise NotFound("Note not found")
    db.delete(note)
    db.commit()


def _deliver(db: Session, note: ParentNote, now: datetime) -> None:
    profile = db.get(CareProfile, note.care_profile_id)
    parent_name = profile.display_name if profile else "Your parent"
    if note.remind_user_id is None:
        recipient_id = _parent_user_id(profile, note.created_by_user_id) if profile else note.created_by_user_id
        greeting = (profile.greeting_name or profile.display_name) if profile else ""
        message = f"Hello {greeting}, here is your reminder: {note.text}".replace("Hello , ", "Hello, ")
        kind = "note.reminder"
    else:
        recipient_id = note.remind_user_id
        message = f"Reminder from {parent_name}: {note.text}"
        kind = "note.reminder_for_you"

    recipient = db.get(User, recipient_id)
    if recipient is not None and recipient.phone:
        get_whatsapp_provider().send(recipient.phone, message)
        get_sms_provider().send(recipient.phone, message)
    notify(db, recipient_id, kind, note.family_id,
           {"note_id": note.id, "message": message, "care_profile_id": note.care_profile_id,
            "task_id": note.task_id})
    note.reminded_at = now


def deliver_due_reminders(db: Session, now: datetime) -> int:
    """Scheduled job: send every reminder whose time has come. Returns how many were sent."""
    due = db.execute(
        select(ParentNote).where(ParentNote.reminded_at.is_(None), ParentNote.remind_at.is_not(None))
    ).scalars().all()
    sent = 0
    for note in due:
        if _aware(note.remind_at) <= now:
            _deliver(db, note, now)
            sent += 1
    if sent:
        db.commit()
    return sent
