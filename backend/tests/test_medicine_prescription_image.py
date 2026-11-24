"""A medicine can carry a photo of its prescription, separate from the photo of the medicine itself."""

import pytest

from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session
from app.services.prescription_scan import MAX_IMAGE_BYTES


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    outsider = User(email="outsider@example.com", display_name="Outsider")
    db_session.add_all([manager, outsider])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    profile = CareProfile(family_id=family.id, display_name="Amma", greeting_name="Amma")
    db_session.add(profile)
    db_session.commit()
    medicine = Medicine(care_profile_id=profile.id, display_name="Amlodipine", active=True)
    db_session.add(medicine)
    db_session.commit()
    base = f"/api/families/{family.id}/medicines/{medicine.id}"
    return {"manager": manager, "outsider": outsider, "base": base, "url": base + "/prescription-image"}


def _auth(db, user):
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _put(client, db, setup, content=b"rx-bytes", mime="image/png", user=None):
    return client.put(
        setup["url"],
        files={"file": ("rx.png", content, mime)},
        headers=_auth(db, user or setup["manager"]),
    )


def test_upload_then_fetch(client, db_session, setup):
    before = client.get(setup["base"], headers=_auth(db_session, setup["manager"])).json()
    assert before["has_prescription_image"] is False

    r = _put(client, db_session, setup)
    assert r.status_code == 200, r.text
    assert r.json()["has_prescription_image"] is True
    assert r.json()["has_image"] is False  # the medicine photo is separate

    got = client.get(setup["url"], headers=_auth(db_session, setup["manager"]))
    assert got.status_code == 200
    assert got.content == b"rx-bytes"
    assert got.headers["content-type"] == "image/png"


def test_missing_returns_404(client, db_session, setup):
    assert client.get(setup["url"], headers=_auth(db_session, setup["manager"])).status_code == 404


@pytest.mark.parametrize(
    "content, mime",
    [(b"x", "application/pdf"), (b"", "image/jpeg"), (b"x" * (MAX_IMAGE_BYTES + 1), "image/jpeg")],
    ids=["wrong-type", "empty", "too-big"],
)
def test_bad_uploads_are_rejected(client, db_session, setup, content, mime):
    assert _put(client, db_session, setup, content, mime).status_code == 400


def test_outsider_is_refused(client, db_session, setup):
    assert _put(client, db_session, setup, user=setup["outsider"]).status_code == 403
    assert client.get(setup["url"], headers=_auth(db_session, setup["outsider"])).status_code == 403


def test_delete_removes_it(client, db_session, setup):
    _put(client, db_session, setup)
    r = client.delete(setup["url"], headers=_auth(db_session, setup["manager"]))
    assert r.status_code == 200
    assert r.json()["has_prescription_image"] is False
    assert client.get(setup["url"], headers=_auth(db_session, setup["manager"])).status_code == 404
