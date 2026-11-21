"""Appointments: create, list (upcoming/past split), get, update (including cancel), delete; viewers and outsiders are denied writes."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.care_profile import CareProfile
from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session


@pytest.fixture()
def appointment_setup(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    db_session.add(manager)
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    viewer_role = db_session.execute(
        select(Role).where(Role.family_id == family.id, Role.name == "Viewer")
    ).scalar_one()
    viewer_member = families_svc.add_member(
        db_session, manager.id, family.id, "viewer@example.com", viewer_role.id, "Viewer Doe"
    )
    outsider = User(email="outsider@example.com", display_name="Outsider")
    db_session.add(outsider)
    db_session.commit()
    profile = CareProfile(
        family_id=family.id,
        display_name="Amma",
        greeting_name="Amma",
    )
    db_session.add(profile)
    db_session.commit()
    return {
        "manager": manager,
        "viewer": db_session.get(User, viewer_member.user_id),
        "outsider": outsider,
        "family_id": family.id,
        "profile_id": profile.id,
    }


def _auth(db, user: User) -> dict:
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _payload(setup, scheduled: date, provider: str = "Dr Rao", reason: str = "Checkup") -> dict:
    return {
        "family_id": setup["family_id"],
        "care_recipient_id": setup["profile_id"],
        "scheduled_date": scheduled.isoformat(),
        "start_time": "10:30",
        "provider": provider,
        "reason": reason,
    }


def _create(client, db, setup, user: User, scheduled: date) -> dict:
    response = client.post(
        "/api/appointments",
        json=_payload(setup, scheduled),
        headers=_auth(db, user),
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_appointment_returns_201(client, db_session, appointment_setup):
    setup = appointment_setup
    response = client.post(
        "/api/appointments",
        json=_payload(setup, date.today() + timedelta(days=7)),
        headers=_auth(db_session, setup["manager"]),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["care_recipient_id"] == setup["profile_id"]
    assert body["scheduled_date"] == (date.today() + timedelta(days=7)).isoformat()
    assert body["start_time"] == "10:30"
    assert body["provider"] == "Dr Rao"
    assert body["reason"] == "Checkup"
    assert body["notes"] == ""
    assert body["status"] == "scheduled"


def test_list_splits_upcoming_and_past(client, db_session, appointment_setup):
    setup = appointment_setup
    manager = setup["manager"]
    upcoming = _create(client, db_session, setup, manager, date.today() + timedelta(days=7))
    past = _create(client, db_session, setup, manager, date.today() - timedelta(days=7))

    response = client.get(
        "/api/appointments",
        params={"care_recipient_id": setup["profile_id"]},
        headers=_auth(db_session, manager),
    )
    assert response.status_code == 200
    body = response.json()
    assert [a["id"] for a in body["upcoming"]] == [upcoming["id"]]
    assert [a["id"] for a in body["past"]] == [past["id"]]


def test_get_one_appointment(client, db_session, appointment_setup):
    setup = appointment_setup
    created = _create(client, db_session, setup, setup["manager"], date.today() + timedelta(days=3))

    response = client.get(
        f"/api/appointments/{created['id']}",
        headers=_auth(db_session, setup["manager"]),
    )
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_patch_updates_fields_and_cancels(client, db_session, appointment_setup):
    setup = appointment_setup
    created = _create(client, db_session, setup, setup["manager"], date.today() + timedelta(days=3))

    response = client.patch(
        f"/api/appointments/{created['id']}",
        json={"status": "cancelled", "notes": "Cancelled by phone", "start_time": "11:00"},
        headers=_auth(db_session, setup["manager"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["notes"] == "Cancelled by phone"
    assert body["start_time"] == "11:00"
    assert body["provider"] == "Dr Rao"


def test_delete_returns_204_then_get_is_404(client, db_session, appointment_setup):
    setup = appointment_setup
    created = _create(client, db_session, setup, setup["manager"], date.today() + timedelta(days=3))

    response = client.delete(
        f"/api/appointments/{created['id']}",
        headers=_auth(db_session, setup["manager"]),
    )
    assert response.status_code == 204

    response = client.get(
        f"/api/appointments/{created['id']}",
        headers=_auth(db_session, setup["manager"]),
    )
    assert response.status_code == 404


def test_viewer_cannot_create(client, db_session, appointment_setup):
    setup = appointment_setup
    response = client.post(
        "/api/appointments",
        json=_payload(setup, date.today() + timedelta(days=7)),
        headers=_auth(db_session, setup["viewer"]),
    )
    assert response.status_code == 403


def test_outsider_cannot_create(client, db_session, appointment_setup):
    setup = appointment_setup
    response = client.post(
        "/api/appointments",
        json=_payload(setup, date.today() + timedelta(days=7)),
        headers=_auth(db_session, setup["outsider"]),
    )
    assert response.status_code == 403
