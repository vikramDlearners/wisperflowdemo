"""Sign-in by one-time email link, then a session token."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.models.user import User
from app.schemas import (
    LoginRequest,
    ParentInviteAccept,
    ProfileIn,
    ProfileOut,
    RoleIn,
    SessionOut,
    SignInRequest,
    SignUpRequest,
    UserOut,
    VerifyOtpRequest,
    VerifyRequest,
)
from app.services.auth import (
    accept_parent_invite,
    create_auth_session,
    login_with_otp,
    request_sign_in_link,
    revoke_auth_session,
    signup_with_otp,
    verify_otp,
    verify_sign_in_token,
)
from app.services import care as care_svc
from app.services.profile import MAX_PHOTO_BYTES, age_from, clear_profile_photo, completion, set_profile_photo

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        other_role=user.other_role,
    )


@router.post("/request-link", status_code=202)
def request_link(body: SignInRequest, db: Session = DbSession) -> dict:
    # Same response whether or not the account exists, so emails cannot be probed.
    request_sign_in_link(db, body.email, body.display_name)
    return {"detail": "If this email can sign in, a link has been sent."}


@router.post("/verify", response_model=SessionOut)
def verify(body: VerifyRequest, db: Session = DbSession) -> SessionOut:
    user = verify_sign_in_token(db, body.token)
    return SessionOut(
        session_token=create_auth_session(db, user.id),
        user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
    )


@router.post("/accept-invite", response_model=SessionOut)
def accept_invite(body: ParentInviteAccept, db: Session = DbSession) -> SessionOut:
    user = accept_parent_invite(db, body.token)
    return SessionOut(
        session_token=create_auth_session(db, user.id),
        user=UserOut(id=user.id, email=user.email, display_name=user.display_name),
    )


@router.post("/signup", status_code=202)
def signup(body: SignUpRequest, db: Session = DbSession) -> dict:
    signup_with_otp(db, body.email, body.display_name)
    return {"detail": "We sent a code to your email."}


@router.post("/login", status_code=202)
def login(body: LoginRequest, db: Session = DbSession) -> dict:
    # Same response whether or not the account exists, so emails cannot be probed.
    login_with_otp(db, body.email)
    return {"detail": "We sent a code to your email."}


@router.post("/verify-otp", response_model=SessionOut)
def verify_code(body: VerifyOtpRequest, db: Session = DbSession) -> SessionOut:
    user = verify_otp(db, body.email, body.code)
    return SessionOut(
        session_token=create_auth_session(db, user.id),
        user=_user_out(user),
    )


@router.post("/logout", status_code=204)
def logout(authorization: str | None = Header(default=None), db: Session = DbSession) -> Response:
    # Same bearer parsing and 401 messages as current_user in deps.py.
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    if not revoke_auth_session(db, authorization[7:].strip()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is invalid")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: User = CurrentUser) -> UserOut:
    return _user_out(user)


@router.patch("/me/role", response_model=UserOut)
def set_role(body: RoleIn, user: User = CurrentUser, db: Session = DbSession) -> UserOut:
    user.role = body.role
    user.other_role = body.other_role if body.role == "others" else None
    db.commit()
    db.refresh(user)
    return _user_out(user)


_PROFILE_FIELDS = (
    "parent_full_name",
    "preferred_name",
    "relationship",
    "date_of_birth",
    "approximate_age",
    "profile_picture_url",
    "preferred_language",
    "parent_mobile",
    "known_health_conditions",
    "allergies",
    "primary_doctor_name",
    "doctor_contact_number",
    "preferred_hospital",
    "care_instructions",
    "deficiencies",
    "notes",
    "caregiver_name",
    "caregiver_relationship",
    "caregiver_phone",
    "caregiver_email",
)


def _profile_out(profile: ParentOnboardingProfile) -> ProfileOut:
    # Works for an unsaved profile too: unset columns read as None.
    values = {name: getattr(profile, name) for name in _PROFILE_FIELDS}
    return ProfileOut(
        **values,
        has_photo=profile.profile_photo_content_type is not None,
        age=age_from(profile),
        updated_at=profile.updated_at,
        completion=completion(profile),
    )


@router.get("/me/profile", response_model=ProfileOut)
def get_profile(user: User = CurrentUser, db: Session = DbSession) -> ProfileOut:
    profile = db.scalar(
        select(ParentOnboardingProfile).where(ParentOnboardingProfile.user_id == user.id)
    )
    if profile is None:
        profile = ParentOnboardingProfile(user_id=user.id)
    return _profile_out(profile)


def _own_profile(db: Session, user: User, create: bool = False) -> ParentOnboardingProfile | None:
    profile = db.scalar(select(ParentOnboardingProfile).where(ParentOnboardingProfile.user_id == user.id))
    if profile is None and create:
        profile = ParentOnboardingProfile(user_id=user.id)
        db.add(profile)
    return profile


def _photo_response(profile: ParentOnboardingProfile | None) -> Response:
    if profile is None or profile.profile_photo_content_type is None or profile.profile_photo_data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo yet")
    return Response(content=profile.profile_photo_data, media_type=profile.profile_photo_content_type,
                    headers={"Cache-Control": "private, no-cache"})


@router.get("/me/profile/photo")
def get_profile_photo(user: User = CurrentUser, db: Session = DbSession) -> Response:
    return _photo_response(_own_profile(db, user))


@router.put("/me/profile/photo", response_model=ProfileOut)
def upload_profile_photo(
    file: UploadFile = File(...), user: User = CurrentUser, db: Session = DbSession
) -> ProfileOut:
    profile = _own_profile(db, user, create=True)
    # Read one byte past the limit so an oversized upload is refused without loading it all.
    set_profile_photo(profile, file.file.read(MAX_PHOTO_BYTES + 1), file.content_type or "")
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return _profile_out(profile)


@router.delete("/me/profile/photo", status_code=204)
def delete_profile_photo(user: User = CurrentUser, db: Session = DbSession) -> Response:
    profile = _own_profile(db, user)
    if profile is not None:
        clear_profile_photo(profile)
        db.commit()
    return Response(status_code=204)


@router.patch("/me/profile", response_model=ProfileOut)
def update_profile(
    body: ProfileIn, user: User = CurrentUser, db: Session = DbSession
) -> ProfileOut:
    profile = db.scalar(
        select(ParentOnboardingProfile).where(ParentOnboardingProfile.user_id == user.id)
    )
    if profile is None:
        profile = ParentOnboardingProfile(user_id=user.id)
        db.add(profile)
    # Only touch the fields the client actually sent; the section name is not stored.
    for name in body.model_fields_set - {"section"}:
        setattr(profile, name, getattr(body, name))
    if "preferred_language" in body.model_fields_set:
        # A parent editing their own profile changes their chatbot's language too.
        care_svc.sync_chatbot_language(db, user.id, body.preferred_language)
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return _profile_out(profile)
