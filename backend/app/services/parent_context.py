"""Find the care profile, family and language that belong to the signed-in parent."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.membership import FamilyMember
from app.models.user import User
from app.services.errors import NotFound
from app.services.languages import language_code
from app.services.permissions import require, role_name_for
from app.services.profile import is_child

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


def _parent_membership(db: Session, user: User) -> FamilyMember:
    memberships = db.execute(
        select(FamilyMember).where(
            FamilyMember.user_id == user.id, FamilyMember.status == "active"
        )
    ).scalars().all()
    found = [m for m in memberships if role_name_for(db, m) == PARENT_ROLE]
    if len(found) != 1:
        raise ParentNotLinked("Ask your family to link your profile")
    return found[0]


def _linked_profile(db: Session, user: User) -> CareProfile | None:
    return db.execute(
        select(CareProfile)
        .where(CareProfile.linked_user_id == user.id)
        .order_by(CareProfile.created_at, CareProfile.id)  # PostgreSQL has no implicit row order
    ).scalars().first()


def _own_context(db: Session, user: User) -> ParentContext:
    profile = _linked_profile(db, user)
    if profile is not None:
        require(db, user.id, profile.family_id, PARENT_PERMISSION)
        return _context(user, profile)

    membership = _parent_membership(db, user)
    family_id = membership.family_id
    own = db.execute(
        select(CareProfile).where(
            CareProfile.family_id == family_id,
            CareProfile.linked_member_id == membership.id,
            CareProfile.linked_user_id.is_(None),
        )
    ).scalars().first()
    if own is not None:
        require(db, user.id, family_id, PARENT_PERMISSION)
        own.linked_user_id = user.id
        db.commit()
        return _context(user, own)
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


def family_profiles(db: Session, user: User) -> list[CareProfile]:
    """The parents' profiles this account can use the chat as: its own family's, without the children."""
    own = _linked_profile(db, user)
    family_id = own.family_id if own is not None else _parent_membership(db, user).family_id
    require(db, user.id, family_id, PARENT_PERMISSION)
    profiles = db.execute(
        select(CareProfile)
        .where(CareProfile.family_id == family_id)
        .order_by(CareProfile.created_at, CareProfile.id)
    ).scalars().all()
    return [p for p in profiles if not is_child(db, p)]


def resolve_parent(db: Session, user: User, care_profile_id: str | None = None) -> ParentContext:
    """Whose conversation this is: the profile chosen on the chat page, else the account's own."""
    if care_profile_id is None:
        return _own_context(db, user)
    profile = next((p for p in family_profiles(db, user) if p.id == care_profile_id), None)
    if profile is None:
        raise NotFound("Profile not found")
    return _context(user, profile)
