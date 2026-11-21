"""Permission catalogue and access checks for family-scoped data.

Every family-scoped endpoint and file download must call ``require()`` before
touching data. Hiding a UI element is not access control: the frontend may
hide buttons for convenience, but the backend decides what a user may do.

Each member has exactly one role within a family (see README assumptions).
A role is a named set of permission codes stored in ``role_permissions``.
"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.membership import FamilyMember
from app.models.role import Role, RolePermission

PERMISSIONS: tuple[str, ...] = (
    "dashboard.view",
    "parent_profile.view",
    "parent_profile.edit",
    "medicines.view",
    "medicines.edit",
    "medicine_quantity.update",
    "reports.view",
    "reports.upload",
    "tasks.view",
    "tasks.create",
    "tasks.assign",
    "tasks.update_own",
    "appointments.view",
    "appointments.create",
    "appointments.update",
    "appointments.delete",
    "activity.view",
    "members.manage",
    "roles.manage",
    "notifications.configure",
    "voice.use_parent_mode",
)

_ALL = frozenset(PERMISSIONS)

DEFAULT_ROLES: dict[str, frozenset[str]] = {
    "Family manager": _ALL,
    "Caregiver": frozenset(
        {
            "dashboard.view",
            "parent_profile.view",
            "medicines.view",
            "medicine_quantity.update",
            "reports.view",
            "reports.upload",
            "tasks.view",
            "tasks.create",
            "tasks.assign",
            "tasks.update_own",
            "appointments.view",
            "appointments.create",
            "appointments.update",
            "appointments.delete",
            "activity.view",
            "notifications.configure",
        }
    ),
    "Viewer": frozenset(
        {
            "dashboard.view",
            "parent_profile.view",
            "medicines.view",
            "reports.view",
            "tasks.view",
            "appointments.view",
            "activity.view",
        }
    ),
    "Parent": frozenset({"parent_profile.view", "voice.use_parent_mode"}),
}


class PermissionDenied(Exception):
    """The user is a member but lacks the required permission."""


class NotAMember(Exception):
    """The user has no active membership in the family."""


def validate_permission_codes(codes: Iterable[str]) -> list[str]:
    """Return codes de-duplicated in input order; raise ValueError on unknown codes."""
    seen: list[str] = []
    for code in codes:
        if code not in _ALL:
            raise ValueError(f"Unknown permission code: {code}")
        if code not in seen:
            seen.append(code)
    return seen


def get_membership(db: Session, user_id: str, family_id: str) -> FamilyMember:
    """Return the active membership, or raise NotAMember."""
    membership = db.execute(
        select(FamilyMember).where(
            FamilyMember.user_id == user_id,
            FamilyMember.family_id == family_id,
            FamilyMember.status == "active",
        )
    ).scalar_one_or_none()
    if membership is None:
        raise NotAMember(f"User {user_id} is not an active member of family {family_id}")
    return membership


def permission_codes_for(db: Session, membership: FamilyMember) -> set[str]:
    """Return the set of permission codes granted by the member's role."""
    rows = db.execute(
        select(RolePermission.permission).where(RolePermission.role_id == membership.role_id)
    ).scalars()
    return set(rows)


def require(db: Session, user_id: str, family_id: str, permission: str) -> FamilyMember:
    """Check membership and permission; return the membership on success.

    Raises NotAMember if the user is not in the family, and PermissionDenied if
    the user's role does not grant ``permission``.
    """
    if permission not in _ALL:
        raise ValueError(f"Unknown permission code: {permission}")
    membership = get_membership(db, user_id, family_id)
    if permission not in permission_codes_for(db, membership):
        raise PermissionDenied(f"Missing permission: {permission}")
    return membership


def role_name_for(db: Session, membership: FamilyMember) -> str:
    role = db.get(Role, membership.role_id)
    return role.name if role else ""
