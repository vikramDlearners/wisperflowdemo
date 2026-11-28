"""The parent's circle (see app/services/care_circle.py for who may do what).

Family, under /api/families/{family_id}:
GET    /help                                          errands the parent asked for
PATCH  /help/{help_id}                                approve, decline or mark done
GET    /care-profiles/{care_profile_id}/posts         what the family sent the parent
POST   /care-profiles/{care_profile_id}/posts         send a line, photo or voice note
GET    /posts/{post_id}/media                         the photo or voice note
GET    /care-profiles/{care_profile_id}/contacts      doctors, neighbours, friends and their birthdays
POST   /care-profiles/{care_profile_id}/contacts
PATCH  /contacts/{contact_id}
DELETE /contacts/{contact_id}
GET    /care-profiles/{care_profile_id}/card          the medical card
PUT    /care-profiles/{care_profile_id}/card

Parent (X-Care-Profile-Id picks the profile):
GET/POST /api/parent/help        GET /api/parent/posts      GET /api/parent/posts/{post_id}/media
GET  /api/parent/circle          GET /api/parent/card       GET/PUT /api/parent/privacy
GET  /api/parent/nudge
"""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, File, Form, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.care_circle import CareContact, FamilyPost, HelpRequest, ParentPrivacy
from app.models.user import User
from app.services import care_circle as svc
from app.services.parent_context import resolve_parent

family_router = APIRouter(prefix="/api/families/{family_id}", tags=["care-circle"])
parent_router = APIRouter(prefix="/api/parent", tags=["care-circle"])
ProfileId = Header(default=None, alias="X-Care-Profile-Id")


def _now() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def _bad_input():
    try:
        yield
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _help(r: HelpRequest) -> dict:
    return {"id": r.id, "care_profile_id": r.care_profile_id, "kind": r.kind, "note": r.note, "status": r.status,
            "task_id": r.task_id, "amount": float(r.amount) if r.amount is not None else None,
            "created_at": r.created_at, "decided_at": r.decided_at}


def _post(p: FamilyPost, names: dict[str, str], media_base: str) -> dict:
    return {"id": p.id, "kind": p.kind, "text": p.text, "author": names.get(p.author_user_id),
            "created_at": p.created_at, "seen_at": p.seen_at,
            "media_url": f"{media_base}/{p.id}/media" if p.kind != "text" else None}


def _contact(c: CareContact) -> dict:
    return {k: getattr(c, k) for k in ("id", "name", "role", "phone", "address", "birthday_month", "birthday_day",
                                       "sort_order")}


def _privacy(p: ParentPrivacy) -> dict:
    return {"share_words": p.share_words, "share_chats": p.share_chats, "video_auto_answer": p.video_auto_answer}


def _media(post: FamilyPost) -> Response:
    return Response(content=post.data, media_type=post.content_type,
                    headers={"Cache-Control": "private, max-age=3600"})


# ---------- family ----------

class DecideIn(BaseModel):
    status: str
    amount: Decimal | None = Field(default=None, ge=0)


class ContactIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    role: str | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=240)
    birthday_month: int | None = Field(default=None, ge=1, le=12)
    birthday_day: int | None = Field(default=None, ge=1, le=31)
    sort_order: int | None = None


class CardIn(BaseModel):
    blood_group: str | None = Field(default=None, max_length=8)
    emergency_name: str | None = Field(default=None, max_length=120)
    emergency_phone: str | None = Field(default=None, max_length=30)
    notes: str | None = Field(default=None, max_length=2000)


@family_router.get("/help")
def list_help(family_id: str, db: Session = DbSession, user: User = CurrentUser) -> list[dict]:
    return [_help(r) for r in svc.family_help(db, user.id, family_id)]


@family_router.patch("/help/{help_id}")
def decide_help(family_id: str, help_id: str, body: DecideIn, db: Session = DbSession,
                user: User = CurrentUser) -> dict:
    with _bad_input():
        return _help(svc.decide_help(db, user.id, family_id, help_id, body.status, body.amount, _now()))


@family_router.get("/care-profiles/{care_profile_id}/posts")
def list_posts(family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser) -> list[dict]:
    posts = svc.family_posts(db, user.id, family_id, care_profile_id)
    names = svc.author_names(db, posts)
    return [_post(p, names, f"/api/families/{family_id}/posts") for p in posts]


@family_router.post("/care-profiles/{care_profile_id}/posts", status_code=201)
def add_post(family_id: str, care_profile_id: str, kind: str = Form(...), text: str | None = Form(default=None),
             file: UploadFile | None = File(default=None), db: Session = DbSession,
             user: User = CurrentUser) -> dict:
    data = file.file.read(svc.MAX_POST_BYTES + 1) if file is not None else None
    with _bad_input():
        post = svc.add_post(db, user.id, family_id, care_profile_id, kind, text, data,
                            file.content_type if file is not None else None, _now())
    return _post(post, {user.id: user.display_name}, f"/api/families/{family_id}/posts")


@family_router.get("/posts/{post_id}/media")
def post_media(family_id: str, post_id: str, db: Session = DbSession, user: User = CurrentUser) -> Response:
    return _media(svc.post_for_family(db, user.id, family_id, post_id))


@family_router.get("/care-profiles/{care_profile_id}/contacts")
def list_contacts(family_id: str, care_profile_id: str, db: Session = DbSession,
                  user: User = CurrentUser) -> list[dict]:
    return [_contact(c) for c in svc.family_contacts(db, user.id, family_id, care_profile_id)]


@family_router.post("/care-profiles/{care_profile_id}/contacts", status_code=201)
def add_contact(family_id: str, care_profile_id: str, body: ContactIn, db: Session = DbSession,
                user: User = CurrentUser) -> dict:
    with _bad_input():
        return _contact(svc.add_contact(db, user.id, family_id, care_profile_id, body.model_dump(exclude_unset=True)))


@family_router.patch("/contacts/{contact_id}")
def update_contact(family_id: str, contact_id: str, body: ContactIn, db: Session = DbSession,
                   user: User = CurrentUser) -> dict:
    with _bad_input():
        return _contact(svc.update_contact(db, user.id, family_id, contact_id, body.model_dump(exclude_unset=True)))


@family_router.delete("/contacts/{contact_id}", status_code=204)
def delete_contact(family_id: str, contact_id: str, db: Session = DbSession, user: User = CurrentUser) -> Response:
    svc.delete_contact(db, user.id, family_id, contact_id)
    return Response(status_code=204)


@family_router.get("/care-profiles/{care_profile_id}/card")
def get_card(family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser) -> dict:
    return svc.family_card(db, user.id, family_id, care_profile_id)


@family_router.put("/care-profiles/{care_profile_id}/card")
def put_card(family_id: str, care_profile_id: str, body: CardIn, db: Session = DbSession,
             user: User = CurrentUser) -> dict:
    return svc.save_card(db, user.id, family_id, care_profile_id, body.model_dump(exclude_unset=True), _now())


# ---------- parent ----------

class AskHelpIn(BaseModel):
    kind: str
    note: str | None = Field(default=None, max_length=500)


class PrivacyIn(BaseModel):
    share_words: bool | None = None
    share_chats: bool | None = None
    video_auto_answer: bool | None = None


@parent_router.get("/help")
def my_help(db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId) -> list[dict]:
    return [_help(r) for r in svc.parent_help(db, resolve_parent(db, user, profile_id))]


@parent_router.post("/help", status_code=201)
def ask_help(body: AskHelpIn, db: Session = DbSession, user: User = CurrentUser,
             profile_id: str | None = ProfileId) -> dict:
    with _bad_input():
        return _help(svc.ask_help(db, resolve_parent(db, user, profile_id), body.kind, body.note, _now()))


@parent_router.get("/posts")
def my_posts(db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId) -> list[dict]:
    posts = svc.parent_posts(db, resolve_parent(db, user, profile_id), _now())
    names = svc.author_names(db, posts)
    return [_post(p, names, "/api/parent/posts") for p in posts]


@parent_router.get("/posts/{post_id}/media")
def my_post_media(post_id: str, db: Session = DbSession, user: User = CurrentUser,
                  profile_id: str | None = ProfileId) -> Response:
    return _media(svc.post_for_parent(db, resolve_parent(db, user, profile_id), post_id))


@parent_router.get("/circle")
def my_circle(db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId) -> list[dict]:
    ctx = resolve_parent(db, user, profile_id)
    return [asdict(p) for p in svc.call_circle(db, ctx.family_id, ctx.profile.id, ctx.user_id)]


@parent_router.get("/card")
def my_card(db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId) -> dict:
    return svc.card(db, resolve_parent(db, user, profile_id).profile)


@parent_router.get("/privacy")
def my_privacy(db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId) -> dict:
    return _privacy(svc.privacy(db, resolve_parent(db, user, profile_id).profile.id))


@parent_router.put("/privacy")
def set_my_privacy(body: PrivacyIn, db: Session = DbSession, user: User = CurrentUser,
                   profile_id: str | None = ProfileId) -> dict:
    return _privacy(svc.set_privacy(db, resolve_parent(db, user, profile_id), body.model_dump(), _now()))


@parent_router.get("/nudge")
def my_nudge(db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId) -> dict:
    return svc.nudge(db, resolve_parent(db, user, profile_id), _now())
