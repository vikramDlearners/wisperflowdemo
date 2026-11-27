"""Shareable task links: a token opens exactly one task without sign-in, until it expires or is revoked."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.membership import FamilyMember
from app.models.notification import Notification
from app.models.role import Role, RolePermission
from app.models.task import Task
from app.models.task_link import TaskShareLink
from app.models.user import User
from app.services import families as families_svc
from app.services import task_links as svc
from app.services.auth import create_auth_session

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    db_session.add(manager)
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    headers = {"Authorization": f"Bearer {create_auth_session(db_session, manager.id)}"}
    return {"db": db_session, "family": family, "manager": manager, "headers": headers,
            "base": f"/api/families/{family.id}/tasks"}


def _task(client, setup, title="Pick up eye drops"):
    r = client.post(setup["base"], json={"title": title}, headers=setup["headers"])
    assert r.status_code == 201, r.text
    return r.json()


def _link(client, setup, task_id):
    r = client.post(f"{setup['base']}/{task_id}/share-link", headers=setup["headers"])
    assert r.status_code == 200, r.text
    return r.json()


# --- Making links -------------------------------------------------------------------------


def test_link_is_stable_until_revoked(client, setup):
    task = _task(client, setup)
    first = _link(client, setup, task["id"])
    assert first["path"] == f"/task-link/{first['token']}"
    assert _link(client, setup, task["id"])["token"] == first["token"]

    assert client.delete(f"{setup['base']}/{task['id']}/share-link", headers=setup["headers"]).status_code == 204
    assert client.get(f"/api/task-links/{first['token']}").status_code == 410
    second = _link(client, setup, task["id"])
    assert second["token"] != first["token"]
    assert client.get(f"/api/task-links/{second['token']}").status_code == 200


def test_making_a_link_needs_sign_in_and_membership(client, setup, db_session):
    task = _task(client, setup)
    assert client.post(f"{setup['base']}/{task['id']}/share-link").status_code == 401
    outsider = User(email="outsider@example.com", display_name="Outsider")
    db_session.add(outsider)
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_auth_session(db_session, outsider.id)}"}
    assert client.post(f"{setup['base']}/{task['id']}/share-link", headers=headers).status_code == 403


def test_making_a_link_needs_tasks_create(client, setup, db_session):
    task = _task(client, setup)
    viewer = User(email="viewer@example.com", display_name="Viewer")
    db_session.add(viewer)
    db_session.flush()
    role = Role(family_id=setup["family"].id, name="Looker")
    db_session.add(role)
    db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission="tasks.view"))
    db_session.add(FamilyMember(family_id=setup["family"].id, user_id=viewer.id, role_id=role.id, status="active"))
    db_session.commit()
    headers = {"Authorization": f"Bearer {create_auth_session(db_session, viewer.id)}"}
    assert client.post(f"{setup['base']}/{task['id']}/share-link", headers=headers).status_code == 403


# --- Token access rules -------------------------------------------------------------------


def test_link_opens_the_task_without_sign_in(client, setup):
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    r = client.get(f"/api/task-links/{token}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == task["id"]
    assert body["title"] == "Pick up eye drops"
    assert body["status"] == "OPEN"
    assert body["notes"] == [] and body["images"] == []
    assert r.headers["cache-control"] == "private, no-store"


@pytest.mark.parametrize("make_bad", [
    lambda t: "nonsense",
    lambda t: t[:-1] + ("A" if t[-1] != "A" else "B"),          # signature altered
    lambda t: t.split(".")[0],                                    # signature missing
    lambda t: "00000000-0000-0000-0000-000000000000." + t.split(".")[1],  # signature from another id
])
def test_wrong_token_is_404(client, setup, make_bad):
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    bad = make_bad(token)
    assert client.get(f"/api/task-links/{bad}").status_code == 404
    assert client.post(f"/api/task-links/{bad}/complete").status_code == 404
    assert client.post(f"/api/task-links/{bad}/notes", json={"body": "hi"}).status_code == 404
    assert client.post(f"/api/task-links/{bad}/images",
                       files={"file": ("a.png", PNG, "image/png")}).status_code == 404


def test_expired_token_is_410_for_every_action(client, setup, db_session):
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    link = db_session.get(TaskShareLink, token.split(".")[0])
    link.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    assert client.get(f"/api/task-links/{token}").status_code == 410
    assert client.post(f"/api/task-links/{token}/complete").status_code == 410
    assert client.post(f"/api/task-links/{token}/notes", json={"body": "hi"}).status_code == 410
    assert client.post(f"/api/task-links/{token}/images",
                       files={"file": ("a.png", PNG, "image/png")}).status_code == 410
    assert db_session.get(Task, task["id"]).status == "OPEN"


def test_expired_link_is_replaced_by_a_new_one(client, setup, db_session):
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    db_session.get(TaskShareLink, token.split(".")[0]).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    fresh = _link(client, setup, task["id"])
    assert fresh["token"] != token
    assert client.get(f"/api/task-links/{fresh['token']}").status_code == 200


def test_token_only_reaches_its_own_task(client, setup):
    task_a = _task(client, setup, "Task A")
    task_b = _task(client, setup, "Task B")
    token_a = _link(client, setup, task_a["id"])["token"]
    token_b = _link(client, setup, task_b["id"])["token"]

    image_b = client.post(f"/api/task-links/{token_b}/images", files={"file": ("b.png", PNG, "image/png")}).json()
    # Task A's token cannot fetch task B's photo, even with the right photo id.
    assert client.get(f"/api/task-links/{token_a}/images/{image_b['id']}").status_code == 404
    assert client.get(f"/api/task-links/{token_b}/images/{image_b['id']}").status_code == 200

    # Completing through A leaves B untouched, and B's view never shows A's notes.
    client.post(f"/api/task-links/{token_a}/notes", json={"body": "note for A"})
    assert client.post(f"/api/task-links/{token_a}/complete").status_code == 204
    view_b = client.get(f"/api/task-links/{token_b}").json()
    assert view_b["title"] == "Task B"
    assert view_b["status"] == "OPEN"
    assert view_b["notes"] == []


def test_token_does_not_unlock_family_routes(client, setup):
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    r = client.get(setup["base"], headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_link_dies_with_its_task(client, setup):
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    client.delete(f"{setup['base']}/{task['id']}", headers=setup["headers"])
    assert client.get(f"/api/task-links/{token}").status_code in (404, 410)


# --- Actions ------------------------------------------------------------------------------


def test_complete_marks_done_and_tells_the_creator(client, setup, db_session):
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    assert client.post(f"/api/task-links/{token}/complete").status_code == 204
    assert client.get(f"/api/task-links/{token}").json()["status"] == "DONE"
    # A second press changes nothing and sends no second notification.
    assert client.post(f"/api/task-links/{token}/complete").status_code == 204
    sent = db_session.query(Notification).filter_by(
        recipient_user_id=setup["manager"].id, type="task.completed"
    ).count()
    assert sent == 1


def test_notes_are_saved_and_shown(client, setup):
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    r = client.post(f"/api/task-links/{token}/notes", json={"body": "  Bought them at Apollo  ", "author_name": "Ravi"})
    assert r.status_code == 201, r.text
    assert r.json()["body"] == "Bought them at Apollo"
    notes = client.get(f"/api/task-links/{token}").json()["notes"]
    assert [(n["body"], n["author_name"]) for n in notes] == [("Bought them at Apollo", "Ravi")]


@pytest.mark.parametrize("body", ["", "   ", "x" * 2001])
def test_bad_notes_are_refused(client, setup, body):
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    assert client.post(f"/api/task-links/{token}/notes", json={"body": body}).status_code in (400, 422)


@pytest.mark.parametrize("name,data,mime", [("a.png", PNG, "image/png"), ("a.jpg", JPEG, "image/jpeg")])
def test_upload_and_fetch_image(client, setup, name, data, mime):
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    r = client.post(f"/api/task-links/{token}/images", files={"file": (name, data, mime)})
    assert r.status_code == 201, r.text
    image = r.json()
    assert image["size_bytes"] == len(data)
    got = client.get(image["url"])
    assert got.status_code == 200
    assert got.content == data
    assert got.headers["content-type"] == mime
    assert got.headers["x-content-type-options"] == "nosniff"
    assert [i["id"] for i in client.get(f"/api/task-links/{token}").json()["images"]] == [image["id"]]


@pytest.mark.parametrize("data,mime", [
    (b"%PDF-1.4 not an image", "application/pdf"),   # wrong type
    (b"<svg></svg>", "image/svg+xml"),               # not allowed
    (b"plain text pretending", "image/png"),          # claims PNG, is not
    (b"", "image/png"),                               # empty
])
def test_bad_images_are_refused(client, setup, data, mime):
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    assert client.post(f"/api/task-links/{token}/images", files={"file": ("f", data, mime)}).status_code == 400


def test_oversized_image_is_refused(client, setup, monkeypatch):
    monkeypatch.setattr(svc, "MAX_IMAGE_BYTES", 100)
    import app.api.task_links as api
    monkeypatch.setattr(api, "MAX_IMAGE_BYTES", 100)
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    big = PNG + b"\x00" * 200
    r = client.post(f"/api/task-links/{token}/images", files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 400
    assert "MB" in r.json()["detail"]


def test_image_count_is_capped(client, setup, monkeypatch):
    monkeypatch.setattr(svc, "MAX_IMAGES_PER_TASK", 2)
    task = _task(client, setup)
    token = _link(client, setup, task["id"])["token"]
    for _ in range(2):
        assert client.post(f"/api/task-links/{token}/images", files={"file": ("a.png", PNG, "image/png")}).status_code == 201
    assert client.post(f"/api/task-links/{token}/images", files={"file": ("a.png", PNG, "image/png")}).status_code == 400
