"""Soft-delete of family members: creator and self protection, hidden from the members list, permission check."""

import pytest
from sqlalchemy import select

from app.models.membership import FamilyMember
from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session


@pytest.fixture()
def family_setup(db_session):
    manager = User(email="creator@example.com", display_name="Creator")
    db_session.add(manager)
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Removal family")
    roles = {
        role.name: role.id
        for role in db_session.execute(select(Role).where(Role.family_id == family.id)).scalars()
    }
    creator_membership = db_session.execute(
        select(FamilyMember).where(FamilyMember.family_id == family.id, FamilyMember.user_id == manager.id)
    ).scalar_one()
    return {
        "manager": manager,
        "family_id": family.id,
        "manager_role_id": roles["Family manager"],
        "caregiver_role_id": roles["Caregiver"],
        "viewer_role_id": roles["Viewer"],
        "creator_membership_id": creator_membership.id,
    }


def _auth(db, user: User) -> dict:
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _add(db, setup, email: str, role_id: str, display_name: str = "Someone") -> FamilyMember:
    return families_svc.add_member(
        db, setup["manager"].id, setup["family_id"], email, role_id, display_name
    )


def test_creator_cannot_be_removed(db_session, family_setup):
    setup = family_setup
    # A second Family manager (not the creator) tries to remove the creator.
    co_manager = _add(db_session, setup, "co@example.com", setup["manager_role_id"], "Co Manager")

    with pytest.raises(ValueError):
        families_svc.remove_member(
            db_session, setup["family_id"], setup["creator_membership_id"], co_manager.user_id
        )

    creator = db_session.get(FamilyMember, setup["creator_membership_id"])
    assert creator.status == "active"


def test_non_creator_member_is_removed_and_hidden_from_list(client, db_session, family_setup):
    setup = family_setup
    friend = _add(db_session, setup, "friend@example.com", setup["caregiver_role_id"], "Friend")

    response = client.delete(
        f"/api/families/{setup['family_id']}/members/{friend.id}",
        headers=_auth(db_session, setup["manager"]),
    )
    assert response.status_code == 204

    db_session.refresh(friend)
    assert friend.status == "removed"

    listing = client.get(
        f"/api/families/{setup['family_id']}/members",
        headers=_auth(db_session, setup["manager"]),
    )
    assert listing.status_code == 200
    assert friend.id not in [item["membership_id"] for item in listing.json()]


def test_removing_yourself_is_rejected(client, db_session, family_setup):
    setup = family_setup
    co_manager = _add(db_session, setup, "self@example.com", setup["manager_role_id"], "Self Manager")

    with pytest.raises(ValueError):
        families_svc.remove_member(
            db_session, setup["family_id"], co_manager.id, co_manager.user_id
        )

    response = client.delete(
        f"/api/families/{setup['family_id']}/members/{co_manager.id}",
        headers=_auth(db_session, db_session.get(User, co_manager.user_id)),
    )
    assert response.status_code == 400
    db_session.refresh(co_manager)
    assert co_manager.status == "active"


def test_user_without_members_manage_gets_403(client, db_session, family_setup):
    setup = family_setup
    viewer = _add(db_session, setup, "viewer@example.com", setup["viewer_role_id"], "Viewer")
    friend = _add(db_session, setup, "target@example.com", setup["caregiver_role_id"], "Target")

    response = client.delete(
        f"/api/families/{setup['family_id']}/members/{friend.id}",
        headers=_auth(db_session, db_session.get(User, viewer.user_id)),
    )
    assert response.status_code == 403
    db_session.refresh(friend)
    assert friend.status == "active"
