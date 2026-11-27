"""Shareable task links.

A family member with tasks.create makes a link for one task. Anyone holding the link can,
without signing in, view that task, mark it done, add notes and upload photos. The link opens
nothing else: every lookup starts from the token and stays inside its task.

The token is `<link id>.<HMAC-SHA256(secret_key, link id)>`. Only the link id is stored, so
the same link can be copied again, and revoking or expiry is checked on every request.
"""

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.task import Task
from app.models.task_link import TaskImage, TaskNote, TaskShareLink
from app.models.user import User
from app.services.activity import log_activity
from app.services.errors import LinkGone, NotFound
from app.services.notifications import notify
from app.services.permissions import require
from app.services.prescription_scan import ALLOWED_MIME_TYPES, MAX_IMAGE_BYTES

LINK_LIFETIME = timedelta(days=30)
MAX_IMAGES_PER_TASK = 20
MAX_NOTES_PER_TASK = 200

# The first bytes each allowed image type starts with, so a file cannot claim to be an image.
_MAGIC = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    # SQLite hands back naive datetimes; everything here is stored in UTC.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _signature(link_id: str) -> str:
    digest = hmac.new(
        settings.secret_key.encode("utf-8"), f"task-link:{link_id}".encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def token_for(link: TaskShareLink) -> str:
    return f"{link.id}.{_signature(link.id)}"


def _is_active(link: TaskShareLink, now: datetime) -> bool:
    return link.revoked_at is None and as_utc(link.expires_at) > now


# --- Family side (signed in) -------------------------------------------------------------


def _task_in_family(db: Session, family_id: str, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.family_id != family_id:
        raise NotFound("Task not found")
    return task


def get_or_create_link(db: Session, actor_id: str, family_id: str, task_id: str) -> TaskShareLink:
    """Return the task's active link, or make one that lasts LINK_LIFETIME."""
    require(db, actor_id, family_id, "tasks.create")
    task = _task_in_family(db, family_id, task_id)
    now = _utcnow()
    links = db.execute(
        select(TaskShareLink)
        .where(TaskShareLink.task_id == task.id, TaskShareLink.revoked_at.is_(None))
        .order_by(TaskShareLink.created_at.desc())
    ).scalars()
    for link in links:
        if _is_active(link, now):
            return link
    link = TaskShareLink(task_id=task.id, created_by_user_id=actor_id, expires_at=now + LINK_LIFETIME)
    db.add(link)
    db.flush()
    log_activity(db, family_id, actor_id, "task.link_created", "task", task.id, {"expires_at": link.expires_at.isoformat()})
    db.commit()
    return link


def revoke_links(db: Session, actor_id: str, family_id: str, task_id: str) -> int:
    """Turn off every link to the task. Returns how many were active."""
    require(db, actor_id, family_id, "tasks.create")
    task = _task_in_family(db, family_id, task_id)
    now = _utcnow()
    links = db.execute(
        select(TaskShareLink).where(TaskShareLink.task_id == task.id, TaskShareLink.revoked_at.is_(None))
    ).scalars().all()
    for link in links:
        link.revoked_at = now
    log_activity(db, family_id, actor_id, "task.link_revoked", "task", task.id, {"count": len(links)})
    db.commit()
    return len(links)


# --- Link side (no sign-in) ------------------------------------------------------------


def resolve(db: Session, token: str) -> tuple[TaskShareLink, Task]:
    """Find the link and task for a token. Unknown or forged tokens raise NotFound;
    a genuine link that was revoked or has expired raises LinkGone."""
    link_id, _, signature = token.partition(".")
    if not link_id or not signature or len(link_id) > 36:
        raise NotFound("Link not found")
    if not hmac.compare_digest(signature.encode("utf-8"), _signature(link_id).encode("utf-8")):
        raise NotFound("Link not found")
    link = db.get(TaskShareLink, link_id)
    task = db.get(Task, link.task_id) if link is not None else None
    if link is None or task is None:
        raise NotFound("Link not found")
    if link.revoked_at is not None:
        raise LinkGone("This link was turned off")
    if as_utc(link.expires_at) <= _utcnow():
        raise LinkGone("This link has expired")
    return link, task


def view(db: Session, token: str) -> dict:
    link, task = resolve(db, token)
    assignee = db.get(User, task.assigned_to_user_id) if task.assigned_to_user_id else None
    notes = db.execute(
        select(TaskNote).where(TaskNote.task_id == task.id).order_by(TaskNote.created_at)
    ).scalars().all()
    images = db.execute(
        select(TaskImage).where(TaskImage.task_id == task.id).order_by(TaskImage.created_at)
    ).scalars().all()
    return {
        "task": task,
        "assignee_name": assignee.display_name if assignee else None,
        "expires_at": as_utc(link.expires_at),
        "notes": notes,
        "images": images,
    }


def complete(db: Session, token: str) -> Task:
    link, task = resolve(db, token)
    if task.status != "DONE":
        task.status = "DONE"
        log_activity(db, task.family_id, None, "task.status_changed", "task", task.id,
                     {"status": "DONE", "via": "share_link", "link_id": link.id})
        notify(db, task.created_by_user_id, "task.completed", task.family_id,
               {"task_id": task.id, "title": task.title, "via": "share_link"})
        db.commit()
    return task


def add_note(db: Session, token: str, body: str, author_name: str | None) -> TaskNote:
    link, task = resolve(db, token)
    body = body.strip()
    if not body:
        raise ValueError("Write a note first")
    count = db.execute(select(func.count()).select_from(TaskNote).where(TaskNote.task_id == task.id)).scalar_one()
    if count >= MAX_NOTES_PER_TASK:
        raise ValueError("This task has too many notes")
    note = TaskNote(task_id=task.id, body=body, author_name=(author_name or "").strip() or None,
                    share_link_id=link.id)
    db.add(note)
    db.flush()
    log_activity(db, task.family_id, None, "task.note_added", "task", task.id, {"via": "share_link", "note_id": note.id})
    db.commit()
    return note


def check_image(image_bytes: bytes, mime_type: str) -> None:
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError("Upload a JPEG, PNG or WebP image")
    if not image_bytes:
        raise ValueError("Uploaded image is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Uploaded image must be 10 MB or smaller")
    if not image_bytes.startswith(_MAGIC[mime_type]) or (
        mime_type == "image/webp" and image_bytes[8:12] != b"WEBP"
    ):
        raise ValueError("The file is not a JPEG, PNG or WebP image")


def add_image(db: Session, token: str, image_bytes: bytes, mime_type: str) -> TaskImage:
    link, task = resolve(db, token)
    check_image(image_bytes, mime_type)
    count = db.execute(select(func.count()).select_from(TaskImage).where(TaskImage.task_id == task.id)).scalar_one()
    if count >= MAX_IMAGES_PER_TASK:
        raise ValueError(f"A task can hold at most {MAX_IMAGES_PER_TASK} photos")
    image = TaskImage(task_id=task.id, content_type=mime_type, size_bytes=len(image_bytes),
                      data=image_bytes, share_link_id=link.id)
    db.add(image)
    db.flush()
    log_activity(db, task.family_id, None, "task.image_added", "task", task.id, {"via": "share_link", "image_id": image.id})
    db.commit()
    return image


def get_image(db: Session, token: str, image_id: str) -> TaskImage:
    _, task = resolve(db, token)
    image = db.get(TaskImage, image_id)
    if image is None or image.task_id != task.id:
        raise NotFound("Photo not found")
    return image
