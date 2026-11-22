"""The signed-in parent's daily check-in: start/resume it, answer by text or voice, hear the bot's reply."""

import base64
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.checkin import HealthCheckin
from app.models.medicine import Medicine
from app.models.user import User
from app.schemas import (
    ChatMessageOut,
    CheckinOut,
    ParentTextIn,
    ReminderDueOut,
    TurnMessageOut,
    TurnOut,
    VoiceTurnOut,
)
from app.services import checkin as engine
from app.services.adapters.speech import SpeechUnavailable, get_speech_to_text, get_text_to_speech
from app.services.doses import _aware, logged_today
from app.services.parent_context import ParentContext, resolve_parent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/parent", tags=["parent"])

MAX_AUDIO_BYTES = 2 * 1024 * 1024
VOICE_UNAVAILABLE = "Voice isn't available right now. Please type instead."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _messages(db: Session, checkin: HealthCheckin) -> list[ChatMessageOut]:
    return [
        ChatMessageOut(sender=m.sender, text=m.text, created_at=_aware(m.created_at))
        for m in engine.conversation(db, checkin)
    ]


def _reminders_due(db: Session, ctx: ParentContext, now: datetime) -> list[ReminderDueOut]:
    out = []
    for row in logged_today(db, ctx.profile, now).values():
        remind_at = _aware(row.remind_at)
        if remind_at is None or remind_at <= now or row.status == "taken":
            continue
        med = db.get(Medicine, row.medicine_id)
        out.append(ReminderDueOut(
            medicine_id=row.medicine_id, name=med.display_name if med else "", slot=row.slot, remind_at=remind_at,
        ))
    return sorted(out, key=lambda r: (r.remind_at, r.name))


def _speak(texts: list[str], language: str) -> tuple[str | None, str | None]:
    if not texts:
        return None, None
    try:
        audio, mime = get_text_to_speech().synthesize(" ".join(texts), language)
    except SpeechUnavailable:
        logger.info("Text-to-speech unavailable; replying with text only")
        return None, None
    return base64.b64encode(audio).decode("ascii"), mime


def _turn_fields(turn: engine.Turn, language: str) -> dict:
    audio, audio_type = _speak(turn.bot_messages, language)
    return {
        "messages": [TurnMessageOut(sender="bot", text=t) for t in turn.bot_messages],
        "step": turn.checkin.step,
        # Stays true for the rest of the day once anything urgent was reported.
        "urgent": turn.urgent,
        "call_number": turn.call_number,
        "audio": audio,
        "audio_type": audio_type,
    }


@router.get("/checkin", response_model=CheckinOut)
def get_checkin(db: Session = DbSession, user: User = CurrentUser) -> CheckinOut:
    ctx = resolve_parent(db, user)
    now = _now()
    turn = engine.start_or_resume(db, ctx, now)
    return CheckinOut(
        checkin_id=turn.checkin.id,
        step=turn.checkin.step,
        messages=_messages(db, turn.checkin),
        call_number=turn.call_number,
        language=ctx.language,
        reminders_due=_reminders_due(db, ctx, now),
    )


@router.post("/checkin/text", response_model=TurnOut)
def post_text(body: ParentTextIn, db: Session = DbSession, user: User = CurrentUser) -> TurnOut:
    ctx = resolve_parent(db, user)
    turn = engine.handle_parent_text(db, ctx, body.text, _now())
    return TurnOut(**_turn_fields(turn, ctx.language))


@router.post("/checkin/voice", response_model=VoiceTurnOut)
def post_voice(
    file: UploadFile = File(...), db: Session = DbSession, user: User = CurrentUser
) -> VoiceTurnOut:
    ctx = resolve_parent(db, user)
    # Read one byte past the limit to detect oversized clips without loading them whole.
    audio = file.file.read(MAX_AUDIO_BYTES + 1)
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Voice message is too long (max 2 MB)")
    if not audio:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Voice message is empty")
    try:
        transcript = get_speech_to_text().transcribe(audio, ctx.language, file.content_type or "")
    except SpeechUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, VOICE_UNAVAILABLE) from None
    transcript = (transcript or "").strip()
    if not transcript:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, VOICE_UNAVAILABLE)
    turn = engine.handle_parent_text(db, ctx, transcript, _now())
    return VoiceTurnOut(**_turn_fields(turn, ctx.language), transcript=transcript)
