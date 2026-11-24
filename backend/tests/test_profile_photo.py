"""Parent profile photo: upload from the device, show it, for your own profile and for each parent tab."""

import pytest

from app.models.care_profile import CareProfile
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    stranger = User(email="stranger@example.com", display_name="Stranger")
    db_session.add_all([manager, stranger])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    amma = CareProfile(family_id=family.id, display_name="Amma", greeting_name="Amma")
    db_session.add(amma)
    db_session.commit()
    return {"manager": manager, "stranger": stranger, "family": family, "amma": amma}


def _auth(db, user):
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _upload(client, url, headers, data=PNG, mime="image/png"):
    return client.put(url, files={"file": ("photo.png", data, mime)}, headers=headers)


def test_own_profile_photo_upload_and_read(client, db_session, setup):
    headers = _auth(db_session, setup["manager"])
    assert client.get("/api/auth/me/profile", headers=headers).json()["has_photo"] is False
    assert client.get("/api/auth/me/profile/photo", headers=headers).status_code == 404
    r = _upload(client, "/api/auth/me/profile/photo", headers)
    assert r.status_code == 200, r.text
    assert r.json()["has_photo"] is True
    photo = client.get("/api/auth/me/profile/photo", headers=headers)
    assert photo.status_code == 200
    assert photo.content == PNG
    assert photo.headers["content-type"] == "image/png"


def test_parent_tab_photo_upload_and_read(client, db_session, setup):
    s = setup
    headers = _auth(db_session, s["manager"])
    url = f"/api/families/{s['family'].id}/parents/{s['amma'].id}/profile/photo"
    r = _upload(client, url, headers, mime="image/png")
    assert r.status_code == 200, r.text
    assert r.json()["has_photo"] is True
    assert client.get(url, headers=headers).content == PNG
    profile = client.get(f"/api/families/{s['family'].id}/parents/{s['amma'].id}/profile", headers=headers)
    assert profile.json()["has_photo"] is True


@pytest.mark.parametrize(
    "data,mime",
    [(PNG, "application/pdf"), (b"", "image/png"), (b"0" * (10 * 1024 * 1024 + 1), "image/png")],
    ids=["not an image", "empty", "too big"],
)
def test_bad_photos_are_refused(client, db_session, setup, data, mime):
    r = _upload(client, "/api/auth/me/profile/photo", _auth(db_session, setup["manager"]), data=data, mime=mime)
    assert r.status_code == 400


def test_outsiders_cannot_read_or_change_a_parents_photo(client, db_session, setup):
    s = setup
    url = f"/api/families/{s['family'].id}/parents/{s['amma'].id}/profile/photo"
    headers = _auth(db_session, s["stranger"])
    assert _upload(client, url, headers).status_code == 403
    assert client.get(url, headers=headers).status_code == 403


def test_remove_photo(client, db_session, setup):
    headers = _auth(db_session, setup["manager"])
    _upload(client, "/api/auth/me/profile/photo", headers)
    r = client.delete("/api/auth/me/profile/photo", headers=headers)
    assert r.status_code == 204
    assert client.get("/api/auth/me/profile", headers=headers).json()["has_photo"] is False
