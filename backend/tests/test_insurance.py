"""Insurance policies: kept per family (optionally for one parent), with renewal dates and "Mark renewed"."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.care_profile import CareProfile
from app.models.membership import FamilyMember
from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session
from app.services.insurance import next_renewal


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Priya")
    viewer = User(email="viewer@example.com", display_name="Viewer")
    outsider = User(email="o@example.com", display_name="Outsider")
    db_session.add_all([manager, viewer, outsider])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    viewer_role = db_session.query(Role).filter_by(family_id=family.id, name="Viewer").one()
    db_session.add(FamilyMember(family_id=family.id, user_id=viewer.id, role_id=viewer_role.id, status="active"))
    amma = CareProfile(family_id=family.id, display_name="Amma", greeting_name="Amma")
    other_family = families_svc.create_family(db_session, outsider, "Other family")
    stranger = CareProfile(family_id=other_family.id, display_name="Stranger", greeting_name="Stranger")
    db_session.add_all([amma, stranger])
    db_session.commit()

    def h(u):
        return {"Authorization": f"Bearer {create_auth_session(db_session, u.id)}"}

    return {"base": f"/api/families/{family.id}/insurance", "amma": amma, "stranger": stranger,
            "manager": manager, "viewer": viewer, "outsider": outsider, "h": h}


POLICY = {
    "policy_type": "health",
    "insurer": "Star Health",
    "plan_name": "Senior Citizens Red Carpet",
    "policy_number": "P/211/2026/001234",
    "sum_insured": "500000",
    "premium": "28450.50",
    "premium_frequency": "yearly",
    "renewal_date": "2026-12-15",
    "agent_name": "Ramesh",
    "agent_phone": "+91 98450 12345",
    "notes": "Cashless at Apollo",
}


def _create(client, s, **extra):
    r = client.post(s["base"], json={**POLICY, "care_profile_id": s["amma"].id, **extra}, headers=s["h"](s["manager"]))
    assert r.status_code == 201, r.text
    return r.json()


def test_create_list_and_get(client, setup):
    p = _create(client, setup)
    assert p["insurer"] == "Star Health"
    assert Decimal(str(p["premium"])) == Decimal("28450.50")
    assert p["care_profile_id"] == setup["amma"].id
    assert p["renewal_date"] == "2026-12-15"
    listed = client.get(setup["base"], headers=setup["h"](setup["viewer"])).json()
    assert [x["id"] for x in listed] == [p["id"]]
    got = client.get(f"{setup['base']}/{p['id']}", headers=setup["h"](setup["viewer"])).json()
    assert got["policy_number"] == "P/211/2026/001234"


def test_list_is_sorted_by_renewal_date(client, setup):
    later = _create(client, setup, renewal_date="2027-03-01", insurer="LIC", policy_type="life")
    sooner = _create(client, setup, renewal_date="2026-12-01")
    family_wide = _create(client, setup, renewal_date="2026-12-10", care_profile_id=None, insurer="HDFC Ergo")
    listed = client.get(setup["base"], headers=setup["h"](setup["manager"])).json()
    assert [x["id"] for x in listed] == [sooner["id"], family_wide["id"], later["id"]]
    assert listed[1]["care_profile_id"] is None


def test_edit_and_delete(client, setup):
    p = _create(client, setup)
    url = f"{setup['base']}/{p['id']}"
    r = client.patch(url, json={"premium": "30000", "notes": None}, headers=setup["h"](setup["manager"]))
    assert r.status_code == 200, r.text
    assert Decimal(str(r.json()["premium"])) == Decimal("30000")
    assert r.json()["notes"] is None
    assert client.delete(url, headers=setup["h"](setup["manager"])).status_code == 204
    assert client.get(url, headers=setup["h"](setup["manager"])).status_code == 404


@pytest.mark.parametrize(
    "start, frequency, expected",
    [
        (date(2026, 12, 15), "yearly", date(2027, 12, 15)),
        (date(2026, 12, 15), "half_yearly", date(2027, 6, 15)),
        (date(2026, 12, 15), "quarterly", date(2027, 3, 15)),
        (date(2026, 12, 15), "monthly", date(2027, 1, 15)),
        (date(2024, 2, 29), "yearly", date(2025, 2, 28)),
        (date(2026, 1, 31), "monthly", date(2026, 2, 28)),
    ],
)
def test_next_renewal(start, frequency, expected):
    assert next_renewal(start, frequency) == expected


def test_mark_renewed_moves_the_date_and_keeps_the_new_premium(client, setup):
    p = _create(client, setup)
    r = client.post(f"{setup['base']}/{p['id']}/renew", json={"premium": "29900"}, headers=setup["h"](setup["manager"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["renewal_date"] == "2027-12-15"
    assert Decimal(str(body["premium"])) == Decimal("29900")
    assert body["last_renewed_on"] is not None
    # A date can also be given (the insurer's new end date).
    r = client.post(f"{setup['base']}/{p['id']}/renew", json={"renewal_date": "2028-01-05"},
                    headers=setup["h"](setup["manager"]))
    assert r.json()["renewal_date"] == "2028-01-05"


def test_bad_input_is_refused(client, setup):
    assert client.post(setup["base"], json={**POLICY, "premium": "-5"}, headers=setup["h"](setup["manager"])).status_code == 422
    assert client.post(setup["base"], json={**POLICY, "premium_frequency": "weekly"},
                       headers=setup["h"](setup["manager"])).status_code == 422
    r = client.post(setup["base"], json={**POLICY, "care_profile_id": setup["stranger"].id},
                    headers=setup["h"](setup["manager"]))
    assert r.status_code in (400, 404)


def test_permissions(client, setup):
    p = _create(client, setup)
    # A viewer can see policies but not change them; someone outside the family can do neither.
    assert client.post(setup["base"], json=POLICY, headers=setup["h"](setup["viewer"])).status_code == 403
    assert client.patch(f"{setup['base']}/{p['id']}", json={"notes": "x"},
                        headers=setup["h"](setup["viewer"])).status_code == 403
    assert client.get(setup["base"], headers=setup["h"](setup["outsider"])).status_code == 403
