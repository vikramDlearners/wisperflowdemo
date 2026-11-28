"""The signed-in parent's daily check-in: start/resume it, answer by text or voice, hear the bot's reply."""

import base64
from dataclasses import asdict
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, File, Header, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import _photo_response
from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.models.checkin import HealthCheckin
from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.models.membership import FamilyMember
from app.models.user import User
from app.schemas import (
    ChatMessageOut,
    CheckinOut,
    EmergencyOut,
    ParentLanguageIn,
    ParentMedicineOut,
    ParentProfileOut,
    ParentSpeakIn,
    ParentTextIn,
    ReminderDueOut,
    SpeechOut,
    TurnMessageOut,
    TurnOut,
    VoiceTurnOut,
)
from app.services import care as care_svc
from app.services import checkin as engine
from app.services import fine_checkin, today_plan
from app.services.adapters.speech import SpeechUnavailable, get_speech_to_text, get_text_to_speech
from app.services.doses import _aware, logged_today
from app.services.parent_context import ParentContext, family_profiles, resolve_parent
from app.services.permissions import get_membership, permission_codes_for
from app.services.prescription_scan import ALLOWED_MIME_TYPES, MAX_IMAGE_BYTES
from app.services.profile import get_care_profile_onboarding
from app.services.replies import shows_photos, spoken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/parent", tags=["parent"])

# The profile chosen on the chat page ("Who is using CareCircle?"); none: the account's own profile.
ProfileId = Header(default=None, alias="X-Care-Profile-Id")

MAX_AUDIO_BYTES = 2 * 1024 * 1024
VOICE_UNAVAILABLE = "Voice isn't available right now. Please type instead."


def _can_open_portal(db: Session, ctx: ParentContext) -> bool:
    membership = get_membership(db, ctx.user_id, ctx.family_id)
    return "dashboard.view" in permission_codes_for(db, membership)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _messages(db: Session, checkin: HealthCheckin) -> list[ChatMessageOut]:
    # Only the conversation on screen now: each opening of the chat starts a new one.
    return [
        ChatMessageOut(
            sender=m.sender, text=m.text, created_at=_aware(m.created_at),
            photos=m.sender == "bot" and shows_photos(m.text),
        )
        for m in engine.session_messages(db, checkin)
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
        audio, mime = get_text_to_speech().synthesize(" ".join(spoken(t) for t in texts), language)
    except SpeechUnavailable:
        logger.info("Text-to-speech unavailable; replying with text only")
        return None, None
    except Exception:  # noqa: BLE001 - speech is optional; never fail the reply over it
        logger.exception("Text-to-speech failed; replying with text only")
        return None, None
    return base64.b64encode(audio).decode("ascii"), mime


def _turn_fields(db: Session, ctx: ParentContext, turn: engine.Turn, speak: bool = True) -> dict:
    audio, audio_type = _speak(turn.bot_messages if speak else [], ctx.language)
    return {
        "messages": [TurnMessageOut(sender="bot", text=t, photos=shows_photos(t)) for t in turn.bot_messages],
        "step": turn.checkin.step,
        "language": ctx.language,
        # Stays true for the rest of the day once anything urgent was reported.
        "urgent": turn.urgent,
        "call_number": turn.call_number,
        "help_number": engine.call_number(db, ctx),
        "audio": audio,
        "audio_type": audio_type,
    }


@router.get("/checkin", response_model=CheckinOut)
def get_checkin(
    new_session: bool = False, speak: bool = True, db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId,
) -> CheckinOut:
    """Today's conversation. new_session=true (the chat page just opened) starts a new conversation on screen:
    a fresh greeting and today's open question; earlier messages stay stored but are not returned.
    speak=false (voice is off in the chat): no speech is made."""
    ctx = resolve_parent(db, user, profile_id)
    now = _now()
    turn = engine.start_new_session(db, ctx, now) if new_session else engine.start_or_resume(db, ctx, now)
    return _checkin_out(db, ctx, turn, now, speak)


@router.put("/language", response_model=CheckinOut)
def set_language(
    body: ParentLanguageIn, speak: bool = True, db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId,
) -> CheckinOut:
    """The parent picks the chat's language: greet again and repeat today's open question in it."""
    ctx = resolve_parent(db, user, profile_id)
    care_svc.switch_chat_language(db, ctx.profile, body.language)
    ctx = resolve_parent(db, user, profile_id)
    now = _now()
    return _checkin_out(db, ctx, engine.start_new_session(db, ctx, now, force=True), now, speak)


@router.post("/speak", response_model=SpeechOut)
def speak_message(
    body: ParentSpeakIn, db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId,
) -> SpeechOut:
    """The parent tapped a bot message. Only messages on their own screen are spoken, never any other text."""
    ctx = resolve_parent(db, user, profile_id)
    checkin = engine.current_checkin(db, ctx, _now())
    if checkin is None or not any(
        m.sender == "bot" and m.text == body.text for m in engine.session_messages(db, checkin)
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    audio, audio_type = _speak([body.text], ctx.language)
    return SpeechOut(audio=audio, audio_type=audio_type)


def _checkin_out(
    db: Session, ctx: ParentContext, turn: engine.Turn, now: datetime, speak: bool
) -> CheckinOut:
    # Only what this request stored is spoken (a reload that adds nothing stays silent).
    audio, audio_type = _speak(turn.bot_messages if speak else [], ctx.language)
    return CheckinOut(
        checkin_id=turn.checkin.id,
        family_id=ctx.family_id,
        can_open_portal=_can_open_portal(db, ctx),
        step=turn.checkin.step,
        messages=_messages(db, turn.checkin),
        call_number=turn.call_number,
        help_number=engine.call_number(db, ctx),
        language=ctx.language,
        recommended_language=care_svc.recommended_language(db, ctx.profile),
        reminders_due=_reminders_due(db, ctx, now),
        audio=audio,
        audio_type=audio_type,
    )


@router.post("/checkin/text", response_model=TurnOut)
def post_text(
    body: ParentTextIn, speak: bool = True, db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId,
) -> TurnOut:
    ctx = resolve_parent(db, user, profile_id)
    turn = engine.handle_parent_text(db, ctx, body.text, _now())
    return TurnOut(**_turn_fields(db, ctx, turn, speak))


@router.post("/checkin/medicine-photo", response_model=TurnOut)
def post_medicine_photo(
    file: UploadFile = File(...), speak: bool = True,
    db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId,
) -> TurnOut:
    """A photo of a medicine the parent is unsure about: which of their medicines it is, when to take it,
    and whether the doctor prescribed it."""
    ctx = resolve_parent(db, user, profile_id)
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Please send a JPEG, PNG or WebP photo")
    image = file.file.read(MAX_IMAGE_BYTES + 1)
    if len(image) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Photo is too large (max 10 MB)")
    if not image:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Photo is empty")
    turn = engine.handle_medicine_photo(db, ctx, image, file.content_type, _now())
    return TurnOut(**_turn_fields(db, ctx, turn, speak))


@router.post("/checkin/voice", response_model=VoiceTurnOut)
def post_voice(
    file: UploadFile = File(...), db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId,
) -> VoiceTurnOut:
    ctx = resolve_parent(db, user, profile_id)
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
    return VoiceTurnOut(**_turn_fields(db, ctx, turn), transcript=transcript)


def _parent_medicine(db: Session, ctx: ParentContext, medicine_id: str) -> Medicine:
    med = db.get(Medicine, medicine_id)
    if med is None or med.care_profile_id != ctx.profile.id or not med.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medicine not found")
    return med


@router.get("/medicines", response_model=list[ParentMedicineOut])
def list_parent_medicines(
    db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId,
) -> list[ParentMedicineOut]:
    """The parent's own active medicines, so the chat can show a photo next to a medicine it names."""
    ctx = resolve_parent(db, user, profile_id)
    meds = db.execute(
        select(Medicine.id, Medicine.display_name, Medicine.image_data.isnot(None))
        .where(Medicine.care_profile_id == ctx.profile.id, Medicine.active.is_(True))
        .order_by(Medicine.created_at, Medicine.id)
    ).all()
    return [ParentMedicineOut(id=mid, name=name, has_image=has_image) for mid, name, has_image in meds]


@router.get("/medicines/{medicine_id}/image")
def get_parent_medicine_image(
    medicine_id: str, db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId,
) -> Response:
    ctx = resolve_parent(db, user, profile_id)
    med = _parent_medicine(db, ctx, medicine_id)
    if med.image_data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This medicine has no photo")
    return Response(content=med.image_data, media_type=med.image_content_type or "application/octet-stream")


def _profile_out(db: Session, user: User, profile: CareProfile) -> ParentProfileOut:
    onboarding = get_care_profile_onboarding(db, profile)
    relationship = onboarding.relationship if onboarding is not None else None
    if not relationship and profile.linked_member_id is not None:
        member = db.get(FamilyMember, profile.linked_member_id)
        relationship = member.relationship if member is not None else None
    return ParentProfileOut(
        id=profile.id,
        name=profile.greeting_name or profile.display_name,
        relationship=relationship,
        has_photo=onboarding is not None and onboarding.profile_photo_content_type is not None,
        photo_url=onboarding.profile_picture_url if onboarding is not None else None,
        own=profile.linked_user_id == user.id,
    )


@router.get("/profiles", response_model=list[ParentProfileOut])
def list_parent_profiles(db: Session = DbSession, user: User = CurrentUser) -> list[ParentProfileOut]:
    """Who this account can use the chat as (father, mother...)."""
    return [_profile_out(db, user, p) for p in family_profiles(db, user)]


@router.get("/profiles/{care_profile_id}/photo")
def get_parent_profile_photo(care_profile_id: str, db: Session = DbSession, user: User = CurrentUser) -> Response:
    ctx = resolve_parent(db, user, care_profile_id)
    return _photo_response(get_care_profile_onboarding(db, ctx.profile))


# Shown on the parent's pop-up. Only Email (and in-app notes) are sent today; WhatsApp and SMS are not wired yet.
EMERGENCY_CHANNELS = ["WhatsApp", "Email", "Text message"]


@router.post("/emergency", response_model=EmergencyOut)
def emergency(
    db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId,
) -> EmergencyOut:
    """Help -> "Yes, it's an emergency": alert the whole family now and give the number to call."""
    ctx = resolve_parent(db, user, profile_id)
    notified = engine.raise_emergency(db, ctx, _now())
    return EmergencyOut(notified=notified, channels=EMERGENCY_CHANNELS, emergency_number=settings.emergency_number)


class FineOut(BaseModel):
    day: date
    fine_at: datetime | None
    asked: bool
    family_told: bool


def _fine_out(s: fine_checkin.FineStatus) -> FineOut:
    return FineOut(day=s.day, fine_at=s.fine_at, asked=s.asked, family_told=s.family_told)


@router.get("/fine", response_model=FineOut)
def get_fine(db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId) -> FineOut:
    """Has the parent tapped "I'm fine" today, and has the app asked them yet?"""
    return _fine_out(fine_checkin.status(db, resolve_parent(db, user, profile_id), _now()))


@router.post("/fine", response_model=FineOut)
def post_fine(db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId) -> FineOut:
    """The parent tapped "I'm fine": tell the family all is well (once a day)."""
    return _fine_out(fine_checkin.press_fine(db, resolve_parent(db, user, profile_id), _now()))


@router.get("/today")
def get_today(db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId) -> dict:
    """Today only: tablets, visits in the next two days, tasks due, medicines running low, and what to tell
    the doctor when a visit is close."""
    return asdict(today_plan.today(db, resolve_parent(db, user, profile_id), _now()))


@router.post("/refills/{medicine_id}")
def ask_refill(
    medicine_id: str, db: Session = DbSession, user: User = CurrentUser, profile_id: str | None = ProfileId,
) -> dict:
    """The parent said yes to a refill: one task for the family to order it. Asking again changes nothing."""
    return asdict(today_plan.ask_refill(db, resolve_parent(db, user, profile_id), medicine_id, _now()))
