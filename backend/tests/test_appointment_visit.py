"""After a visit: the appointment's fee, the doctor's notes, and which medicines the doctor gave at it."""

from decimal import Decimal

import pytest

from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    outsider = User(email="o@example.com", display_name="Outsider")
    db_session.add_all([manager, outsider])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    amma = CareProfile(family_id=family.id, display_name="Amma", greeting_name="Amma")
    appa = CareProfile(family_id=family.id, display_name="Appa", greeting_name="Appa")
    db_session.add_all([amma, appa])
    db_session.commit()
    meds = [Medicine(care_profile_id=amma.id, display_name=n, active=True) for n in ("Amlodipine", "Metformin")]
    other = Medicine(care_profile_id=appa.id, display_name="Atorvastatin", active=True)
    db_session.add_all([*meds, other])
    db_session.commit()
    h = {"Authorization": f"Bearer {create_auth_session(db_session, manager.id)}"}
    return {"family": family, "amma": amma, "appa": appa, "meds": meds, "other": other, "h": h,
            "outsider": {"Authorization": f"Bearer {create_auth_session(db_session, outsider.id)}"}}


def _create(client, s, **extra):
    r = client.post("/api/appointments", headers=s["h"], json={
        "family_id": s["family"].id, "care_recipient_id": s["amma"].id, "scheduled_date": "2026-12-01",
        "start_time": "10:30", "provider": "Dr. Rao", "reason": "BP review", **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_update_fee_and_doctor_notes(client, setup):
    a = _create(client, setup, fee=500)
    assert Decimal(str(a["fee"])) == Decimal("500")
    assert a["doctor_notes"] is None
    assert a["medicines"] == []

    r = client.patch(f"/api/appointments/{a['id']}", headers=setup["h"], json={
        "fee": "650.50", "doctor_notes": "BP is better. Reduce salt. Review in 3 months.", "status": "completed",
    })
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["fee"])) == Decimal("650.50")
    assert r.json()["doctor_notes"] == "BP is better. Reduce salt. Review in 3 months."

    cleared = client.patch(f"/api/appointments/{a['id']}", headers=setup["h"], json={"fee": None, "doctor_notes": None})
    assert cleared.json()["fee"] is None and cleared.json()["doctor_notes"] is None


def test_negative_fee_is_refused(client, setup):
    a = _create(client, setup)
    assert client.patch(f"/api/appointments/{a['id']}", headers=setup["h"], json={"fee": -1}).status_code == 422


def test_link_medicines_to_the_appointment(client, db_session, setup):
    a = _create(client, setup)
    ids = [m.id for m in setup["meds"]]
    r = client.put(f"/api/appointments/{a['id']}/medicines", headers=setup["h"], json={"medicine_ids": ids})
    assert r.status_code == 200, r.text
    assert sorted(m["display_name"] for m in r.json()["medicines"]) == ["Amlodipine", "Metformin"]

    med = client.get(f"/api/families/{setup['family'].id}/medicines/{ids[0]}", headers=setup["h"]).json()
    assert med["appointment_id"] == a["id"]

    # Replacing the list unlinks the one left out.
    r = client.put(f"/api/appointments/{a['id']}/medicines", headers=setup["h"], json={"medicine_ids": [ids[1]]})
    assert [m["display_name"] for m in r.json()["medicines"]] == ["Metformin"]
    db_session.expire_all()
    assert db_session.get(Medicine, ids[0]).appointment_id is None


def test_medicine_of_another_parent_cannot_be_linked(client, setup):
    a = _create(client, setup)
    r = client.put(f"/api/appointments/{a['id']}/medicines", headers=setup["h"],
                   json={"medicine_ids": [setup["other"].id]})
    assert r.status_code == 400


def test_medicine_form_can_pick_the_appointment(client, setup):
    a = _create(client, setup)
    fam = setup["family"].id
    r = client.post(f"/api/families/{fam}/medicines", headers=setup["h"], json={
        "care_profile_id": setup["amma"].id, "display_name": "Telmisartan 40 mg", "appointment_id": a["id"],
    })
    assert r.status_code == 201, r.text
    assert r.json()["appointment_id"] == a["id"]
    assert "Telmisartan 40 mg" in [m["display_name"] for m in
                                   client.get(f"/api/appointments/{a['id']}", headers=setup["h"]).json()["medicines"]]

    # Wrong parent's appointment is refused; null unlinks.
    r = client.patch(f"/api/families/{fam}/medicines/{setup['other'].id}", headers=setup["h"],
                     json={"appointment_id": a["id"]})
    assert r.status_code == 400
    med_id = setup["meds"][0].id
    client.patch(f"/api/families/{fam}/medicines/{med_id}", headers=setup["h"], json={"appointment_id": a["id"]})
    r = client.patch(f"/api/families/{fam}/medicines/{med_id}", headers=setup["h"], json={"appointment_id": None})
    assert r.json()["appointment_id"] is None


def test_deleting_the_appointment_keeps_the_medicines(client, db_session, setup):
    a = _create(client, setup)
    ids = [m.id for m in setup["meds"]]
    client.put(f"/api/appointments/{a['id']}/medicines", headers=setup["h"], json={"medicine_ids": ids})
    assert client.delete(f"/api/appointments/{a['id']}", headers=setup["h"]).status_code == 204
    db_session.expire_all()
    assert all(db_session.get(Medicine, i).appointment_id is None for i in ids)


def test_outsider_cannot_link(client, setup):
    a = _create(client, setup)
    r = client.put(f"/api/appointments/{a['id']}/medicines", headers=setup["outsider"],
                   json={"medicine_ids": [setup["meds"][0].id]})
    assert r.status_code == 403
