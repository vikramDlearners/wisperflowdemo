"""Marking an appointment completed notifies the family managers and the person responsible for it."""

import pytest

from app.models.care_profile import CareProfile
from app.models.membership import FamilyMember
from app.models.notification import Notification
from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Priya")
    manager2 = User(email="manager2@example.com", display_name="Ravi")
    carer = User(email="carer@example.com", display_name="Deepak")
    viewer = User(email="viewer@example.com", display_name="Viewer")
    outsider = User(email="outsider@example.com", display_name="Outsider")
    db_session.add_all([manager, manager2, carer, viewer, outsider])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    roles = {r.name: r for r in db_session.query(Role).filter_by(family_id=family.id)}
    db_session.add_all([
        FamilyMember(family_id=family.id, user_id=manager2.id, role_id=roles["Family manager"].id, status="active"),
        FamilyMember(family_id=family.id, user_id=carer.id, role_id=roles["Caregiver"].id, status="active"),
        FamilyMember(family_id=family.id, user_id=viewer.id, role_id=roles["Viewer"].id, status="active"),
    ])
    profile = CareProfile(family_id=family.id, display_name="Amma", greeting_name="Amma")
    db_session.add(profile)
    db_session.commit()
    h = lambda u: {"Authorization": f"Bearer {create_auth_session(db_session, u.id)}"}  # noqa: E731
    return {"family": family, "profile": profile, "manager": manager, "manager2": manager2, "carer": carer,
            "viewer": viewer, "outsider": outsider, "h": h}


def _create(client, s, **extra):
    r = client.post("/api/appointments", headers=s["h"](s["manager"]), json={
        "family_id": s["family"].id, "care_recipient_id": s["profile"].id, "scheduled_date": "2026-12-01",
        "start_time": "10:30", "provider": "Dr. Rao", "reason": "BP review", **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _notes(db, type_="appointment.completed"):
    return {n.recipient_user_id: n for n in db.query(Notification).filter_by(type=type_)}


def test_responsible_person_is_saved(client, setup):
    a = _create(client, setup, responsible_user_id=setup["carer"].id)
    assert a["responsible_user_id"] == setup["carer"].id
    r = client.patch(f"/api/appointments/{a['id']}", headers=setup["h"](setup["manager"]),
                     json={"responsible_user_id": None})
    assert r.json()["responsible_user_id"] is None


def test_responsible_person_must_be_in_the_family(client, setup):
    r = client.post("/api/appointments", headers=setup["h"](setup["manager"]), json={
        "family_id": setup["family"].id, "care_recipient_id": setup["profile"].id, "scheduled_date": "2026-12-01",
        "start_time": "10:30", "provider": "Dr. Rao", "reason": "BP review",
        "responsible_user_id": setup["outsider"].id,
    })
    assert r.status_code == 400


def test_completing_notifies_managers_and_the_responsible_person(client, db_session, setup):
    a = _create(client, setup, responsible_user_id=setup["carer"].id)
    r = client.patch(f"/api/appointments/{a['id']}", headers=setup["h"](setup["manager"]),
                     json={"status": "completed"})
    assert r.status_code == 200, r.text
    notes = _notes(db_session)
    # The manager who completed it is not told about their own action.
    assert set(notes) == {setup["manager2"].id, setup["carer"].id}
    p = notes[setup["carer"].id].payload
    assert p["appointment_id"] == a["id"]
    assert p["parent_name"] == "Amma"
    assert p["reason"] == "BP review" and p["provider"] == "Dr. Rao"
    assert p["completed_by"] == "Priya"
    assert notes[setup["carer"].id].family_id == setup["family"].id


def test_responsible_person_completing_tells_all_managers(client, db_session, setup):
    a = _create(client, setup, responsible_user_id=setup["carer"].id)
    r = client.patch(f"/api/appointments/{a['id']}", headers=setup["h"](setup["carer"]), json={"status": "completed"})
    assert r.status_code == 200, r.text
    notes = _notes(db_session)
    assert set(notes) == {setup["manager"].id, setup["manager2"].id}


def test_only_the_change_to_completed_notifies(client, db_session, setup):
    a = _create(client, setup)
    url = f"/api/appointments/{a['id']}"
    client.patch(url, headers=setup["h"](setup["manager"]), json={"notes": "bring reports"})
    assert _notes(db_session) == {}
    client.patch(url, headers=setup["h"](setup["manager"]), json={"status": "completed"})
    assert set(_notes(db_session)) == {setup["manager2"].id}
    # Saving the fee afterwards does not notify again.
    client.patch(url, headers=setup["h"](setup["manager"]), json={"status": "completed", "fee": 500})
    assert db_session.query(Notification).filter_by(type="appointment.completed").count() == 1
