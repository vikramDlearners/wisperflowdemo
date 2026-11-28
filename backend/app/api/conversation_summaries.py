"""Conversation summaries of parent check-ins, read-only. Viewing needs activity.view."""

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.checkin import HealthCheckin
from app.models.conversation_summary import ConversationSummary
from app.models.user import User
from app.schemas import ConversationSummaryOut
from app.services.care_circle import shares_chats
from app.services.permissions import require

router = APIRouter(prefix="/api/families/{family_id}/conversation-summaries", tags=["conversation-summaries"])


@router.get("", response_model=list[ConversationSummaryOut])
def list_conversation_summaries(
    family_id: str, db: Session = DbSession, user: User = CurrentUser
) -> list[ConversationSummaryOut]:
    require(db, user.id, family_id, "activity.view")
    rows = (
        db.query(ConversationSummary)
        .filter(ConversationSummary.family_id == family_id)
        .order_by(ConversationSummary.created_at.desc())
        .all()
    )
    # Chats from an urgent check-in always reach the family; the rest only if the parent shares chats.
    hidden = {pid for pid in {r.care_profile_id for r in rows} if not shares_chats(db, pid)}
    if hidden:
        urgent = set(db.execute(select(HealthCheckin.id).where(
            HealthCheckin.id.in_({r.checkin_id for r in rows}), HealthCheckin.urgent.is_(True))).scalars())
        rows = [r for r in rows if r.care_profile_id not in hidden or r.checkin_id in urgent]
    return [
        ConversationSummaryOut(
            id=row.id,
            checkin_id=row.checkin_id,
            care_profile_id=row.care_profile_id,
            from_seq=row.from_seq,
            to_seq=row.to_seq,
            summary=row.summary,
            important=row.important,
            source=row.source,
            created_at=row.created_at,
        )
        for row in rows
    ]
