"""Family tasks move OPEN -> IN_PROGRESS -> DONE (and can be reopened); other statuses are refused."""

import pytest

from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    db_session.add(manager)
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    headers = {"Authorization": f"Bearer {create_auth_session(db_session, manager.id)}"}
    return {"base": f"/api/families/{family.id}/tasks", "headers": headers}


def _create(client, setup, **body):
    r = client.post(setup["base"], json={"title": "Book eye check-up", **body}, headers=setup["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def test_new_task_is_open(client, setup):
    assert _create(client, setup)["status"] == "OPEN"


@pytest.mark.parametrize("status", ["IN_PROGRESS", "DONE", "OPEN"])
def test_status_can_be_set(client, setup, status):
    task = _create(client, setup)
    r = client.patch(f"{setup['base']}/{task['id']}/status", json={"status": status}, headers=setup["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == status


def test_unknown_status_is_refused(client, setup):
    task = _create(client, setup)
    r = client.patch(f"{setup['base']}/{task['id']}/status", json={"status": "later"}, headers=setup["headers"])
    assert r.status_code == 400


def test_edit_priority_and_delete(client, setup):
    task = _create(client, setup, priority="normal")
    r = client.patch(f"{setup['base']}/{task['id']}", json={"priority": "high", "title": "Book eye test"},
                     headers=setup["headers"])
    assert r.status_code == 200
    assert r.json()["priority"] == "high"
    assert r.json()["title"] == "Book eye test"
    assert client.delete(f"{setup['base']}/{task['id']}", headers=setup["headers"]).status_code == 204
    assert client.get(setup["base"], headers=setup["headers"]).json() == []
