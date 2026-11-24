"""Summarise each finished part of a parent's chat, save it, and turn important points into tasks.

A part is the messages since the last summary of that day's check-in. It counts as finished once the check-in
is done and quiet for a minute, or quiet for half an hour whatever step it stopped at. Gemini writes the
summary and picks the important points; without Gemini (no key, or a failure) a simple summary is saved and an
urgent day becomes a task. Each important point becomes an OPEN task for every caretaker (Caregiver role) and
manager (Family manager role) of the family, who are notified.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.care_profile import CareProfile
from app.models.checkin import ChatMessage, HealthCheckin
from app.models.conversation_summary import ConversationSummary
from app.models.membership import FamilyMember
from app.models.task import Task
from app.models.user import User
from app.services import understanding
from app.services.activity import log_activity
from app.services.notifications import notify
from app.services.permissions import role_name_for

logger = logging.getLogger(__name__)

FINISHED_STEPS = ("note", "done")  # a quiet chat may end with "anything to note down?" unanswered
QUIET_AFTER_DONE = timedelta(minutes=1)
QUIET_ANY_STEP = timedelta(minutes=30)
LOOK_BACK = timedelta(days=2)
TASK_ROLES = ("Caregiver", "Family manager")
MAX_TASKS = 3
TITLE_MAX, DETAIL_MAX = 200, 1000


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _last_summarised_seq(db: Session, checkin_id: str) -> int:
    return db.execute(
        select(func.max(ConversationSummary.to_seq)).where(ConversationSummary.checkin_id == checkin_id)
    ).scalar() or 0


def _new_messages(db: Session, checkin: HealthCheckin) -> list[ChatMessage]:
    after = _last_summarised_seq(db, checkin.id)
    return list(db.execute(
        select(ChatMessage)
        .where(ChatMessage.checkin_id == checkin.id, ChatMessage.seq > after)
        .order_by(ChatMessage.seq, ChatMessage.created_at, ChatMessage.id)
    ).scalars())


def _finished(checkin: HealthCheckin, now: datetime) -> bool:
    quiet = now - (_aware(checkin.updated_at) or now)
    return (checkin.step in FINISHED_STEPS and quiet >= QUIET_AFTER_DONE) or quiet >= QUIET_ANY_STEP


def _transcript(messages: list[ChatMessage]) -> str:
    return "\n".join(f"{'Parent' if m.sender == 'parent' else 'Assistant'}: {m.text}" for m in messages)


def _prompt(profile: CareProfile, checkin: HealthCheckin, messages: list[ChatMessage]) -> str:
    return (
        "You summarise a short daily check-in chat between an elderly parent and a care assistant, for the "
        "parent's family. The chat may be in English, Tamil, Hindi, Telugu, Malayalam or Kannada.\n"
        f"Parent: {profile.display_name}. Date: {checkin.checkin_date.isoformat()}.\n\n"
        "Return JSON only, in English:\n"
        '{"summary": "2-4 plain sentences: how the parent is, medicines taken or not, meals, anything else said", '
        '"important": [{"title": "short action for the family (max 12 words)", "detail": "what the parent said", '
        '"priority": "high or normal"}]}\n'
        "List in important only things a family member should act on: a health complaint or symptom, a fall or "
        "emergency, medicine not taken or run out, something the parent asked for. Use high only for safety "
        "or urgent health problems. Use an empty list when nothing needs action. Do not give medical advice and "
        "do not invent anything that was not said.\n\n"
        f"Chat:\n{_transcript(messages)}"
    )


def _clean_important(items) -> list[dict]:
    out: list[dict] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        title = " ".join(str(item.get("title") or "").split())[:TITLE_MAX]
        if not title:
            continue
        detail = " ".join(str(item.get("detail") or "").split())[:DETAIL_MAX] or None
        priority = "high" if str(item.get("priority") or "").strip().lower() == "high" else "normal"
        out.append({"title": title, "detail": detail, "priority": priority})
        if len(out) == MAX_TASKS:
            break
    return out


def _from_gemini(profile: CareProfile, checkin: HealthCheckin, messages: list[ChatMessage]) -> tuple[str, list[dict]]:
    result = understanding.ask_gemini(_prompt(profile, checkin, messages))
    summary = " ".join(str(result.get("summary") or "").split())
    if not summary:
        raise ValueError("Gemini returned no summary")
    return summary, _clean_important(result.get("important"))


def _from_rules(profile: CareProfile, checkin: HealthCheckin, messages: list[ChatMessage]) -> tuple[str, list[dict]]:
    name = profile.display_name
    said = [m.text for m in messages if m.sender == "parent"]
    summary = f"{name}'s check-in on {checkin.checkin_date.strftime('%d %b %Y')}. {name} said: " + "; ".join(
        f'"{t}"' for t in said
    ) + "."
    important = []
    if checkin.urgent:
        summary += " Something needed attention today and the family was alerted."
        important.append({"title": f"Call {name} now: something needed attention",
                          "detail": "; ".join(said) or None, "priority": "high"})
    return summary, important


def _assignees(db: Session, checkin: HealthCheckin) -> list[User]:
    members = db.execute(
        select(FamilyMember)
        .where(FamilyMember.family_id == checkin.family_id, FamilyMember.status == "active")
        .order_by(FamilyMember.created_at, FamilyMember.id)
    ).scalars()
    users: list[User] = []
    for m in members:
        if m.user_id == checkin.parent_user_id or role_name_for(db, m) not in TASK_ROLES:
            continue
        user = db.get(User, m.user_id)
        if user is not None and user not in users:
            users.append(user)
    return users


def _create_tasks(db: Session, checkin: HealthCheckin, important: list[dict]) -> int:
    created = 0
    for user in _assignees(db, checkin):
        for item in important:
            exists = db.execute(select(Task.id).where(
                Task.care_profile_id == checkin.care_profile_id, Task.assigned_to_user_id == user.id,
                Task.title == item["title"], Task.status != "DONE",
            )).first()
            if exists is not None:
                continue  # the same point from a later part of the chat: no duplicate task
            task = Task(
                family_id=checkin.family_id, care_profile_id=checkin.care_profile_id, title=item["title"],
                description=item["detail"], priority=item["priority"], assigned_to_user_id=user.id,
                status="OPEN", created_by_user_id=checkin.parent_user_id,
            )
            db.add(task)
            db.flush()
            log_activity(db, checkin.family_id, checkin.parent_user_id, "task.created", "task", task.id,
                         {"title": task.title, "source": "chat_summary"})
            notify(db, user.id, "task.assigned", checkin.family_id, {"task_id": task.id, "title": task.title})
            created += 1
    return created


def _summarise(db: Session, checkin: HealthCheckin, messages: list[ChatMessage], now: datetime) -> None:
    profile = db.get(CareProfile, checkin.care_profile_id)
    source = "rules"
    summary, important = _from_rules(profile, checkin, messages)
    if settings.gemini_api_key:
        try:
            summary, important = _from_gemini(profile, checkin, messages)
            source = "gemini"
        except Exception as exc:  # noqa: BLE001 - the simple summary is kept
            logger.warning("Gemini chat summary failed, using the simple summary: %s: %s", type(exc).__name__, exc)
    db.add(ConversationSummary(
        family_id=checkin.family_id, care_profile_id=checkin.care_profile_id, checkin_id=checkin.id,
        from_seq=messages[0].seq, to_seq=messages[-1].seq, summary=summary, important=important,
        source=source, created_at=now,
    ))
    _create_tasks(db, checkin, important)
    db.commit()


def summarise_conversations(db: Session, now: datetime) -> int:
    """Summarise every finished, not yet summarised part of recent parent chats. Returns parts summarised."""
    now = _aware(now)
    checkin_ids = list(db.execute(
        select(HealthCheckin.id).where(HealthCheckin.updated_at >= now - LOOK_BACK).order_by(HealthCheckin.id)
    ).scalars())
    done = 0
    for checkin_id in checkin_ids:
        try:
            checkin = db.get(HealthCheckin, checkin_id)
            if checkin is None or not _finished(checkin, now):
                continue
            messages = _new_messages(db, checkin)
            if not any(m.sender == "parent" for m in messages):
                continue
            _summarise(db, checkin, messages, now)
            done += 1
        except Exception:  # noqa: BLE001 - one bad check-in must not block every later one
            db.rollback()
            logger.exception("Chat summary failed for check-in %s", checkin_id)
    return done
