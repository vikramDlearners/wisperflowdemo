"""Medicine images: upload validates type and size; non-members are refused; GET returns the stored bytes."""

import pytest
from sqlalchemy import select

from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session
from app.services.prescription_scan import MAX_IMAGE_BYTES


@pytest.fixture()
def family_setup(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    db_session.add(manager)
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    profile = CareProfile(
        family_id=family.id,
        display_name="Amma",
        greeting_name="Amma",
    )
    db_session.add(profile)
    db_session.commit()
    medicine = Medicine(care_profile_id=profile.id, display_name="Amlodipine", active=True)
    db_session.add(medicine)
    db_session.commit()
    return {
        "manager": manager,
        "family_id": family.id,
        "medicine_id": medicine.id,
    }


def _auth(db, user: User) -> dict:
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _image_url(setup) -> str:
    return f"/api/families/{setup['family_id']}/medicines/{setup['medicine_id']}/image"


def _upload(client, setup, db, content: bytes = b"fake-image-bytes", mime_type: str = "image/jpeg", user=None):
    return client.post(
        _image_url(setup),
        files={"file": ("pill.jpg", content, mime_type)},
        headers=_auth(db, user or setup["manager"]),
    )


def test_upload_then_get_returns_same_bytes(client, db_session, family_setup):
    response = _upload(client, family_setup, db_session)
    assert response.status_code == 200
    assert response.json()["id"] == family_setup["medicine_id"]
    assert "image_data" not in response.json()

    fetched = client.get(_image_url(family_setup), headers=_auth(db_session, family_setup["manager"]))
    assert fetched.status_code == 200
    assert fetched.content == b"fake-image-bytes"
    assert fetched.headers["content-type"].startswith("image/jpeg")


def test_upload_rejects_unsupported_content_type(client, db_session, family_setup):
    response = _upload(client, family_setup, db_session, mime_type="application/pdf")
    assert response.status_code == 400
    medicine = db_session.get(Medicine, family_setup["medicine_id"])
    assert medicine.image_data is None


def test_upload_rejects_oversized_image(client, db_session, family_setup):
    response = _upload(client, family_setup, db_session, content=b"x" * (MAX_IMAGE_BYTES + 1))
    assert response.status_code == 400
    medicine = db_session.get(Medicine, family_setup["medicine_id"])
    assert medicine.image_data is None


def test_non_member_cannot_upload_or_fetch(client, db_session, family_setup):
    outsider = User(email="outsider@example.com", display_name="Outsider")
    db_session.add(outsider)
    db_session.commit()

    assert _upload(client, family_setup, db_session, user=outsider).status_code == 403

    _upload(client, family_setup, db_session)
    fetched = client.get(_image_url(family_setup), headers=_auth(db_session, outsider))
    assert fetched.status_code == 403


def test_get_without_image_returns_404(client, db_session, family_setup):
    response = client.get(_image_url(family_setup), headers=_auth(db_session, family_setup["manager"]))
    assert response.status_code == 404
