"""Families, members and roles. Every action is permission-checked and logged."""

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.care_profile import CareProfile
from app.models.family import Family
from app.models.membership import FamilyMember
from app.models.parent_invite import ParentInvite
from app.models.role import Role, RolePermission
from app.models.user import User
from app.services.activity import log_activity
from app.services.adapters.messaging import get_email_provider
from app.services.auth import _hash_token
from app.services.errors import NotFound

"""Families, members and the caller's own access summary."""

from datetime import date as Date
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.api.auth import _profile_out
from app.api.deps import CurrentUser, DbSession
from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.models.checkin import ChatMessage, HealthCheckin
from app.models.dose import MedicineDose
from app.models.medicine import Medicine
from app.models.membership import FamilyMember
from app.models.parent_invite import ParentInvite
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.models.prescription_scan import MedicineReminder, PrescriptionScan
from app.models.task import Task
from app.models.user import User
from app.schemas import (
    DashboardResponse,
    FamilyCreate,
    FamilyOut,
    MemberCreate,
    MemberOut,
    MemberRoleChange,
    MyAccess,
    ProfileIn,
    ProfileOut,
)
from app.services import families as svc
from app.services.dashboard import build_family_dashboard
from app.services.profile import get_care_profile_onboarding
from app.services.permissions import get_membership, permission_codes_for
from app.services.permissions import require  # noqa: F401  (re-exported for readers of this module)

from app.services.permissions import (
    DEFAULT_ROLES,
    PermissionDenied,
    permission_codes_for,
    require,
    get_membership,
    validate_permission_codes,
)



def create_family(db: Session, creator: User, name: str) -> Family:
    """Create a family with the four default roles; the creator becomes Family manager."""
    family = Family(name=name.strip(), created_by_user_id=creator.id)
    db.add(family)
    db.flush()

    manager_role_id = None
    for role_name, codes in DEFAULT_ROLES.items():
        role = Role(family_id=family.id, name=role_name, is_system=True)
        db.add(role)
        db.flush()
        for code in sorted(codes):
            db.add(RolePermission(role_id=role.id, permission=code))
        if role_name == "Family manager":
            manager_role_id = role.id

    db.add(FamilyMember(family_id=family.id, user_id=creator.id, role_id=manager_role_id))
    log_activity(db, family.id, creator.id, "family.created", "family", family.id)
    db.commit()
    return family


def list_families_for_user(db: Session, user_id: str) -> list[Family]:
    stmt = (
        select(Family)
        .join(FamilyMember, FamilyMember.family_id == Family.id)
        .where(FamilyMember.user_id == user_id, FamilyMember.status == "active")
        .order_by(Family.created_at)
    )
    return list(db.execute(stmt).scalars())


def get_family(db: Session, actor_id: str, family_id: str) -> Family:
    require(db, actor_id, family_id, "dashboard.view")
    family = db.get(Family, family_id)
    if family is None:
        raise NotFound("Family not found")
    return family


def list_members(db: Session, actor_id: str, family_id: str) -> list[tuple[FamilyMember, User, Role]]:
    require(db, actor_id, family_id, "dashboard.view")
    stmt = (
        select(FamilyMember, User, Role)
        .join(User, User.id == FamilyMember.user_id)
        .join(Role, Role.id == FamilyMember.role_id)
        .where(
            FamilyMember.family_id == family_id,
            FamilyMember.status == "active",
            FamilyMember.status != "removed",
        )
        .order_by(User.display_name)
    )
    return [tuple(row) for row in db.execute(stmt).all()]


def _role_in_family(db: Session, family_id: str, role_id: str) -> Role:
    role = db.get(Role, role_id)
    if role is None or role.family_id != family_id:
        raise NotFound("Role not found in this family")
    return role


def list_roles(db: Session, actor_id: str, family_id: str) -> list[dict]:
    require(db, actor_id, family_id, "members.manage")
    roles = db.execute(
        select(Role).where(Role.family_id == family_id).order_by(Role.name)
    ).scalars()
    result = []
    for role in roles:
        codes = sorted(
            db.execute(
                select(RolePermission.permission).where(RolePermission.role_id == role.id)
            ).scalars()
        )
        result.append({"id": role.id, "name": role.name, "is_system": role.is_system, "permissions": codes})
    return result


def create_custom_role(
    db: Session, actor_id: str, family_id: str, name: str, codes: list[str]
) -> Role:
    require(db, actor_id, family_id, "roles.manage")
    clean = validate_permission_codes(codes)
    role = Role(family_id=family_id, name=name.strip(), is_system=False)
    db.add(role)
    db.flush()
    for code in clean:
        db.add(RolePermission(role_id=role.id, permission=code))
    log_activity(db, family_id, actor_id, "role.created", "role", role.id, {"name": role.name})
    db.commit()
    return role


def update_role_permissions(
    db: Session, actor_id: str, family_id: str, role_id: str, codes: list[str]
) -> Role:
    require(db, actor_id, family_id, "roles.manage")
    role = _role_in_family(db, family_id, role_id)
    if role.is_system:
        raise ValueError("System roles cannot be edited; create a custom role instead")
    clean = validate_permission_codes(codes)
    for old in db.execute(
        select(RolePermission).where(RolePermission.role_id == role.id)
    ).scalars():
        db.delete(old)
    db.flush()
    for code in clean:
        db.add(RolePermission(role_id=role.id, permission=code))
    log_activity(
        db, family_id, actor_id, "role.permissions_updated", "role", role.id, {"permissions": clean}
    )
    db.commit()
    return role


def add_member(
    db: Session,
    actor_id: str,
    family_id: str,
    email: str,
    role_id: str,
    display_name: str | None = None,
    relationship: str | None = None,
    care_profile_id: str | None = None,
) -> FamilyMember:
    """Add a person to the family. Creates the user record if the email is new.

    A mother or father member also gets a linked Mother/Father care profile. With care_profile_id
    the member is linked to that existing care profile instead (no duplicate parent): it must be
    in this family and not yet linked to another member or account.
    """
    require(db, actor_id, family_id, "members.manage")
    role = _role_in_family(db, family_id, role_id)
    existing_profile = None
    if care_profile_id is not None:
        existing_profile = db.get(CareProfile, care_profile_id)
        if existing_profile is None or existing_profile.family_id != family_id:
            raise ValueError("Care profile not found in this family")
        if existing_profile.linked_member_id is not None:
            raise ValueError("This care profile already belongs to another member")
    if relationship is not None:
        relationship = relationship.strip().lower() or None
        if relationship is not None and relationship not in {
            "mother", "father", "grandmother", "grandfather", "son", "daughter", "other",
        }:
            raise ValueError("Unknown relationship")
    email = email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        if not display_name or not display_name.strip():
            raise ValueError("display_name is required for a new person")
        user = User(email=email, display_name=display_name.strip())
        db.add(user)
        db.flush()
    existing = db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id, FamilyMember.user_id == user.id
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("This person is already a member; one role per member per family")
    membership = FamilyMember(
        family_id=family_id, user_id=user.id, role_id=role.id, relationship=relationship
    )
    db.add(membership)
    db.flush()
    if existing_profile is not None:
        existing_profile.linked_member_id = membership.id  # the account is linked when the invite is accepted
    elif relationship in ("mother", "father") or role.name.strip().lower() == "parent":
        db.add(
            CareProfile(
                family_id=family_id,
                display_name=user.display_name,
                greeting_name=user.display_name,
                linked_member_id=membership.id,
            )
        )
    log_activity(
        db, family_id, actor_id, "member.added", "member", membership.id, {"role": role.name}
    )
    db.commit()
    return membership


def change_member_role(
    db: Session, actor_id: str, family_id: str, membership_id: str, role_id: str
) -> FamilyMember:
    require(db, actor_id, family_id, "members.manage")
    role = _role_in_family(db, family_id, role_id)
    membership = db.get(FamilyMember, membership_id)
    if membership is None or membership.family_id != family_id:
        raise NotFound("Member not found")
    membership.role_id = role.id
    log_activity(
        db, family_id, actor_id, "member.role_changed", "member", membership.id, {"role": role.name}
    )
    db.commit()
    return membership


def remove_member(
    db: Session, family_id: str, membership_id: str, acting_user_id: str
) -> FamilyMember:
    """Soft-delete a family member (status='removed'). The family creator and the caller cannot be removed."""
    require(db, acting_user_id, family_id, "members.manage")
    membership = db.get(FamilyMember, membership_id)
    if membership is None or membership.family_id != family_id:
        raise NotFound("Member not found")
    family = db.get(Family, family_id)
    if family is not None and membership.user_id == family.created_by_user_id:
        raise ValueError("The family creator cannot be removed")
    if membership.user_id == acting_user_id:
        raise ValueError("You cannot remove yourself")
    membership.status = "removed"
    log_activity(db, family_id, acting_user_id, "member.removed", "member", membership.id)
    db.commit()
    return membership


def membership_permissions(db: Session, actor_id: str, family_id: str) -> dict:
    """Return the caller's role name and permission codes (used by the UI to hide controls)."""
    membership = get_membership(db, actor_id, family_id)
    role = db.get(Role, membership.role_id)
    return {"role": role.name if role else "", "permissions": sorted(permission_codes_for(db, membership))}


def create_parent_invite(db: Session, actor_id: str, family_id: str, membership_id: str) -> tuple[str, str]:
    """Create a one-time sign-in link for a parent member and email it to them. Returns (email address, sign-in link)."""
    require(db, actor_id, family_id, "members.manage")
    membership = db.get(FamilyMember, membership_id)
    if membership is None or membership.family_id != family_id:
        raise NotFound("Member not found")
    role = db.get(Role, membership.role_id)
    if role is None or role.name != "Parent":
        raise ValueError("Sign-in links can only be sent to members with the Parent role")
    user = db.get(User, membership.user_id)
    if user is None or not user.email:
        raise NotFound("Member has no email address to send the invite to")

    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.parent_invite_hours)
    db.add(
        ParentInvite(
            family_id=family_id,
            membership_id=membership.id,
            user_id=user.id,
            email=user.email,
            token_hash=_hash_token(token),
            expires_at=expires,
            created_by_user_id=actor_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    log_activity(db, family_id, actor_id, "parent_invite.created", "member", membership.id)
    db.commit()

    link = f"{settings.parent_invite_base_url}?token={token}"
    get_email_provider().send(
        user.email,
        "You're invited to CareCircle",
        f"Open this link within {settings.parent_invite_hours} hours to create your sign-in: {link}",
    )
    return user.email, link


__all__ = [
    "create_parent_invite",
    "PermissionDenied",
    "create_family",
    "list_families_for_user",
    "get_family",
    "list_members",
    "list_roles",
    "create_custom_role",
    "update_role_permissions",
    "add_member",
    "change_member_role",
    "remove_member",
    "membership_permissions",
]
