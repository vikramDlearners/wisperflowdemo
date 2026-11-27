"""Shareable task links.

Family routes (signed in, tasks.create) make, show and revoke a task's link.
Public routes take only the link token: they view that one task, mark it done, add notes
and upload photos. Unknown or forged tokens get 404; revoked or expired links get 410.
"""

from fastapi import APIRouter, File, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.task_link import TaskImage, TaskNote, TaskShareLink
from app.models.user import User
from app.schemas import (
    TaskLinkImageOut,
    TaskLinkNoteIn,
    TaskLinkNoteOut,
    TaskLinkView,
    TaskShareLinkOut,
)
from app.services import task_links as svc
from app.services.prescription_scan import MAX_IMAGE_BYTES

family_router = APIRouter(prefix="/api/families/{family_id}/tasks/{task_id}/share-link", tags=["task links"])
public_router = APIRouter(prefix="/api/task-links/{token}", tags=["task links"])

# The token is the only credential: keep link pages out of caches and referrers.
_PRIVATE = {"Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer"}


def _link_out(link: TaskShareLink) -> TaskShareLinkOut:
    token = svc.token_for(link)
    return TaskShareLinkOut(token=token, path=f"/task-link/{token}", expires_at=svc.as_utc(link.expires_at))


def _note_out(note: TaskNote) -> TaskLinkNoteOut:
    return TaskLinkNoteOut(id=note.id, body=note.body, author_name=note.author_name, created_at=note.created_at)


def _image_out(token: str, image: TaskImage) -> TaskLinkImageOut:
    return TaskLinkImageOut(
        id=image.id,
        url=f"/api/task-links/{token}/images/{image.id}",
        content_type=image.content_type,
        size_bytes=image.size_bytes,
        created_at=image.created_at,
    )


@family_router.post("", response_model=TaskShareLinkOut)
def create_or_get_link(
    family_id: str, task_id: str, db: Session = DbSession, user: User = CurrentUser
) -> TaskShareLinkOut:
    return _link_out(svc.get_or_create_link(db, user.id, family_id, task_id))


@family_router.delete("", status_code=204)
def revoke_link(family_id: str, task_id: str, db: Session = DbSession, user: User = CurrentUser) -> Response:
    svc.revoke_links(db, user.id, family_id, task_id)
    return Response(status_code=204)


@public_router.get("", response_model=TaskLinkView)
def view_task(token: str, response: Response, db: Session = DbSession) -> TaskLinkView:
    response.headers.update(_PRIVATE)
    data = svc.view(db, token)
    task = data["task"]
    return TaskLinkView(
        id=task.id,
        title=task.title,
        description=task.description,
        due_at=task.due_at,
        status=task.status,
        priority=task.priority,
        assignee_name=data["assignee_name"],
        link_expires_at=data["expires_at"],
        notes=[_note_out(n) for n in data["notes"]],
        images=[_image_out(token, i) for i in data["images"]],
    )


@public_router.post("/complete", status_code=204)
def complete_task(token: str, db: Session = DbSession) -> Response:
    svc.complete(db, token)
    return Response(status_code=204, headers=_PRIVATE)


@public_router.post("/notes", response_model=TaskLinkNoteOut, status_code=201)
def add_note(token: str, body: TaskLinkNoteIn, response: Response, db: Session = DbSession) -> TaskLinkNoteOut:
    response.headers.update(_PRIVATE)
    return _note_out(svc.add_note(db, token, body.body, body.author_name))


@public_router.post("/images", response_model=TaskLinkImageOut, status_code=201)
def upload_image(
    token: str, response: Response, file: UploadFile = File(...), db: Session = DbSession
) -> TaskLinkImageOut:
    response.headers.update(_PRIVATE)
    # Read one byte past the limit so the service can reject oversized uploads.
    image_bytes = file.file.read(MAX_IMAGE_BYTES + 1)
    return _image_out(token, svc.add_image(db, token, image_bytes, file.content_type or ""))


@public_router.get("/images/{image_id}")
def get_image(token: str, image_id: str, db: Session = DbSession) -> Response:
    image = svc.get_image(db, token, image_id)
    return Response(
        content=image.data,
        media_type=image.content_type,
        headers={**_PRIVATE, "X-Content-Type-Options": "nosniff"},
    )
