"""Find the care profile, family and language that belong to the signed-in parent."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.membership import FamilyMember
from app.models.user import User
from app.services.languages import language_code
from app.services.permissions import require, role_name_for

PARENT_ROLE = "Parent"
PARENT_PERMISSION = "voice.use_parent_mode"


class ParentNotLinked(Exception):
    """The signed-in user is not linked to a care profile yet."""


@dataclass
class ParentContext:
    user_id: str
    family_id: str
    profile: CareProfile
    language: str
    greeting_name: str


def _context(user: User, profile: CareProfile) -> ParentContext:
    return ParentContext(
        user_id=user.id,
        family_id=profile.family_id,
        profile=profile,
        language=language_code(profile.preferred_language),
        greeting_name=profile.greeting_name or profile.display_name,
    )


def resolve_parent(db: Session, user: User) -> ParentContext:
    profile = db.execute(
        select(CareProfile)
        .where(CareProfile.linked_user_id == user.id)
        .order_by(CareProfile.created_at, CareProfile.id)  # PostgreSQL has no implicit row order
    ).scalars().first()
    if profile is not None:
        require(db, user.id, profile.family_id, PARENT_PERMISSION)
        return _context(user, profile)

    memberships = db.execute(
        select(FamilyMember).where(
            FamilyMember.user_id == user.id, FamilyMember.status == "active"
        )
    ).scalars().all()
    parent_families = [m.family_id for m in memberships if role_name_for(db, m) == PARENT_ROLE]
    if len(parent_families) != 1:
        raise ParentNotLinked("Ask your family to link your profile")
    family_id = parent_families[0]
    profiles = db.execute(
        select(CareProfile).where(CareProfile.family_id == family_id)
    ).scalars().all()
    if len(profiles) != 1:
        raise ParentNotLinked("Ask your family to link your profile")
    require(db, user.id, family_id, PARENT_PERMISSION)
    profile = profiles[0]
    if profile.linked_user_id is not None:
        raise ParentNotLinked("Ask your family to link your profile")
    profile.linked_user_id = user.id
    db.commit()
    return _context(user, profile)
