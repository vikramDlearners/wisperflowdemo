"""Emergencies: noted when the parent raises one, shown to the family until someone marks it completed."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.checkin import HealthCheckin
from app.models.emergency import Emergency
from app.services.activity import log_activity
from app.services.errors import NotFound
from app.services.parent_context import ParentContext
from app.services.permissions import require

OPEN, COMPLETED = "open", "completed"
COMPLETE_PERMISSION = "tasks.update_own"  # managers and caregivers, not viewers


def note_emergency(
    db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str, source: str, now: datetime
) -> None:
    """Stage the emergency. The caller commits. More of the same adds to today's open one."""
    row = db.execute(
        select(Emergency)
        .where(Emergency.checkin_id == checkin.id, Emergency.source == source, Emergency.status == OPEN)
        .with_for_update()
    ).scalars().first()
    if row is not None:
        if text not in row.text.split("\n"):
            row.text = f"{row.text}\n{text}"
        return
    db.add(Emergency(
        family_id=ctx.family_id, care_profile_id=ctx.profile.id, checkin_id=checkin.id,
        reported_by_user_id=ctx.user_id, text=text, source=source, status=OPEN, created_at=now,
    ))


def open_emergencies(db: Session, family_id: str) -> list[dict[str, Any]]:
    """The whole family's open emergencies, newest first, whichever parent the overview is showing."""
    rows = db.execute(
        select(Emergency, CareProfile.display_name)
        .join(CareProfile, CareProfile.id == Emergency.care_profile_id)
        .where(Emergency.family_id == family_id, Emergency.status == OPEN)
        .order_by(Emergency.created_at.desc(), Emergency.id)
    ).all()
    return [
        {"id": e.id, "care_profile_id": e.care_profile_id, "parent_name": name, "text": e.text,
         "source": e.source, "created_at": e.created_at}
        for e, name in rows
    ]


def complete_emergency(db: Session, actor_id: str, family_id: str, emergency_id: str, now: datetime) -> None:
    require(db, actor_id, family_id, COMPLETE_PERMISSION)
    row = db.execute(
        select(Emergency).where(Emergency.id == emergency_id, Emergency.family_id == family_id).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise NotFound("Emergency not found")
    if row.status == COMPLETED:
        return  # someone else in the family already did it
    row.status, row.completed_at, row.completed_by_user_id = COMPLETED, now, actor_id
    log_activity(db, family_id, actor_id, "emergency.completed", "emergency", row.id, {})
    db.commit()
