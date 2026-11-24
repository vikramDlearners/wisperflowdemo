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


def test_add_parent_without_relationship_creates_profile(db_session, family_setup):
    setup = family_setup
    membership = _add(db_session, setup, "friend@example.com", None, "Friend")

    assert membership.relationship is None
    profiles = _profiles_for(db_session, membership.id)
    assert len(profiles) == 1
    assert profiles[0].family_id == setup["family_id"]


def test_add_parent_grandmother_creates_profile(db_session, family_setup):
    setup = family_setup
    membership = _add(db_session, setup, "nan@example.com", "grandmother", "Nan Doe")

    assert membership.relationship == "grandmother"
    profiles = _profiles_for(db_session, membership.id)
    assert len(profiles) == 1
    assert profiles[0].family_id == setup["family_id"]


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


# ---------- linking a new Parent member to the parent's existing care profile ----------

def _existing_profile(db, family_id, name="Amma"):
    p = CareProfile(family_id=family_id, display_name=name, greeting_name=name)
    db.add(p)
    db.commit()
    return p


def test_parent_member_links_to_existing_care_profile_instead_of_a_new_one(db_session, family_setup):
    existing = _existing_profile(db_session, family_setup["family_id"])
    membership = families_svc.add_member(
        db_session, family_setup["manager"].id, family_setup["family_id"], "amma@example.com",
        family_setup["parent_role_id"], "Amma", relationship="mother", care_profile_id=existing.id,
    )
    profiles = db_session.execute(
        select(CareProfile).where(CareProfile.family_id == family_setup["family_id"])
    ).scalars().all()
    assert [p.id for p in profiles] == [existing.id]  # no duplicate parent
    db_session.refresh(existing)
    assert existing.linked_member_id == membership.id


def test_care_profile_from_another_family_is_refused(db_session, family_setup):
    other_manager = User(email="other@example.com", display_name="Other")
    db_session.add(other_manager)
    db_session.commit()
    other_family = families_svc.create_family(db_session, other_manager, "Other family")
    foreign = _existing_profile(db_session, other_family.id)
    with pytest.raises(ValueError):
        families_svc.add_member(
            db_session, family_setup["manager"].id, family_setup["family_id"], "amma@example.com",
            family_setup["parent_role_id"], "Amma", care_profile_id=foreign.id,
        )


def test_care_profile_already_linked_to_a_member_is_refused(db_session, family_setup):
    first = _add(db_session, family_setup, "appa@example.com", "father")
    [taken] = _profiles_for(db_session, first.id)
    with pytest.raises(ValueError):
        families_svc.add_member(
            db_session, family_setup["manager"].id, family_setup["family_id"], "amma@example.com",
            family_setup["parent_role_id"], "Amma", care_profile_id=taken.id,
        )


def test_api_post_member_with_care_profile_id(client, db_session, family_setup):
    existing = _existing_profile(db_session, family_setup["family_id"])
    r = client.post(
        f"/api/families/{family_setup['family_id']}/members",
        json={"email": "amma@example.com", "display_name": "Amma", "role_id": family_setup["parent_role_id"],
              "care_profile_id": existing.id},
        headers=_auth(db_session, family_setup["manager"]),
    )
    assert r.status_code == 201, r.text
    db_session.refresh(existing)
    assert existing.linked_member_id == r.json()["membership_id"]
