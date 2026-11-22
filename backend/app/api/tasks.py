"""Family tasks. Viewing needs tasks.view; creating and editing need tasks.create; assigning needs tasks.assign; completing and status updates need tasks.update_own; deleting needs tasks.assign."""

from fastapi import APIRouter, Response
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.task import Task
from app.models.user import User
from app.schemas import TaskAssign, TaskCreate, TaskOut, TaskStatusUpdate, TaskUpdate
from app.services import tasks as svc

router = APIRouter(prefix="/api/families/{family_id}/tasks", tags=["tasks"])


def _out(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        title=task.title,
        description=task.description,
        due_at=task.due_at,
        status=task.status,
        priority=task.priority,
        assigned_to_user_id=task.assigned_to_user_id,
        created_by_user_id=task.created_by_user_id,
    )


@router.get("", response_model=list[TaskOut])
def list_tasks(family_id: str, db: Session = DbSession, user: User = CurrentUser) -> list[TaskOut]:
    return [_out(t) for t in svc.list_tasks(db, user.id, family_id)]


@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    family_id: str, body: TaskCreate, db: Session = DbSession, user: User = CurrentUser
) -> TaskOut:
    task = svc.create_task(
        db,
        user.id,
        family_id,
        body.title,
        body.description,
        body.due_at,
        body.priority,
        body.assigned_to_user_id,
        body.care_profile_id,
    )
    return _out(task)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    family_id: str, task_id: str, db: Session = DbSession, user: User = CurrentUser
) -> TaskOut:
    return _out(svc.get_task(db, user.id, family_id, task_id))


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    family_id: str, task_id: str, body: TaskUpdate,
    db: Session = DbSession, user: User = CurrentUser,
) -> TaskOut:
    changes = body.model_dump(exclude_unset=True)
    return _out(svc.update_task(db, user.id, family_id, task_id, changes))


@router.delete("/{task_id}", status_code=204)
def delete_task(
    family_id: str, task_id: str, db: Session = DbSession, user: User = CurrentUser
) -> Response:
    svc.delete_task(db, user.id, family_id, task_id)
    return Response(status_code=204)


@router.post("/{task_id}/assign", response_model=TaskOut)
def assign_task(
    family_id: str, task_id: str, body: TaskAssign, db: Session = DbSession, user: User = CurrentUser
) -> TaskOut:
    return _out(svc.assign_task(db, user.id, family_id, task_id, body.assignee_user_id))


@router.post("/{task_id}/complete", response_model=TaskOut)
def complete_task(
    family_id: str, task_id: str, db: Session = DbSession, user: User = CurrentUser
) -> TaskOut:
    return _out(svc.update_task_status(db, user.id, family_id, task_id, "DONE"))


@router.post("/{task_id}/notify", response_model=TaskOut)
def notify_task(
    family_id: str, task_id: str, db: Session = DbSession, user: User = CurrentUser
) -> TaskOut:
    return _out(svc.notify_task(db, user.id, family_id, task_id))


@router.patch("/{task_id}/status", response_model=TaskOut)
def update_task_status(
    family_id: str, task_id: str, body: TaskStatusUpdate,
    db: Session = DbSession, user: User = CurrentUser,
) -> TaskOut:
    return _out(svc.update_task_status(db, user.id, family_id, task_id, body.status))
