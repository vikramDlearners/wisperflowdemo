"""Parent invites: a family manager sends a parent a link; the parent accepts it to sign in."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.parent_invite import ParentInvite
from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session, create_otp, user_from_session_token
from app.services.adapters import messaging


class RecordingEmail:
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


@pytest.fixture()
def email(monkeypatch):
    fake = RecordingEmail()
    monkeypatch.setattr(messaging.settings, "smtp_host", None)
    monkeypatch.setattr(messaging, "_email_provider", fake)
    return fake


@pytest.fixture()
def family_setup(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    db_session.add(manager)
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    parent_role = db_session.execute(
        select(Role).where(Role.family_id == family.id, Role.name == "Parent")
    ).scalar_one()
    viewer_role = db_session.execute(
        select(Role).where(Role.family_id == family.id, Role.name == "Viewer")
    ).scalar_one()
    membership = families_svc.add_member(
        db_session, manager.id, family.id, "parent@example.com", parent_role.id, "Parent Doe"
    )
    caregiver = families_svc.add_member(
        db_session, manager.id, family.id, "viewer@example.com", viewer_role.id, "Viewer Doe"
    )
    return {
        "manager": manager,
        "family_id": family.id,
        "membership": membership,
        "caregiver_membership": caregiver,
    }


def _auth(db, user: User) -> dict:
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _invite_url(family_id: str, membership_id: str) -> str:
    return f"/api/families/{family_id}/members/{membership_id}/invite"


def _token_from(email: RecordingEmail) -> str:
    _, _, body = email.sent[-1]
    return body.split("token=", 1)[1].split()[0]


def test_invite_sends_email_with_link_and_stores_only_hash(client, db_session, family_setup, email):
    setup = family_setup
    response = client.post(
        _invite_url(setup["family_id"], setup["membership"].id), headers=_auth(db_session, setup["manager"])
    )
    assert response.status_code == 201
    assert response.json()["email"] == "parent@example.com"

    assert len(email.sent) == 1
    to, subject, body = email.sent[0]
    assert to == "parent@example.com"
    assert "/parent/accept-invite?token=" in body
    token = _token_from(email)

    row = db_session.execute(select(ParentInvite)).scalar_one()
    assert row.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert token not in row.token_hash
    assert row.used_at is None


def test_invite_rejects_non_parent_member(client, db_session, family_setup, email):
    setup = family_setup
    response = client.post(
        _invite_url(setup["family_id"], setup["caregiver_membership"].id),
        headers=_auth(db_session, setup["manager"]),
    )
    assert response.status_code == 400
    assert email.sent == []


def test_invite_requires_members_manage(client, db_session, family_setup, email):
    setup = family_setup
    response = client.post(
        _invite_url(setup["family_id"], setup["membership"].id),
        headers={"Authorization": f"Bearer {create_auth_session(db_session, setup['membership'].user_id)}"},
    )
    assert response.status_code == 403
    assert email.sent == []


def test_accept_invite_signs_parent_in_once(client, db_session, family_setup, email):
    setup = family_setup
    client.post(
        _invite_url(setup["family_id"], setup["membership"].id), headers=_auth(db_session, setup["manager"])
    )
    token = _token_from(email)

    response = client.post("/api/auth/accept-invite", json={"token": token})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == setup["membership"].user_id
    assert isinstance(body["session_token"], str) and body["session_token"]
    authed = user_from_session_token(db_session, body["session_token"])
    assert authed is not None
    assert authed.id == setup["membership"].user_id

    again = client.post("/api/auth/accept-invite", json={"token": token})
    assert again.status_code == 401


def test_accept_invite_rejects_expired_token(client, db_session, family_setup, email):
    setup = family_setup
    client.post(
        _invite_url(setup["family_id"], setup["membership"].id), headers=_auth(db_session, setup["manager"])
    )
    token = _token_from(email)
    row = db_session.execute(select(ParentInvite)).scalar_one()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    response = client.post("/api/auth/accept-invite", json={"token": token})
    assert response.status_code == 401


def test_otp_for_parent_does_not_cancel_invite(client, db_session, family_setup, email):
    setup = family_setup
    client.post(
        _invite_url(setup["family_id"], setup["membership"].id), headers=_auth(db_session, setup["manager"])
    )
    token = _token_from(email)
    parent = db_session.get(User, setup["membership"].user_id)

    create_otp(db_session, parent, "login")

    response = client.post("/api/auth/accept-invite", json={"token": token})
    assert response.status_code == 200
