"""Two spoken questions the check-in answers from the database: "When is my doctor visit?" and "Call my son".

A call request names a relationship (son, daughter) or a family member's first name. The answer puts that
member's number on the chat's call button; nothing is dialled for the parent.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.membership import FamilyMember
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.models.user import User
from app.services.doses import today_for
from app.services.parent_context import ParentContext

UPCOMING = ("scheduled", "rescheduled")

_VISIT_WORDS = re.compile(r"\b(?:doctor|doctor's|appointment|appointments|visit|check-?up|clinic|hospital)\b")
_VISIT_CUES = re.compile(r"\b(?:when|what time|which day|next|do i have|is there|have i got)\b")
_VISIT_NON_LATIN = (
    ("டாக்டர்", "மருத்துவர்", "அப்பாயின்ட்மென்ட்"),
    ("डॉक्टर", "अपॉइंटमेंट", "डाक्टर"),
    ("డాక్టర్", "అపాయింట్‌మెంట్"),
    ("ഡോക്ടർ", "അപ്പോയിന്റ്മെന്റ്"),
    ("ವೈದ್ಯ", "ಡಾಕ್ಟರ್", "ಅಪಾಯಿಂಟ್‌ಮೆಂಟ್"),
)
_WHEN_NON_LATIN = ("எப்போ", "எப்ப", "कब", "ఎప్పుడు", "എപ്പോൾ", "ಯಾವಾಗ")

_CALL = re.compile(r"\b(?:call|phone|ring|dial)\s+(?:to\s+)?(?:my\s+)?([a-z]+)")
_CALL_NON_LATIN = ("போன் பண்ண", "கால் பண்ண", "फोन कर", "फ़ोन कर", "कॉल कर", "ఫోన్ చే", "కాల్ చే",
                   "ഫോൺ ചെയ്", "വിളിക്ക", "ಫೋನ್ ಮಾಡ", "ಕರೆ ಮಾಡ")
_RELATION_WORDS = {
    "son": "son", "daughter": "daughter", "beta": "son", "beti": "daughter",
    "மகன்": "son", "மகள்": "daughter", "बेटा": "son", "बेटे": "son", "बेटी": "daughter",
    "కొడుకు": "son", "కూతురు": "daughter", "മകൻ": "son", "മകൾ": "daughter", "ಮಗ": "son", "ಮಗಳು": "daughter",
}
_NOT_A_NAME = frozenset({"me", "you", "back", "later", "him", "her", "them", "the", "a", "family", "someone"})


def _plain(text: str) -> str:
    return " ".join((text or "").lower().replace("’", "'").split())


def is_visit_question(text: str) -> bool:
    t = _plain(text)
    if _VISIT_WORDS.search(t) and _VISIT_CUES.search(t):
        return True
    return any(w in t for w in _WHEN_NON_LATIN) and any(w in t for group in _VISIT_NON_LATIN for w in group)


def next_visit(db: Session, ctx: ParentContext, now: datetime) -> Appointment | None:
    return db.execute(
        select(Appointment).where(
            Appointment.care_profile_id == ctx.profile.id, Appointment.status.in_(UPCOMING),
            Appointment.scheduled_date >= today_for(ctx.profile, now),
        ).order_by(Appointment.scheduled_date, Appointment.start_time).limit(1)
    ).scalar_one_or_none()


@dataclass
class CallAsk:
    """Who the parent asked to call. `name` is None when no member matched; `number` when none is on file."""

    name: str | None
    number: str | None


def _asked_for(text: str) -> tuple[str | None, str | None] | None:
    """(relationship, name word) the parent asked to call, or None when the text is not a call request."""
    t = _plain(text)
    rel = next((r for w, r in _RELATION_WORDS.items() if w in t.split() or (not w.isascii() and w in t)), None)
    m = _CALL.search(t)
    if m:
        word = m.group(1)
        if word in _RELATION_WORDS:
            return _RELATION_WORDS[word], None
        return rel, None if word in _NOT_A_NAME else word
    if any(w in t for w in _CALL_NON_LATIN):
        return rel, None
    return None


def _phone(db: Session, user: User) -> str | None:
    if user.phone and user.phone.strip():
        return user.phone.strip()
    p = db.execute(
        select(ParentOnboardingProfile).where(ParentOnboardingProfile.user_id == user.id)
    ).scalars().first()
    return p.caregiver_phone.strip() if p and p.caregiver_phone and p.caregiver_phone.strip() else None


def call_ask(db: Session, ctx: ParentContext, text: str) -> CallAsk | None:
    asked = _asked_for(text)
    if asked is None:
        return None
    rel, name = asked
    rows = db.execute(
        select(FamilyMember, User).join(User, User.id == FamilyMember.user_id).where(
            FamilyMember.family_id == ctx.family_id, FamilyMember.status == "active", User.id != ctx.user_id,
        ).order_by(FamilyMember.created_at, FamilyMember.id)
    ).all()
    match = None
    if name:
        match = next((u for _, u in rows if (u.display_name or "").lower().split()[:1] == [name]), None)
    if match is None and rel:
        match = next((u for fm, u in rows if (fm.relationship or "").lower() == rel), None)
    if match is None:
        # "I'll call you later" or "my phone is broken" name no one: not a call request.
        return CallAsk(None, None) if rel else None
    return CallAsk(match.display_name, _phone(db, match))
