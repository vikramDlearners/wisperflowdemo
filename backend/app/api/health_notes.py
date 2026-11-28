"""A parent's health list: allergies, conditions and readings (see app/services/health_notes.py).

Family (needs parent_profile.view to read, parent_profile.edit to change):
GET    /api/families/{family_id}/care-profiles/{care_profile_id}/health              the list
POST   /api/families/{family_id}/care-profiles/{care_profile_id}/health              add from words or a reading
DELETE /api/families/{family_id}/care-profiles/{care_profile_id}/health/{note_id}    take a note off the list
GET    /api/families/{family_id}/care-profiles/{care_profile_id}/health/readings     readings for graphs

Parent (X-Care-Profile-Id picks the profile, as in the rest of /api/parent):
GET    /api/parent/health    the list
POST   /api/parent/health    add from words
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.care_profile import CareProfile
from app.models.health_note import HealthNote
from app.models.user import User
from app.services import health_notes as svc
from app.services.errors import NotFound
from app.services.parent_context import resolve_parent
from app.services.permissions import require

family_router = APIRouter(
    prefix="/api/families/{family_id}/care-profiles/{care_profile_id}/health", tags=["health-notes"]
)
parent_router = APIRouter(prefix="/api/parent/health", tags=["health-notes"])

ProfileId = Header(default=None, alias="X-Care-Profile-Id")


class HealthNoteIn(BaseModel):
    # Plain words ("BP 150/95 today, allergic to peanuts"), or a reading kind and value.
    text: str | None = Field(default=None, max_length=2000)
    kind: str | None = None
    value: str | None = Field(default=None, max_length=60)


class HealthNoteOut(BaseModel):
    id: str
    kind: str
    label: str
    value: str | None
    value_num: float | None
    value_num2: float | None
    text: str
    source: str
    source_text: str | None
    recorded_at: datetime


class HealthListOut(BaseModel):
    allergies: list[HealthNoteOut]
    conditions: list[HealthNoteOut]
    readings: list[HealthNoteOut]
    # Everything known, the onboarding profile's answers included, as food advice uses it.
    known_allergies: list[str]
    known_conditions: list[str]


class HealthSavedOut(BaseModel):
    # What the app will keep track of from these words, one line each; empty when nothing was found.
    tracking: list[str]
    notes: list[HealthNoteOut]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _out(note: HealthNote) -> HealthNoteOut:
    return HealthNoteOut(
        id=note.id, kind=note.kind, label=note.label, value=note.value, value_num=note.value_num,
        value_num2=note.value_num2, text=svc.describe(note), source=note.source, source_text=note.source_text,
        recorded_at=_aware(note.recorded_at),
    )


def _list(db: Session, profile: CareProfile) -> HealthListOut:
    notes = svc.active_notes(db, profile.id)
    summary = svc.health_summary(db, profile)
    readings = [n for n in notes if n.kind == svc.READING][-30:]
    return HealthListOut(
        allergies=[_out(n) for n in notes if n.kind == svc.ALLERGY],
        conditions=[_out(n) for n in notes if n.kind == svc.CONDITION],
        readings=[_out(n) for n in reversed(readings)],
        known_allergies=summary.allergies,
        known_conditions=summary.conditions,
    )


def _save(db: Session, profile: CareProfile, body: HealthNoteIn, source: str, user_id: str) -> HealthSavedOut:
    if body.kind:
        reading = svc.parse_reading(body.kind, body.value)
        if reading is None:
            raise ValueError("Give a reading as bp, sugar, weight or pulse with a value, like 130/85")
        found, words = [reading], f"{body.kind} {body.value}"
    else:
        words = (body.text or "").strip()
        if not words:
            raise ValueError("Write what to note down")
        found = svc.read_notes(words)
    saved = svc.save_found(db, profile, found, source, words, user_id, datetime.now(timezone.utc))
    db.commit()
    return HealthSavedOut(tracking=[svc.describe(n) for n in saved], notes=[_out(n) for n in saved])


def _profile(db: Session, user: User, family_id: str, care_profile_id: str, permission: str) -> CareProfile:
    require(db, user.id, family_id, permission)
    profile = db.get(CareProfile, care_profile_id)
    if profile is None or profile.family_id != family_id:
        raise NotFound("Care profile not found")
    return profile


@family_router.get("", response_model=HealthListOut)
def family_list(
    family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser
) -> HealthListOut:
    return _list(db, _profile(db, user, family_id, care_profile_id, "parent_profile.view"))


@family_router.post("", response_model=HealthSavedOut, status_code=201)
def family_add(
    family_id: str, care_profile_id: str, body: HealthNoteIn, db: Session = DbSession, user: User = CurrentUser
) -> HealthSavedOut:
    profile = _profile(db, user, family_id, care_profile_id, "parent_profile.edit")
    return _save(db, profile, body, "family", user.id)


@family_router.get("/readings", response_model=list[HealthNoteOut])
def family_readings(
    family_id: str,
    care_profile_id: str,
    kind: str | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=730),
    db: Session = DbSession,
    user: User = CurrentUser,
) -> list[HealthNoteOut]:
    """Readings oldest first, for graphs: value_num (systolic for BP) and value_num2 (diastolic)."""
    profile = _profile(db, user, family_id, care_profile_id, "parent_profile.view")
    since = datetime.now(timezone.utc) - timedelta(days=days)
    query = select(HealthNote).where(
        HealthNote.care_profile_id == profile.id, HealthNote.kind == svc.READING,
        HealthNote.active.is_(True), HealthNote.recorded_at >= since,
    )
    if kind:
        query = query.where(HealthNote.label == kind)
    rows = db.execute(query.order_by(HealthNote.recorded_at, HealthNote.id)).scalars()
    return [_out(n) for n in rows]


@family_router.delete("/{note_id}", status_code=204)
def family_remove(
    family_id: str, care_profile_id: str, note_id: str, db: Session = DbSession, user: User = CurrentUser
) -> Response:
    profile = _profile(db, user, family_id, care_profile_id, "parent_profile.edit")
    note = db.get(HealthNote, note_id)
    if note is None or note.care_profile_id != profile.id:
        raise NotFound("Health note not found")
    note.active = False
    db.commit()
    return Response(status_code=204)


@parent_router.get("", response_model=HealthListOut)
def parent_list(
    db: Session = DbSession, user: User = CurrentUser, care_profile_id: str | None = ProfileId
) -> HealthListOut:
    return _list(db, resolve_parent(db, user, care_profile_id).profile)


@parent_router.post("", response_model=HealthSavedOut, status_code=201)
def parent_add(
    body: HealthNoteIn, db: Session = DbSession, user: User = CurrentUser, care_profile_id: str | None = ProfileId
) -> HealthSavedOut:
    ctx = resolve_parent(db, user, care_profile_id)
    return _save(db, ctx.profile, body, "chat", user.id)
