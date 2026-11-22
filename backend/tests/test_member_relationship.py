"""Family member relationship: optional values, Mother/Father care profile creation, and the members API."""

import pytest
from sqlalchemy import select

from app.models.care_profile import CareProfile
from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
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
    return {"manager": manager, "family_id": family.id, "parent_role_id": parent_role.id}


def _auth(db, user: User) -> dict:
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _profiles_for(db, membership_id: str) -> list[CareProfile]:
    return list(
        db.execute(select(CareProfile).where(CareProfile.linked_member_id == membership_id)).scalars()
    )


def _add(db, setup, email: str, relationship, display_name: str | None = "Someone"):
    return families_svc.add_member(
        db,
        setup["manager"].id,
        setup["family_id"],
        email,
        setup["parent_role_id"],
        display_name,
        relationship=relationship,
    )


def test_add_member_mother_creates_one_linked_profile(db_session, family_setup):
    setup = family_setup
    membership = _add(db_session, setup, "mom@example.com", "mother", "Mom Doe")

    assert membership.relationship == "mother"
    profiles = _profiles_for(db_session, membership.id)
    assert len(profiles) == 1
    assert profiles[0].family_id == setup["family_id"]


def test_add_member_father_creates_one_linked_profile(db_session, family_setup):
    setup = family_setup
    membership = _add(db_session, setup, "dad@example.com", "father", "Dad Doe")

    assert membership.relationship == "father"
    profiles = _profiles_for(db_session, membership.id)
    assert len(profiles) == 1
    assert profiles[0].family_id == setup["family_id"]


def test_add_member_without_relationship_creates_no_profile(db_session, family_setup):
    setup = family_setup
    membership = _add(db_session, setup, "friend@example.com", None, "Friend")

    assert membership.relationship is None
    assert _profiles_for(db_session, membership.id) == []


def test_add_member_grandmother_creates_no_profile(db_session, family_setup):
    setup = family_setup
    membership = _add(db_session, setup, "nan@example.com", "grandmother", "Nan Doe")

    assert membership.relationship == "grandmother"
    assert _profiles_for(db_session, membership.id) == []


def test_add_member_normalises_relationship_case_and_spaces(db_session, family_setup):
    setup = family_setup
    membership = _add(db_session, setup, "mom2@example.com", "  Mother ", "Mom Two")

    assert membership.relationship == "mother"
    assert len(_profiles_for(db_session, membership.id)) == 1


def test_add_member_unknown_relationship_raises_value_error(db_session, family_setup):
    setup = family_setup
    with pytest.raises(ValueError):
        _add(db_session, setup, "uncle@example.com", "uncle", "Uncle Doe")


def test_two_mothers_in_one_family_both_succeed(db_session, family_setup):
    setup = family_setup
    first = _add(db_session, setup, "mother1@example.com", "mother", "Mother One")
    second = _add(db_session, setup, "mother2@example.com", "mother", "Mother Two")

    assert first.id != second.id
    assert len(_profiles_for(db_session, first.id)) == 1
    assert len(_profiles_for(db_session, second.id)) == 1


def test_api_post_member_with_mother_returns_relationship(client, db_session, family_setup):
    setup = family_setup
    response = client.post(
        f"/api/families/{setup['family_id']}/members",
        json={
            "email": "api-mom@example.com",
            "display_name": "API Mom",
            "role_id": setup["parent_role_id"],
            "relationship": "mother",
        },
        headers=_auth(db_session, setup["manager"]),
    )
    assert response.status_code == 201
    assert response.json()["relationship"] == "mother"


def test_api_post_member_with_unknown_relationship_returns_422(client, db_session, family_setup):
    setup = family_setup
    response = client.post(
        f"/api/families/{setup['family_id']}/members",
        json={
            "email": "api-uncle@example.com",
            "display_name": "API Uncle",
            "role_id": setup["parent_role_id"],
            "relationship": "uncle",
        },
        headers=_auth(db_session, setup["manager"]),
    )
    assert response.status_code == 422


def test_api_get_members_includes_relationship_on_each_item(client, db_session, family_setup):
    setup = family_setup
    _add(db_session, setup, "list-mom@example.com", "mother", "List Mom")
    _add(db_session, setup, "list-plain@example.com", None, "List Plain")

    response = client.get(
        f"/api/families/{setup['family_id']}/members",
        headers=_auth(db_session, setup["manager"]),
    )
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 2
    for item in items:
        assert "relationship" in item
