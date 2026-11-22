"""Immediate family alerts from the parent check-in: in-app notifications and emails.

Functions stage notifications; the caller commits. The parent never alerts themselves.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.checkin import HealthCheckin
from app.models.membership import FamilyMember
from app.models.user import User
from app.services.adapters.messaging import get_email_provider
from app.services.doses import DueDose
from app.services.notifications import notify
from app.services.parent_context import ParentContext


def family_recipients(db: Session, family_id: str) -> list[User]:
    """All active members of the family, ordered by display name."""
    return list(
        db.execute(
            select(User)
            .join(FamilyMember, FamilyMember.user_id == User.id)
            .where(FamilyMember.family_id == family_id, FamilyMember.status == "active")
            .order_by(User.display_name, User.id)
        ).scalars()
    )


def other_members(db: Session, ctx: ParentContext) -> list[User]:
    """Active family members except the parent."""
    return [u for u in family_recipients(db, ctx.family_id) if u.id != ctx.user_id]


def _payload(ctx: ParentContext, checkin: HealthCheckin, text: str | None) -> dict:
    return {
        "checkin_id": checkin.id,
        "care_profile_id": ctx.profile.id,
        "parent_name": ctx.profile.display_name,
        "text": text,
    }


def _email(users: list[User], subject: str, body: str) -> None:
    provider = get_email_provider()
    for user in users:
        if user.email:
            provider.send(user.email, subject, body)


def notify_family_update(db: Session, ctx: ParentContext, checkin: HealthCheckin) -> None:
    for user in other_members(db, ctx):
        notify(db, user.id, "checkin.update", family_id=ctx.family_id,
               payload=_payload(ctx, checkin, checkin.health_text))


def notify_family_urgent(db: Session, ctx: ParentContext, checkin: HealthCheckin, text: str) -> None:
    users = other_members(db, ctx)
    for user in users:
        notify(db, user.id, "checkin.urgent", family_id=ctx.family_id, payload=_payload(ctx, checkin, text))
    name = ctx.profile.display_name
    _email(
        users,
        f"Needs attention now: {name}",
        f"{name} said during today's check-in:\n\n\"{text}\"\n\nPlease contact {name} as soon as you can.",
    )


def notify_family_finished(db: Session, ctx: ParentContext, medicine: DueDose) -> None:
    users = other_members(db, ctx)
    payload = {
        "care_profile_id": ctx.profile.id,
        "parent_name": ctx.profile.display_name,
        "medicine_id": medicine.medicine_id,
        "medicine_name": medicine.name,
    }
    for user in users:
        notify(db, user.id, "medicine.finished", family_id=ctx.family_id, payload=payload)
    name = ctx.profile.display_name
    _email(
        users,
        f"{name}'s medicine has run out: {medicine.name}",
        f"{name} said during today's check-in that {medicine.name} has run out. Please arrange a refill.",
    )
