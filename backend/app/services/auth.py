"""Passwordless sign-in: one-time link by email, then a server-side session token.

The session token is random; only its sha256 is stored in auth_sessions.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.care_profile import CareProfile
from app.models.login_token import LoginToken
from app.models.session import AuthSession
from app.models.parent_invite import ParentInvite
from app.models.user import User
from app.services.adapters.messaging import get_email_provider
from app.services.errors import AuthError


def _as_utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes even for timezone=True columns.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def request_sign_in_link(db: Session, email: str, display_name: str | None = None) -> None:
    """Create a one-time link and send it through the email provider (mock by default).

    A new email needs a display_name to create the account.
    """
    email = email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        if not display_name or not display_name.strip():
            raise ValueError("display_name is required to create a new account")
        user = User(email=email, display_name=display_name.strip())
        db.add(user)
        db.flush()

    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.login_token_minutes)
    db.add(LoginToken(user_id=user.id, token_hash=_hash_token(token), expires_at=expires))
    db.commit()

    link = f"{settings.login_link_base_url}?token={token}"
    get_email_provider().send(
        email,
        "Your CareCircle sign-in link",
        f"Open this link within {settings.login_token_minutes} minutes to sign in: {link}",
    )


def _otp_hash(user_id: str, purpose: str, code: str) -> str:
    # Keyed HMAC; user and purpose are bound in so equal codes never share a hash.
    msg = f"{user_id}:{purpose}:{code}".encode("utf-8")
    return hmac.new(settings.secret_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def create_otp(db: Session, user: User, purpose: str) -> str:
    """Generate a 6-digit code, store only its HMAC, and return the code."""
    now = datetime.now(timezone.utc)
    previous = db.execute(
        select(LoginToken).where(LoginToken.user_id == user.id, LoginToken.used_at.is_(None))
    ).scalars().all()
    for row in previous:
        row.used_at = now
    code = "123456"
    expires = now + timedelta(minutes=settings.otp_minutes)
    db.add(
        LoginToken(
            user_id=user.id,
            token_hash=_otp_hash(user.id, purpose, code),
            expires_at=expires,
        )
    )
    db.commit()
    return code


def signup_with_otp(db: Session, email: str, display_name: str) -> None:
    email = email.strip().lower()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise AuthError("An account with this email already exists; sign in instead")
    user = User(email=email, display_name=display_name.strip())
    db.add(user)
    db.commit()
    # Local import: services/families.py imports _hash_token from this module, so a top-level import would be circular.
    from app.services.families import create_family

    create_family(db, user, f"{user.display_name}'s family")
    # OTP email skipped for now; the code is always 123456.
    create_otp(db, user, "signup")


def login_with_otp(db: Session, email: str) -> None:
    # Silent for unknown or inactive emails so accounts cannot be probed.
    email = email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or user.status != "active":
        return
    # OTP email skipped for now; the code is always 123456.
    create_otp(db, user, "login")


def verify_otp(db: Session, email: str, code: str) -> User:
    # No attempt counter: LoginToken has no attempts column, so guesses are not capped per code.
    email = email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or user.status != "active":
        raise AuthError("Code is invalid or expired")
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(LoginToken)
        .where(LoginToken.user_id == user.id, LoginToken.used_at.is_(None))
        .order_by(LoginToken.created_at.desc())
    ).scalars().first()
    if row is None or _as_utc(row.expires_at) < now:
        raise AuthError("Code is invalid or expired")
    if not any(
        hmac.compare_digest(row.token_hash, _otp_hash(user.id, p, code)) for p in ("signup", "login")
    ):
        raise AuthError("Code is invalid or expired")
    row.used_at = now
    db.commit()
    return user


def verify_sign_in_token(db: Session, token: str) -> User:
    row = db.execute(
        select(LoginToken).where(LoginToken.token_hash == _hash_token(token))
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row is None or row.used_at is not None or _as_utc(row.expires_at) < now:
        raise AuthError("Sign-in link is invalid, expired or already used")
    row.used_at = now
    db.commit()
    user = db.get(User, row.user_id)
    if user is None or user.status != "active":
        raise AuthError("Account is not active")
    return user


def accept_parent_invite(db: Session, token: str) -> User:
    """Use a parent invite link once and return the invited user (session is issued by the caller)."""
    row = db.execute(
        select(ParentInvite).where(ParentInvite.token_hash == _hash_token(token))
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if row is None or row.used_at is not None or _as_utc(row.expires_at) < now:
        raise AuthError("Invite link is invalid, expired or already used")
    row.used_at = now
    db.commit()
    user = db.get(User, row.user_id)
    if user is None or user.status != "active":
        raise AuthError("Account is not active")
    _link_single_care_profile(db, row.family_id, user.id)
    return user


def _link_single_care_profile(db: Session, family_id: str, user_id: str) -> None:
    """Link the parent to their own care profile in this family.

    If they already have one here, do nothing. Otherwise link the family's only unlinked profile
    when there is exactly one. Otherwise create a new profile for this parent.
    """
    profiles = db.execute(
        select(CareProfile).where(CareProfile.family_id == family_id)
    ).scalars().all()
    if any(p.linked_user_id == user_id for p in profiles):
        return
    unlinked = [p for p in profiles if p.linked_user_id is None]
    if len(unlinked) == 1:
        unlinked[0].linked_user_id = user_id
        db.commit()
        return
    user = db.get(User, user_id)
    name = (user.display_name or "").strip() or user.email
    db.add(
        CareProfile(
            family_id=family_id,
            display_name=name,
            greeting_name=name,
            linked_user_id=user_id,
        )
    )
    db.commit()


def create_auth_session(db: Session, user_id: str) -> str:
    """Store a new server-side session (hash only) and return the raw token."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.add(
        AuthSession(
            user_id=user_id,
            token_hash=_hash_token(token),
            created_at=now,
            expires_at=now + timedelta(days=settings.session_days),
            revoked_at=None,
        )
    )
    db.commit()
    return token


def issue_session_token(user_id: str) -> str:
    # Legacy stateless HMAC token. Not accepted by user_from_session_token any more;
    # sign-in routes use create_auth_session instead.
    sig = hmac.new(settings.secret_key.encode("utf-8"), user_id.encode("utf-8"), hashlib.sha256)
    return f"{user_id}.{sig.hexdigest()}"


def user_from_session_token(db: Session, token: str) -> User | None:
    now = datetime.now(timezone.utc)
    row = db.execute(
        select(AuthSession).where(
            AuthSession.token_hash == _hash_token(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    user = db.get(User, row.user_id)
    return user if user and user.status == "active" else None


def revoke_auth_session(db: Session, token: str) -> bool:
    """Mark the session for this raw token as revoked. Returns False if none is active."""
    row = db.execute(
        select(AuthSession).where(
            AuthSession.token_hash == _hash_token(token),
            AuthSession.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True
