"""Saving the family Chat: a member's conversations and every question and answer in them.

Only the member who had a conversation can read, continue or delete it.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.family_chat import FamilyChatConversation, FamilyChatMessage
from app.services.errors import NotFound
from app.services.families import get_family

TITLE_LENGTH = 60
LIST_LIMIT = 50
HISTORY_TURNS = 12
MAX_IMPORT = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def own_conversation(db: Session, user_id: str, family_id: str, conversation_id: str) -> FamilyChatConversation:
    convo = db.get(FamilyChatConversation, conversation_id)
    if convo is None or convo.user_id != user_id or convo.family_id != family_id:
        raise NotFound("Chat not found")
    return convo


def start_or_get(
    db: Session, user_id: str, family_id: str, conversation_id: str | None, first_text: str
) -> FamilyChatConversation:
    """The conversation to add to: the given one (must be the member's own), or a new one titled by the question."""
    if conversation_id:
        return own_conversation(db, user_id, family_id, conversation_id)
    convo = FamilyChatConversation(
        family_id=family_id, user_id=user_id, title=" ".join(first_text.split())[:TITLE_LENGTH] or "Chat"
    )
    db.add(convo)
    db.flush()
    return convo


def messages(db: Session, conversation_id: str) -> list[FamilyChatMessage]:
    return list(
        db.execute(
            select(FamilyChatMessage)
            .where(FamilyChatMessage.conversation_id == conversation_id)
            .order_by(FamilyChatMessage.seq)
        ).scalars()
    )


def history(db: Session, conversation_id: str) -> list[dict[str, str]]:
    """The last turns, for answering a follow-up question in context."""
    return [{"role": m.role, "text": m.text[:4000]} for m in messages(db, conversation_id)[-HISTORY_TURNS:]]


def add(
    db: Session, convo: FamilyChatConversation, role: str, text: str,
    destination: str | None = None, source: str | None = None,
) -> FamilyChatMessage:
    last = db.execute(
        select(func.max(FamilyChatMessage.seq)).where(FamilyChatMessage.conversation_id == convo.id)
    ).scalar()
    row = FamilyChatMessage(
        conversation_id=convo.id, seq=(last or 0) + 1, role=role, text=text,
        destination=destination, source=source,
    )
    db.add(row)
    convo.updated_at = _now()
    db.flush()
    return row


def list_conversations(db: Session, user_id: str, family_id: str) -> list[tuple[FamilyChatConversation, int]]:
    get_family(db, user_id, family_id)  # members only
    counts = (
        select(FamilyChatMessage.conversation_id, func.count().label("n"))
        .group_by(FamilyChatMessage.conversation_id)
        .subquery()
    )
    rows = db.execute(
        select(FamilyChatConversation, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.conversation_id == FamilyChatConversation.id)
        .where(FamilyChatConversation.user_id == user_id, FamilyChatConversation.family_id == family_id)
        .order_by(FamilyChatConversation.updated_at.desc(), FamilyChatConversation.created_at.desc())
        .limit(LIST_LIMIT)
    ).all()
    return [(c, int(n)) for c, n in rows]


def get_conversation(
    db: Session, user_id: str, family_id: str, conversation_id: str
) -> tuple[FamilyChatConversation, list[FamilyChatMessage]]:
    get_family(db, user_id, family_id)
    convo = own_conversation(db, user_id, family_id, conversation_id)
    return convo, messages(db, convo.id)


def delete_conversation(db: Session, user_id: str, family_id: str, conversation_id: str) -> None:
    get_family(db, user_id, family_id)
    convo = own_conversation(db, user_id, family_id, conversation_id)
    db.execute(delete(FamilyChatMessage).where(FamilyChatMessage.conversation_id == convo.id))
    db.delete(convo)
    db.commit()


def log_exchange(
    db: Session, user_id: str, family_id: str, conversation_id: str | None, text: str, reply: str,
    destination: str | None,
) -> FamilyChatConversation:
    """A question the page answered itself (a link to the page that does it): save both lines."""
    get_family(db, user_id, family_id)
    convo = start_or_get(db, user_id, family_id, conversation_id, text)
    add(db, convo, "user", text)
    add(db, convo, "assistant", reply, destination, "page")
    db.commit()
    return convo


def import_conversations(db: Session, user_id: str, family_id: str, items: list[dict]) -> int:
    """Chats kept in the browser before chats were saved: copy them in once. Empty ones are skipped."""
    get_family(db, user_id, family_id)
    imported = 0
    for item in items[:MAX_IMPORT]:
        msgs = [m for m in item.get("messages", []) if m.get("text", "").strip()]
        if not msgs:
            continue
        convo = FamilyChatConversation(
            family_id=family_id, user_id=user_id, title=(item.get("title") or msgs[0]["text"]).strip()[:TITLE_LENGTH]
        )
        db.add(convo)
        db.flush()
        for m in msgs:
            add(db, convo, m["role"], m["text"], m.get("destination"))
        imported += 1
    db.commit()
    return imported
