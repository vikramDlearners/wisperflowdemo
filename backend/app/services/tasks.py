"""Family tasks. Assigning a task notifies the assignee and writes activity."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import FamilyMember
from app.models.task import Task
from app.services.activity import log_activity
from app.services.errors import NotFound
from app.services.notifications import notify
from app.services.permissions import PermissionDenied, get_membership, permission_codes_for, require

TASK_STATUSES = frozenset({"OPEN", "IN_PROGRESS", "DONE"})


def list_tasks(db: Session, actor_id: str, family_id: str) -> list[Task]:
    require(db, actor_id, family_id, "tasks.view")
    stmt = select(Task).where(Task.family_id == family_id).order_by(Task.created_at.desc())
    return list(db.execute(stmt).scalars())


def _assert_active_member(db: Session, family_id: str, user_id: str) -> None:
    exists = db.execute(
        select(FamilyMember.id).where(
            FamilyMember.family_id == family_id,
            FamilyMember.user_id == user_id,
            FamilyMember.status == "active",
        )
    ).first()
    if exists is None:
        raise ValueError("Assignee must be an active member of this family")


def create_task(
    db: Session,
    actor_id: str,
    family_id: str,
    title: str,
    description: str | None = None,
    due_at: datetime | None = None,
    priority: str = "normal",
    assigned_to_user_id: str | None = None,
    care_profile_id: str | None = None,
) -> Task:
    require(db, actor_id, family_id, "tasks.create")
    if assigned_to_user_id:
        require(db, actor_id, family_id, "tasks.assign")
        _assert_active_member(db, family_id, assigned_to_user_id)
    task = Task(
        family_id=family_id,
        title=title.strip(),
        description=description,
        due_at=due_at,
        priority=priority,
        care_profile_id=care_profile_id,
        assigned_to_user_id=assigned_to_user_id,
        status="OPEN",
        created_by_user_id=actor_id,
    )
    db.add(task)
    db.flush()
    log_activity(db, family_id, actor_id, "task.created", "task", task.id, {"title": task.title})
    if assigned_to_user_id:
        notify(db, assigned_to_user_id, "task.assigned", family_id, {"task_id": task.id, "title": task.title})
    db.commit()
    return task


def get_task(db: Session, actor_id: str, family_id: str, task_id: str) -> Task:
    require(db, actor_id, family_id, "tasks.view")
    return _task_in_family(db, family_id, task_id)


def update_task(db: Session, actor_id: str, family_id: str, task_id: str, changes: dict) -> Task:
    """Edit title, description, due date or priority. Assignee changes go through assign_task."""
    require(db, actor_id, family_id, "tasks.create")
    task = _task_in_family(db, family_id, task_id)
    if "title" in changes:
        if not changes["title"] or not changes["title"].strip():
            raise ValueError("title cannot be empty")
        task.title = changes["title"].strip()
    if "description" in changes:
        task.description = changes["description"]
    if "due_at" in changes:
        task.due_at = changes["due_at"]
    if "priority" in changes:
        task.priority = changes["priority"]
    log_activity(db, family_id, actor_id, "task.updated", "task", task.id, {"fields": sorted(changes)})
    db.commit()
    return task


def delete_task(db: Session, actor_id: str, family_id: str, task_id: str) -> None:
    require(db, actor_id, family_id, "tasks.assign")
    task = _task_in_family(db, family_id, task_id)
    log_activity(db, family_id, actor_id, "task.deleted", "task", task.id, {"title": task.title})
    db.delete(task)
    db.commit()


def assign_task(db: Session, actor_id: str, family_id: str, task_id: str, assignee_id: str) -> Task:
    require(db, actor_id, family_id, "tasks.assign")
    task = _task_in_family(db, family_id, task_id)
    _assert_active_member(db, family_id, assignee_id)
    task.assigned_to_user_id = assignee_id
    log_activity(db, family_id, actor_id, "task.assigned", "task", task.id, {"assignee": assignee_id})
    notify(db, assignee_id, "task.assigned", family_id, {"task_id": task.id, "title": task.title})
    db.commit()
    return task


def update_task_status(
    db: Session, actor_id: str, family_id: str, task_id: str, status: str
) -> Task:
    """Members with tasks.update_own may change only tasks assigned to themselves,
    unless they also hold tasks.assign."""
    require(db, actor_id, family_id, "tasks.update_own")
    if status not in TASK_STATUSES:
        raise ValueError("status must be OPEN, IN_PROGRESS or DONE")
    task = _task_in_family(db, family_id, task_id)
    codes = permission_codes_for(db, get_membership(db, actor_id, family_id))
    if "tasks.assign" not in codes and task.assigned_to_user_id != actor_id:
        raise PermissionDenied("You can only update tasks assigned to you")
    task.status = status
    log_activity(db, family_id, actor_id, "task.status_changed", "task", task.id, {"status": status})
    db.commit()
    return task


def notify_task(db: Session, actor_id: str, family_id: str, task_id: str) -> Task:
    """Notify the assignee, or every other active member when the task is unassigned."""
    require(db, actor_id, family_id, "tasks.update_own")
    task = _task_in_family(db, family_id, task_id)
    if task.assigned_to_user_id:
        recipient_ids = [task.assigned_to_user_id]
    else:
        recipient_ids = list(
            db.execute(
                select(FamilyMember.user_id).where(
                    FamilyMember.family_id == family_id,
                    FamilyMember.status == "active",
                    FamilyMember.user_id != actor_id,
                )
            ).scalars()
        )
    for user_id in recipient_ids:
        notify(db, user_id, "task.notified", family_id=family_id, payload={"task_id": task.id, "title": task.title})
    log_activity(db, family_id, actor_id, "task.notified", "task", task.id, {"title": task.title})
    db.commit()
    return task


def _task_in_family(db: Session, family_id: str, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.family_id != family_id:
        raise NotFound("Task not found")
    return task
