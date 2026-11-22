"""Medicine pricing and prescription images: total_price is derived from unit_price and count; scan images link to medicines; non-members are refused."""

from decimal import Decimal

import pytest

from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.models.prescription_scan import PrescriptionScan
from app.models.user import User
from app.services import families as families_svc
from app.services import prescription_scan as scan_svc
from app.services.auth import create_auth_session


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
        "profile_id": profile.id,
        "medicine_id": medicine.id,
    }


def _auth(db, user: User) -> dict:
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _medicine_url(setup) -> str:
    return f"/api/families/{setup['family_id']}/medicines/{setup['medicine_id']}"


def _image_url(setup) -> str:
    return f"{_medicine_url(setup)}/image"


def _patch(client, setup, db, body: dict):
    return client.patch(_medicine_url(setup), json=body, headers=_auth(db, setup["manager"]))


def _get(client, setup, db):
    return client.get(_medicine_url(setup), headers=_auth(db, setup["manager"]))


def _mock_scan(monkeypatch, result: dict) -> list:
    calls = []

    def fake_scan_document(image_bytes: bytes, mime_type: str) -> dict:
        calls.append((image_bytes, mime_type))
        return result

    monkeypatch.setattr(scan_svc, "scan_document", fake_scan_document)
    return calls


PRESCRIPTION_RESULT = {
    "document_type": "prescription",
    "medicines": [
        {
            "name": "Amlodipine",
            "dose": "5 mg",
            "instructions": "after food",
            "times": ["08:00", "20:00"],
        }
    ],
}


def test_patch_unit_price_and_count_sets_total_price(client, db_session, family_setup):
    response = _patch(client, family_setup, db_session, {"unit_price": 12.50, "total_medicine_count": 30})
    assert response.status_code == 200
    body = response.json()
    assert Decimal(str(body["total_price"])) == Decimal("375.00")
    assert body["total_medicine_count"] == 30

    fetched = _get(client, family_setup, db_session)
    assert fetched.status_code == 200
    assert Decimal(str(fetched.json()["total_price"])) == Decimal("375.00")
    assert fetched.json()["unit_price"] is not None
    assert fetched.json()["total_medicine_count"] == 30


def test_patch_only_unit_price_recalculates_total_when_count_exists(client, db_session, family_setup):
    assert _patch(client, family_setup, db_session, {"total_medicine_count": 10}).status_code == 200

    response = _patch(client, family_setup, db_session, {"unit_price": 4.25})
    assert response.status_code == 200
    assert Decimal(str(response.json()["total_price"])) == Decimal("42.50")

    fetched = _get(client, family_setup, db_session)
    assert Decimal(str(fetched.json()["total_price"])) == Decimal("42.50")
    assert fetched.json()["total_medicine_count"] == 10


def test_patch_unit_price_null_clears_total_price(client, db_session, family_setup):
    _patch(client, family_setup, db_session, {"unit_price": 12.50, "total_medicine_count": 30})

    response = _patch(client, family_setup, db_session, {"unit_price": None})
    assert response.status_code == 200
    assert response.json()["total_price"] is None

    fetched = _get(client, family_setup, db_session)
    assert fetched.json()["total_price"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"unit_price": -1},
        {"total_medicine_count": -5},
    ],
)
def test_negative_pricing_values_are_rejected(client, db_session, family_setup, body):
    response = _patch(client, family_setup, db_session, body)
    assert response.status_code == 422


def test_prescription_medicine_links_scan_and_image(client, db_session, family_setup, monkeypatch):
    _mock_scan(monkeypatch, PRESCRIPTION_RESULT)
    upload = client.post(
        f"/api/families/{family_setup['family_id']}/care-profiles/{family_setup['profile_id']}/prescription-scans",
        files={"file": ("rx.png", b"fake-image-bytes", "image/png")},
        headers=_auth(db_session, family_setup["manager"]),
    )
    assert upload.status_code == 201
    scan_id = upload.json()["id"]

    confirm = client.post(
        f"/api/families/{family_setup['family_id']}/care-profiles/{family_setup['profile_id']}"
        f"/prescription-scans/{scan_id}/confirm",
        json={"medicines": [{"name": "Amlodipine", "dose": "5 mg", "times": ["08:00"]}]},
        headers=_auth(db_session, family_setup["manager"]),
    )
    assert confirm.status_code == 200
    medicine_id = confirm.json()["medicine_ids"][0]

    fetched = client.get(
        f"/api/families/{family_setup['family_id']}/medicines/{medicine_id}",
        headers=_auth(db_session, family_setup["manager"]),
    )
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["prescription_scan_id"] == scan_id
    assert body["has_image"] is True
    assert body["image_url"] == f"/api/families/{family_setup['family_id']}/medicines/{medicine_id}/image"

    image = client.get(body["image_url"], headers=_auth(db_session, family_setup["manager"]))
    assert image.status_code == 200
    assert image.content == b"fake-image-bytes"
    assert image.headers["content-type"].startswith("image/png")

    scan = db_session.get(PrescriptionScan, scan_id)
    assert scan.status == "confirmed"


def test_non_member_gets_403_on_image(client, db_session, family_setup):
    upload = client.post(
        _image_url(family_setup),
        files={"file": ("pill.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=_auth(db_session, family_setup["manager"]),
    )
    assert upload.status_code == 200

    outsider = User(email="outsider@example.com", display_name="Outsider")
    db_session.add(outsider)
    db_session.commit()

    response = client.get(_image_url(family_setup), headers=_auth(db_session, outsider))
    assert response.status_code == 403
