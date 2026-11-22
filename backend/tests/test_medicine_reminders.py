"""Reminder times per medicine: PUT replaces them (sorted, de-duplicated); Viewers cannot edit."""

import pytest
from sqlalchemy import select

from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    db_session.add(manager)
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    profile = CareProfile(family_id=family.id, display_name="Amma", greeting_name="Amma")
    db_session.add(profile)
    db_session.commit()
    medicine = Medicine(care_profile_id=profile.id, display_name="Amlodipine", active=True)
    db_session.add(medicine)
    db_session.commit()
    viewer_role = db_session.execute(
        select(Role).where(Role.family_id == family.id, Role.name == "Viewer")
    ).scalar_one()
    families_svc.add_member(
        db_session, manager.id, family.id, "viewer@example.com", viewer_role.id, "Viewer Doe"
    )
    viewer = db_session.execute(select(User).where(User.email == "viewer@example.com")).scalar_one()
    return {"manager": manager, "viewer": viewer, "family_id": family.id, "medicine_id": medicine.id}


def _auth(db, user):
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _url(s):
    return f"/api/families/{s['family_id']}/medicines/{s['medicine_id']}/reminders"


def test_put_sorts_and_dedupes_then_get_matches(client, db_session, setup):
    headers = _auth(db_session, setup["manager"])
    r = client.put(_url(setup), json={"times": ["20:00", "08:00", "08:00"]}, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"times": ["08:00", "20:00"]}
    r = client.get(_url(setup), headers=headers)
    assert r.status_code == 200
    assert r.json() == {"times": ["08:00", "20:00"]}


def test_put_replaces_previous_times(client, db_session, setup):
    headers = _auth(db_session, setup["manager"])
    client.put(_url(setup), json={"times": ["08:00", "20:00"]}, headers=headers)
    client.put(_url(setup), json={"times": ["09:30"]}, headers=headers)
    assert client.get(_url(setup), headers=headers).json() == {"times": ["09:30"]}


def test_invalid_time_is_422(client, db_session, setup):
    r = client.put(_url(setup), json={"times": ["25:00"]}, headers=_auth(db_session, setup["manager"]))
    assert r.status_code == 422


def test_viewer_can_read_but_not_write(client, db_session, setup):
    headers = _auth(db_session, setup["viewer"])
    assert client.put(_url(setup), json={"times": ["08:00"]}, headers=headers).status_code == 403
    assert client.get(_url(setup), headers=headers).status_code == 200


def test_empty_list_clears(client, db_session, setup):
    headers = _auth(db_session, setup["manager"])
    client.put(_url(setup), json={"times": ["08:00"]}, headers=headers)
    r = client.put(_url(setup), json={"times": []}, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"times": []}
    assert client.get(_url(setup), headers=headers).json() == {"times": []}
