"""Video check-ins between a family member and the parent, browser to browser over WebRTC.

The server only passes the two descriptions across. Each browser gathers its network candidates before it
sends its description, so no separate candidate exchange is needed. The family member's browser posts the
offer; the parent's app asks every few seconds whether a call is ringing, and answers by itself when the
parent turned on "answer video calls by themself" (ParentPrivacy.video_auto_answer), or shows a big green
button when not. A call nobody answers stops ringing after a minute.

Starting a call needs dashboard.view.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_circle import VideoCall
from app.models.user import User
from app.services.care_circle import _profile_in, privacy
from app.services.errors import NotFound
from app.services.parent_context import ParentContext
from app.services.permissions import require
from app.services.task_links import as_utc

RING = timedelta(seconds=60)
MAX_SDP = 20_000


def _sdp(value: str) -> str:
    value = (value or "").strip()
    if not value or len(value) > MAX_SDP or not value.startswith("v=0"):
        raise ValueError("Not a call description")
    return value


def _expire(db: Session, care_profile_id: str, now: datetime) -> None:
    for call in db.execute(
        select(VideoCall).where(VideoCall.care_profile_id == care_profile_id, VideoCall.status == "ringing")
    ).scalars():
        if as_utc(call.created_at) + RING <= now:
            call.status = "ended"
            call.ended_at = now


def start(db: Session, actor_id: str, family_id: str, care_profile_id: str, offer: str, now: datetime) -> VideoCall:
    require(db, actor_id, family_id, "dashboard.view")
    profile = _profile_in(db, family_id, care_profile_id)
    offer = _sdp(offer)
    for call in db.execute(
        select(VideoCall).where(VideoCall.care_profile_id == profile.id, VideoCall.status.in_(("ringing", "live")))
    ).scalars():
        call.status = "ended"
        call.ended_at = now
    call = VideoCall(family_id=family_id, care_profile_id=profile.id, caller_user_id=actor_id, offer=offer,
                     created_at=now)
    db.add(call)
    db.commit()
    return call


def family_call(db: Session, actor_id: str, family_id: str, call_id: str, now: datetime) -> VideoCall:
    require(db, actor_id, family_id, "dashboard.view")
    call = db.get(VideoCall, call_id)
    if call is None or call.family_id != family_id:
        raise NotFound("Call not found")
    _expire(db, call.care_profile_id, now)
    db.commit()
    return call


def hang_up(call: VideoCall, db: Session, now: datetime) -> VideoCall:
    if call.status != "ended":
        call.status = "ended"
        call.ended_at = now
        db.commit()
    return call


def incoming(db: Session, ctx: ParentContext, now: datetime) -> dict | None:
    """The call ringing for this parent, if any, with whether to answer it without a tap."""
    _expire(db, ctx.profile.id, now)
    db.commit()
    call = db.execute(
        select(VideoCall).where(VideoCall.care_profile_id == ctx.profile.id, VideoCall.status == "ringing")
        .order_by(VideoCall.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if call is None:
        return None
    caller = db.get(User, call.caller_user_id)
    return {"id": call.id, "caller": caller.display_name if caller else "Family", "offer": call.offer,
            "auto_answer": privacy(db, ctx.profile.id).video_auto_answer}


def parent_call(db: Session, ctx: ParentContext, call_id: str) -> VideoCall:
    call = db.get(VideoCall, call_id)
    if call is None or call.care_profile_id != ctx.profile.id:
        raise NotFound("Call not found")
    return call


def answer(db: Session, ctx: ParentContext, call_id: str, sdp: str, now: datetime) -> VideoCall:
    call = parent_call(db, ctx, call_id)
    if call.status != "ringing":
        raise ValueError("This call has ended")
    call.answer = _sdp(sdp)
    call.status = "live"
    call.answered_at = now
    db.commit()
    return call
