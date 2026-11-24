"""A parent can be added by mobile number only; their sign-in link goes out on WhatsApp and as a text message."""

import pytest

from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
from app.services.adapters import messaging
from app.services.auth import create_auth_session


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    db_session.add(manager)
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    parent_role = db_session.query(Role).filter_by(family_id=family.id, name="Parent").one()
    messaging._sms_provider.outbox.clear()
    messaging._whatsapp_provider.outbox.clear()
    headers = {"Authorization": f"Bearer {create_auth_session(db_session, manager.id)}"}
    return {"family": family, "role": parent_role, "headers": headers}


def _add(client, setup, **body):
    return client.post(
        f"/api/families/{setup['family'].id}/members",
        json={"display_name": "Lakshmi", "role_id": setup["role"].id, **body},
        headers=setup["headers"],
    )


def test_add_parent_by_mobile_and_send_link(client, db_session, setup):
    r = _add(client, setup, phone="+91 98765-43210")
    assert r.status_code == 201, r.text
    user = db_session.query(User).filter_by(display_name="Lakshmi").one()
    assert user.email is None
    assert user.phone == "+919876543210"

    invite = client.post(
        f"/api/families/{setup['family'].id}/members/{r.json()['membership_id']}/invite", headers=setup["headers"]
    )
    assert invite.status_code == 201, invite.text
    body = invite.json()
    assert body["channels"] == ["whatsapp", "sms"]
    assert body["sent_to"] == "+919876543210"
    assert body["invite_link"].startswith("http")
    assert [m.to for m in messaging._whatsapp_provider.outbox] == ["+919876543210"]
    assert body["invite_link"] in messaging._sms_provider.outbox[0].body

    # The link signs the parent in.
    token = body["invite_link"].split("token=")[1]
    accept = client.post("/api/auth/accept-invite", json={"token": token})
    assert accept.status_code in (200, 201), accept.text


@pytest.mark.parametrize("phone", ["12345", "call me", ""])
def test_bad_or_missing_mobile_is_refused(client, setup, phone):
    r = _add(client, setup, phone=phone)
    assert r.status_code in (400, 422)


def test_email_still_works(client, setup):
    assert _add(client, setup, email="lakshmi@example.com").status_code == 201
