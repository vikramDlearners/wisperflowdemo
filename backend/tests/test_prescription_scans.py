"""Prescription scans: an invoice is rejected; a prescription waits for review; confirming creates medicines, reminders and notifications."""

import pytest
from sqlalchemy import select

from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.models.notification import Notification
from app.models.prescription_scan import MedicineReminder, PrescriptionScan
from app.models.role import Role
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
    parent_role = db_session.execute(
        select(Role).where(Role.family_id == family.id, Role.name == "Parent")
    ).scalar_one()
    viewer_role = db_session.execute(
        select(Role).where(Role.family_id == family.id, Role.name == "Viewer")
    ).scalar_one()
    parent = families_svc.add_member(
        db_session, manager.id, family.id, "parent@example.com", parent_role.id, "Parent Doe"
    )
    caregiver = families_svc.add_member(
        db_session, manager.id, family.id, "viewer@example.com", viewer_role.id, "Viewer Doe"
    )
    profile = CareProfile(
        family_id=family.id,
        display_name="Amma",
        greeting_name="Amma",
        linked_user_id=parent.user_id,
    )
    db_session.add(profile)
    db_session.commit()
    return {
        "manager": manager,
        "family_id": family.id,
        "profile_id": profile.id,
        "parent": parent,
        "caregiver": caregiver,
    }


def _auth(db, user: User) -> dict:
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _scans_url(setup, scan_id: str = "") -> str:
    base = f"/api/families/{setup['family_id']}/care-profiles/{setup['profile_id']}/prescription-scans"
    return f"{base}/{scan_id}" if scan_id else base


def _mock_scan(monkeypatch, result: dict) -> list:
    calls = []

    def fake_scan_document(image_bytes: bytes, mime_type: str) -> dict:
        calls.append((image_bytes, mime_type))
        return result

    monkeypatch.setattr(scan_svc, "scan_document", fake_scan_document)
    return calls


def _upload(client, setup, db, mime_type: str = "image/jpeg"):
    return client.post(
        _scans_url(setup),
        files={"file": ("photo.jpg", b"fake-image-bytes", mime_type)},
        headers=_auth(db, setup["manager"]),
    )


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


def test_invoice_scan_is_rejected_and_creates_nothing(client, db_session, family_setup, monkeypatch):
    _mock_scan(
        monkeypatch,
        {
            "document_type": "invoice",
            "medicines": [{"name": "Amlodipine", "dose": "5 mg", "instructions": "", "times": ["08:00"]}],
        },
    )
    response = _upload(client, family_setup, db_session)
    assert response.status_code == 201
    body = response.json()
    assert body["document_type"] == "invoice"
    assert body["status"] == "rejected"
    assert body["proposed"] == {"medicines": [], "health_notes": []}

    scan = db_session.execute(select(PrescriptionScan)).scalar_one()
    assert scan.status == "rejected"
    assert db_session.execute(select(Medicine)).scalars().all() == []
    assert db_session.execute(select(MedicineReminder)).scalars().all() == []


def test_prescription_scan_waits_for_review(client, db_session, family_setup, monkeypatch):
    calls = _mock_scan(monkeypatch, PRESCRIPTION_RESULT)
    response = client.post(
        _scans_url(family_setup),
        files={"file": ("rx.png", b"fake-image-bytes", "image/png")},
        headers=_auth(db_session, family_setup["manager"]),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending_review"
    assert body["document_type"] == "prescription"
    assert body["proposed"]["medicines"][0]["name"] == "Amlodipine"
    assert calls == [(b"fake-image-bytes", "image/png")]

    fetched = client.get(_scans_url(family_setup, body["id"]), headers=_auth(db_session, family_setup["manager"]))
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "pending_review"


def test_upload_rejects_unsupported_content_type(client, db_session, family_setup, monkeypatch):
    calls = _mock_scan(monkeypatch, PRESCRIPTION_RESULT)
    response = _upload(client, family_setup, db_session, mime_type="application/pdf")
    assert response.status_code == 400
    assert calls == []


def test_confirm_creates_medicines_reminders_and_notifies(client, db_session, family_setup, monkeypatch):
    _mock_scan(monkeypatch, PRESCRIPTION_RESULT)
    scan_id = _upload(client, family_setup, db_session).json()["id"]
    caregiver_user_id = family_setup["caregiver"].user_id
    parent_user_id = family_setup["parent"].user_id

    response = client.post(
        _scans_url(family_setup, scan_id) + "/confirm",
        json={
            "medicines": [
                {
                    "name": "Amlodipine",
                    "dose": "5 mg",
                    "instructions": "after food",
                    "times": ["08:00", "20:00"],
                    "responsible_user_id": caregiver_user_id,
                }
            ]
        },
        headers=_auth(db_session, family_setup["manager"]),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["medicine_ids"]) == 1
    assert set(body["notified_user_ids"]) == {parent_user_id, caregiver_user_id}

    medicine = db_session.execute(select(Medicine)).scalar_one()
    assert medicine.id == body["medicine_ids"][0]
    assert medicine.display_name == "Amlodipine"
    assert medicine.responsible_user_id == caregiver_user_id
    assert medicine.instructions_text == "5 mg; after food"

    reminders = db_session.execute(select(MedicineReminder)).scalars().all()
    assert sorted(r.time_of_day for r in reminders) == ["08:00", "20:00"]

    notes = db_session.execute(
        select(Notification).where(Notification.type == "medicine_reminders_created")
    ).scalars().all()
    assert {n.recipient_user_id for n in notes} == {parent_user_id, caregiver_user_id}

    scan = db_session.get(PrescriptionScan, scan_id)
    assert scan.status == "confirmed"


def test_second_confirm_returns_400(client, db_session, family_setup, monkeypatch):
    _mock_scan(monkeypatch, PRESCRIPTION_RESULT)
    scan_id = _upload(client, family_setup, db_session).json()["id"]
    payload = {"medicines": [{"name": "Amlodipine", "times": ["08:00"]}]}
    url = _scans_url(family_setup, scan_id) + "/confirm"
    headers = _auth(db_session, family_setup["manager"])

    assert client.post(url, json=payload, headers=headers).status_code == 200
    again = client.post(url, json=payload, headers=headers)
    assert again.status_code == 400
    assert len(db_session.execute(select(Medicine)).scalars().all()) == 1
