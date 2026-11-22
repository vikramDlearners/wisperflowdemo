"""In-app notifications for the signed-in user. Each user sees only their own notifications."""

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.notification import Notification
from app.models.user import User
from app.schemas import NotificationOut, NotificationSummaryOut
from app.services import notification_summary as summary_svc
from app.services import notifications as svc

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _out(row: Notification) -> NotificationOut:
    return NotificationOut(
        id=row.id,
        family_id=row.family_id,
        type=row.type,
        payload=row.payload,
        status=row.status,
        created_at=row.created_at,
    )


@router.get("", response_model=list[NotificationOut])
def list_notifications(db: Session = DbSession, user: User = CurrentUser) -> list[NotificationOut]:
    return [_out(n) for n in svc.list_for_user(db, user.id)]


@router.get("/summary", response_model=NotificationSummaryOut)
def notification_summary(db: Session = DbSession, user: User = CurrentUser) -> NotificationSummaryOut:
    return NotificationSummaryOut(**summary_svc.summarise_recent(db, user.id, datetime.now(timezone.utc)))


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: str, db: Session = DbSession, user: User = CurrentUser
) -> NotificationOut:
    return _out(svc.mark_read(db, user.id, notification_id))
