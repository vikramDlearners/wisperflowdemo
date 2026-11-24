"""'Remind parent': a family member nudges the parent about today's medicines that are due and not taken yet.

The reminder goes out on WhatsApp and as a text message, and into the CareCircle app when the parent has an
account. In Phase 1 the WhatsApp and SMS providers are logging stand-ins (see adapters/messaging.py) that
only record the message; real gateways plug in behind the same calls.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.user import User
from app.services import doses as doses_svc
from app.services.activity import log_activity
from app.services.adapters.messaging import get_sms_provider, get_whatsapp_provider
from app.services.care import _profile_in_family
from app.services.notifications import notify
from app.services.permissions import require


def _slot_label(slot: str) -> str:
    if len(slot) == 5 and slot[2] == ":":
        h, m = int(slot[:2]), slot[3:]
        return f"{h % 12 or 12}:{m} {'PM' if h >= 12 else 'AM'}"
    return {"morning": "morning", "noon": "afternoon", "night": "night"}.get(slot, "")


def _mask(phone: str) -> str:
    digits = [c for c in phone if c.isdigit()]
    return "•••• " + "".join(digits[-4:]) if len(digits) >= 4 else "••••"


def remind_parent(db: Session, actor_id: str, family_id: str, care_profile_id: str, now: datetime | None = None) -> dict:
    """Send the reminder. Raises ValueError when nothing is due right now (the caller shows it)."""
    require(db, actor_id, family_id, "medicines.view")
    profile = _profile_in_family(db, family_id, care_profile_id)
    now = now or datetime.now(timezone.utc)

    pending = [
        d for d in doses_svc.doses_today(db, profile, now)
        if d.status not in ("taken", "skipped") and (d.due_at is None or d.due_at <= now)
    ]
    if not pending:
        raise ValueError(f"{profile.display_name} has no medicines due right now, so there is nothing to remind about.")

    actor = db.get(User, actor_id)
    sender = actor.display_name if actor and actor.display_name else "your family"
    items = []
    for d in pending:
        when = _slot_label(d.slot)
        items.append(f"{d.name} ({when})" if when else d.name)
    names = ", ".join(items[:-1]) + (" and " if len(items) > 1 else "") + items[-1]
    message = (
        f"Hello {profile.greeting_name or profile.display_name}, a gentle reminder from {sender}: "
        f"please take {names}. Tell CareCircle once you have taken it. Take care! 💊"
    )

    parent = db.get(User, profile.linked_user_id) if profile.linked_user_id else None
    phone = parent.phone if parent is not None and parent.phone else None
    to = phone or f"{profile.display_name} (no phone on file)"
    get_whatsapp_provider().send(to, message)
    get_sms_provider().send(to, message)
    channels: list[str] = ["whatsapp", "sms"]
    sent_to = _mask(phone) if phone else None
    if parent is not None:
        notify(db, parent.id, "medicine.reminder", family_id,
               {"care_profile_id": profile.id, "message": message, "from": sender})
        channels.append("app")

    log_activity(db, family_id, actor_id, "medicine.reminder_sent", "care_profile", profile.id,
                 {"medicines": [d.name for d in pending], "channels": channels})
    db.commit()
    return {
        "sent_at": now,
        "channels": channels,
        "sent_to": sent_to,
        "medicines": [d.name for d in pending],
        "message": message,
    }
