"""The signed-in parent's notes, with optional reminders (see app/services/parent_notes.py).

GET    /api/parent/notes          this profile's notes, newest first
POST   /api/parent/notes          save a note (and its reminder / task)
DELETE /api/parent/notes/{id}     delete a note
GET    /api/parent/notes/people   family members a note can be sent to (names only)

Like the rest of /api/parent, the optional X-Care-Profile-Id header picks the profile chosen on the
chat page; without it, the account's own profile is used. 409 when the parent is not linked yet.
"""

from datetime import datetime

from fastapi import APIRouter, Header, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.parent_note import ParentNote
from app.models.user import User
from app.services import parent_notes as svc
from app.services.parent_context import resolve_parent

router = APIRouter(prefix="/api/parent/notes", tags=["parent-notes"])

ProfileId = Header(default=None, alias="X-Care-Profile-Id")


class ParentNoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=svc.MAX_NOTE_LENGTH)
    # When to remind (with a timezone offset); omit for a note without a reminder.
    remind_at: datetime | None = None
    # Another family member to hand the note to (it becomes their task); omit for "myself".
    remind_user_id: str | None = None
    # For another member: also send them a reminder message (at remind_at, or right away).
    send_reminder: bool = False


class ParentNoteOut(BaseModel):
    id: str
    text: str
    remind_at: datetime | None
    # null = the parent themselves
    remind_user_id: str | None
    remind_user_name: str | None
    send_reminder: bool
    task_id: str | None
    reminded: bool
    created_at: datetime


class NotePersonOut(BaseModel):
    user_id: str
    display_name: str
    relationship: str | None


def _out(db: Session, note: ParentNote) -> ParentNoteOut:
    person = db.get(User, note.remind_user_id) if note.remind_user_id else None
    return ParentNoteOut(
        id=note.id,
        text=note.text,
        remind_at=svc._aware(note.remind_at),
        remind_user_id=note.remind_user_id,
        remind_user_name=person.display_name if person else None,
        send_reminder=note.send_reminder,
        task_id=note.task_id,
        reminded=note.reminded_at is not None,
        created_at=svc._aware(note.created_at),
    )


@router.get("", response_model=list[ParentNoteOut])
def list_notes(
    db: Session = DbSession, user: User = CurrentUser, care_profile_id: str | None = ProfileId
) -> list[ParentNoteOut]:
    ctx = resolve_parent(db, user, care_profile_id)
    return [_out(db, n) for n in svc.list_notes(db, ctx)]


@router.get("/people", response_model=list[NotePersonOut])
def list_people(
    db: Session = DbSession, user: User = CurrentUser, care_profile_id: str | None = ProfileId
) -> list[NotePersonOut]:
    ctx = resolve_parent(db, user, care_profile_id)
    return [
        NotePersonOut(user_id=p.user_id, display_name=p.display_name, relationship=p.relationship)
        for p in svc.people(db, ctx)
    ]


@router.post("", response_model=ParentNoteOut, status_code=201)
def create_note(
    body: ParentNoteIn,
    db: Session = DbSession,
    user: User = CurrentUser,
    care_profile_id: str | None = ProfileId,
) -> ParentNoteOut:
    ctx = resolve_parent(db, user, care_profile_id)
    note = svc.create_note(db, ctx, body.text, body.remind_at, body.remind_user_id, body.send_reminder)
    return _out(db, note)


@router.delete("/{note_id}", status_code=204)
def delete_note(
    note_id: str, db: Session = DbSession, user: User = CurrentUser, care_profile_id: str | None = ProfileId
) -> Response:
    ctx = resolve_parent(db, user, care_profile_id)
    svc.delete_note(db, ctx, note_id)
    return Response(status_code=204)
