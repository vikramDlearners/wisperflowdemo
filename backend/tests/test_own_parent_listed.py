"""The parent a caregiver describes in their own onboarding is listed on the family Overview."""

from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session

FATHER = {
    "section": "parent",
    "parent_full_name": "Ravi Kumar",
    "preferred_name": "Dad",
    "relationship": "father",
    "date_of_birth": "1950-01-01",
    "preferred_language": "Tamil",
}


def _setup(db, role=None):
    user = User(email="owner@example.com", display_name="Owner", role=role)
    db.add(user)
    db.commit()
    family = families_svc.create_family(db, user, "Family")
    return family.id, {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _save(client, headers, **changes):
    res = client.patch("/api/auth/me/profile", json={**FATHER, **changes}, headers=headers)
    assert res.status_code == 200, res.text


def _parents(client, family_id, headers):
    return client.get(f"/api/families/{family_id}/dashboard", headers=headers).json()["parents"]


def test_onboarded_father_is_listed_once_and_stays_current(client, db_session):
    family_id, headers = _setup(db_session)
    _save(client, headers)
    _save(client, headers, parent_full_name="Ravi K")
    [card] = _parents(client, family_id, headers)
    assert card["display_name"] == "Ravi K"
    assert card["relationship"] == "father"
    assert card["age"] is not None
    [profile] = client.get(f"/api/families/{family_id}/care-profiles", headers=headers).json()
    assert (profile["greeting_name"], profile["preferred_language"]) == ("Dad", "ta")


def test_existing_parent_with_the_same_name_is_reused(client, db_session):
    family_id, headers = _setup(db_session)
    created = client.post(
        f"/api/families/{family_id}/care-profiles",
        json={"display_name": "Ravi Kumar", "greeting_name": "Ravi"},
        headers=headers,
    ).json()
    _save(client, headers)
    [card] = _parents(client, family_id, headers)
    assert card["care_profile_id"] == created["id"]
    assert card["relationship"] == "father"


def test_parent_account_does_not_list_another_parent(client, db_session):
    family_id, headers = _setup(db_session, role="parent")
    _save(client, headers)
    assert _parents(client, family_id, headers) == []


def test_removing_the_parent_keeps_the_accounts_own_details(client, db_session):
    family_id, headers = _setup(db_session)
    _save(client, headers)
    [card] = _parents(client, family_id, headers)
    res = client.delete(f"/api/families/{family_id}/care-profiles/{card['care_profile_id']}", headers=headers)
    assert res.status_code == 204, res.text
    assert client.get("/api/auth/me/profile", headers=headers).json()["parent_full_name"] == "Ravi Kumar"
