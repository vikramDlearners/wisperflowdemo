"""Families, members and the caller's own access summary."""

from datetime import date as Date
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import _photo_response, _profile_out
from app.api.deps import CurrentUser, DbSession
from app.models.care_profile import CareProfile
from app.models.membership import FamilyMember
from app.models.parent_onboarding_profile import ParentOnboardingProfile
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
from app.services import care as care_svc
from app.services import families as svc
from app.services.emergencies import complete_emergency as complete_emergency_svc
from app.services.profile import MAX_PHOTO_BYTES, clear_profile_photo, set_profile_photo
from app.services.dashboard import build_family_dashboard
from app.services.permissions import get_membership, permission_codes_for
from app.services.permissions import require  # noqa: F401  (re-exported for readers of this module)

router = APIRouter(prefix="/api/families", tags=["families"])


def _member_out(row) -> MemberOut:
    membership, user, role = row
    return MemberOut(
        membership_id=membership.id,
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        role_id=role.id,
        role_name=role.name,
        relationship=membership.relationship,
    )


@router.get("", response_model=list[FamilyOut])
def my_families(db: Session = DbSession, user: User = CurrentUser) -> list[FamilyOut]:
    return [FamilyOut(id=f.id, name=f.name) for f in svc.list_families_for_user(db, user.id)]


@router.post("", response_model=FamilyOut, status_code=201)
def create_family(body: FamilyCreate, db: Session = DbSession, user: User = CurrentUser) -> FamilyOut:
    family = svc.create_family(db, user, body.name)
    return FamilyOut(id=family.id, name=family.name)


@router.get("/{family_id}", response_model=FamilyOut)
def get_family(family_id: str, db: Session = DbSession, user: User = CurrentUser) -> FamilyOut:
    family = svc.get_family(db, user.id, family_id)
    return FamilyOut(id=family.id, name=family.name)


@router.get("/{family_id}/me", response_model=MyAccess)
def my_access(family_id: str, db: Session = DbSession, user: User = CurrentUser) -> MyAccess:
    data = svc.membership_permissions(db, user.id, family_id)
    return MyAccess(**data)


@router.get("/{family_id}/members", response_model=list[MemberOut])
def list_members(family_id: str, db: Session = DbSession, user: User = CurrentUser) -> list[MemberOut]:
    return [_member_out(row) for row in svc.list_members(db, user.id, family_id)]


@router.post("/{family_id}/members", response_model=MemberOut, status_code=201)
def add_member(
    family_id: str, body: MemberCreate, db: Session = DbSession, user: User = CurrentUser
) -> MemberOut:
    membership = svc.add_member(
        db, user.id, family_id, body.email, body.role_id, body.display_name,
        relationship=body.relationship, care_profile_id=body.care_profile_id, phone=body.phone,
    )
    rows = svc.list_members(db, user.id, family_id)
    row = next(r for r in rows if r[0].id == membership.id)
    return _member_out(row)


@router.post("/{family_id}/members/{membership_id}/invite", status_code=201)
def invite_parent(
    family_id: str, membership_id: str, db: Session = DbSession, user: User = CurrentUser
) -> dict:
    # Sends a one-time sign-in link to the parent member (WhatsApp and text message when they have a mobile
    # number, else email) and returns where it went plus the link, so the family can also copy it.
    sent_to, link, channels = svc.create_parent_invite(db, user.id, family_id, membership_id)
    return {
        "email": sent_to if channels == ["email"] else None,
        "sent_to": sent_to,
        "channels": channels,
        "invite_link": link,
    }


@router.patch("/{family_id}/members/{membership_id}", response_model=MemberOut)
def change_role(
    family_id: str, membership_id: str, body: MemberRoleChange,
    db: Session = DbSession, user: User = CurrentUser,
) -> MemberOut:
    membership = svc.change_member_role(db, user.id, family_id, membership_id, body.role_id)
    rows = svc.list_members(db, user.id, family_id)
    row = next(r for r in rows if r[0].id == membership.id)
    return _member_out(row)


@router.delete("/{family_id}/members/{membership_id}", status_code=204)
def remove_member(
    family_id: str, membership_id: str, db: Session = DbSession, user: User = CurrentUser,
) -> Response:
    # Soft delete: sets the membership status to "removed" and keeps the row so care profile links stay valid.
    svc.remove_member(db, family_id, membership_id, user.id)
    return Response(status_code=204)


@router.get("/{family_id}/dashboard", response_model=DashboardResponse)
def family_dashboard(
    family_id: str,
    care_profile_id: str | None = None,
    date: str | None = None,
    db: Session = DbSession,
    user: User = CurrentUser,
) -> DashboardResponse:
    require(db, user.id, family_id, "dashboard.view")
    on_date = None
    if date is not None:
        try:
            on_date = Date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=422, detail="date must be an ISO date (YYYY-MM-DD)")
    return DashboardResponse(**build_family_dashboard(db, family_id, care_profile_id, on_date))


@router.post("/{family_id}/emergencies/{emergency_id}/complete", status_code=204)
def complete_emergency(
    family_id: str, emergency_id: str, db: Session = DbSession, user: User = CurrentUser,
) -> Response:
    complete_emergency_svc(db, user.id, family_id, emergency_id, datetime.now(timezone.utc))
    return Response(status_code=204)


def _parent_in_family(db: Session, family_id: str, care_profile_id: str) -> CareProfile:
    care_profile = db.scalar(
        select(CareProfile).where(CareProfile.id == care_profile_id, CareProfile.family_id == family_id)
    )
    if care_profile is None:
        raise HTTPException(status_code=404, detail="Parent not found in this family")
    return care_profile


def _onboarding_for_care_profile(db: Session, care_profile: CareProfile) -> ParentOnboardingProfile | None:
    if care_profile.linked_user_id is not None:
        return db.scalar(
            select(ParentOnboardingProfile).where(ParentOnboardingProfile.user_id == care_profile.linked_user_id)
        )
    return db.scalar(select(ParentOnboardingProfile).where(ParentOnboardingProfile.care_profile_id == care_profile.id))


@router.get("/{family_id}/parents/{care_profile_id}/profile", response_model=ProfileOut)
def get_parent_profile(
    family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser,
) -> ProfileOut:
    require(db, user.id, family_id, "dashboard.view")
    care_profile = _parent_in_family(db, family_id, care_profile_id)
    profile = _onboarding_for_care_profile(db, care_profile)
    if profile is None:
        # Nothing saved yet: return the same unsaved defaults get_profile does.
        return _profile_out(ParentOnboardingProfile())
    return _profile_out(profile)


@router.get("/{family_id}/parents/{care_profile_id}/profile/photo")
def get_parent_profile_photo(
    family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser,
) -> Response:
    require(db, user.id, family_id, "dashboard.view")
    care_profile = _parent_in_family(db, family_id, care_profile_id)
    return _photo_response(_onboarding_for_care_profile(db, care_profile))


@router.put("/{family_id}/parents/{care_profile_id}/profile/photo", response_model=ProfileOut)
def upload_parent_profile_photo(
    family_id: str, care_profile_id: str, file: UploadFile = File(...),
    db: Session = DbSession, user: User = CurrentUser,
) -> ProfileOut:
    require(db, user.id, family_id, "parent_profile.edit")
    care_profile = _parent_in_family(db, family_id, care_profile_id)
    profile = _onboarding_for_care_profile(db, care_profile)
    if profile is None:
        profile = ParentOnboardingProfile(user_id=care_profile.linked_user_id, care_profile_id=care_profile.id)
        db.add(profile)
    set_profile_photo(profile, file.file.read(MAX_PHOTO_BYTES + 1), file.content_type or "")
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return _profile_out(profile)


@router.delete("/{family_id}/parents/{care_profile_id}/profile/photo", status_code=204)
def delete_parent_profile_photo(
    family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser,
) -> Response:
    require(db, user.id, family_id, "parent_profile.edit")
    care_profile = _parent_in_family(db, family_id, care_profile_id)
    profile = _onboarding_for_care_profile(db, care_profile)
    if profile is not None:
        clear_profile_photo(profile)
        db.commit()
    return Response(status_code=204)


@router.patch("/{family_id}/parents/{care_profile_id}/profile", response_model=ProfileOut)
def update_parent_profile(
    family_id: str, care_profile_id: str, body: ProfileIn,
    db: Session = DbSession, user: User = CurrentUser,
) -> ProfileOut:
    require(db, user.id, family_id, "parent_profile.edit")
    care_profile = _parent_in_family(db, family_id, care_profile_id)
    profile = _onboarding_for_care_profile(db, care_profile)
    if profile is None:
        profile = ParentOnboardingProfile(user_id=care_profile.linked_user_id, care_profile_id=care_profile.id)
        db.add(profile)
    old_language = profile.preferred_language
    # Only touch the fields the client actually sent; the section name is not stored.
    for name in body.model_fields_set - {"section"}:
        setattr(profile, name, getattr(body, name))
    # Chatbot language is per user account, so it only syncs for a linked parent.
    # Saving the form with the same language keeps the one the parent picked in the chat.
    if "preferred_language" in body.model_fields_set and body.preferred_language != old_language and care_profile.linked_user_id is not None:
        care_svc.sync_chatbot_language(db, care_profile.linked_user_id, body.preferred_language)
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return _profile_out(profile)


@router.delete("/{family_id}/parents/{care_profile_id}/profile", status_code=204)
def delete_parent_profile(
    family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser,
) -> Response:
    # Removes only the onboarding profile row; the care profile, membership and other data are kept.
    require(db, user.id, family_id, "parent_profile.edit")
    care_profile = _parent_in_family(db, family_id, care_profile_id)
    if care_profile.linked_user_id is None:
        raise HTTPException(
            status_code=409,
            detail="This parent has no linked account yet, so their profile cannot be deleted.",
        )
    profile = db.scalar(
        select(ParentOnboardingProfile).where(ParentOnboardingProfile.user_id == care_profile.linked_user_id)
    )
    if profile is not None:
        db.delete(profile)
    db.commit()
    return Response(status_code=204)

