"""Repro: a parent added from the Members page does not appear in the family's parents list."""

from sqlalchemy import select

from app.models.care_profile import CareProfile
from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session


def _setup(db):
    manager = User(email="owner@example.com", display_name="Owner")
    db.add(manager)
    db.commit()
    family = families_svc.create_family(db, manager, "Repro family")
    parent_role = db.execute(
        select(Role).where(Role.family_id == family.id, Role.name == "Parent")
    ).scalar_one()
    return manager, family.id, parent_role.id


def _auth(db, user: User) -> dict:
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def test_father_added_via_api_is_listed_in_dashboard_and_members(client, db_session):
    manager, family_id, parent_role_id = _setup(db_session)
    headers = _auth(db_session, manager)

    add = client.post(
        f"/api/families/{family_id}/members",
        json={
            "email": "dad@example.com",
            "display_name": "Dad Repro",
            "role_id": parent_role_id,
            "relationship": "father",
        },
        headers=headers,
    )
    assert add.status_code == 201, add.text
    member_id = add.json()["membership_id"]

    profile_ids = [
        p.id
        for p in db_session.execute(
            select(CareProfile).where(CareProfile.linked_member_id == member_id)
        ).scalars()
    ]
    assert len(profile_ids) == 1, "father member should get exactly one CareProfile"

    dash = client.get(f"/api/families/{family_id}/dashboard", headers=headers)
    assert dash.status_code == 200, dash.text
    parent_ids = [p["care_profile_id"] for p in dash.json()["parents"]]
    assert profile_ids[0] in parent_ids, f"dashboard parents={parent_ids}"

    members = client.get(f"/api/families/{family_id}/members", headers=headers)
    assert members.status_code == 200, members.text
    assert member_id in [m["membership_id"] for m in members.json()], "new member missing from members list"


def test_parent_role_without_relationship_gets_profile_and_is_listed(client, db_session):
    manager, family_id, parent_role_id = _setup(db_session)
    headers = _auth(db_session, manager)

    add = client.post(
        f"/api/families/{family_id}/members",
        json={
            "email": "norel@example.com",
            "display_name": "No Relationship Parent",
            "role_id": parent_role_id,
        },
        headers=headers,
    )
    assert add.status_code == 201, add.text
    member_id = add.json()["membership_id"]

    profiles = list(
        db_session.execute(
            select(CareProfile).where(CareProfile.linked_member_id == member_id)
        ).scalars()
    )
    assert len(profiles) == 1, (
        f"Parent-role member with no relationship has {len(profiles)} CareProfile(s); "
        "add_member only creates one for mother/father"
    )

    dash = client.get(f"/api/families/{family_id}/dashboard", headers=headers)
    parent_ids = [p["care_profile_id"] for p in dash.json()["parents"]]
    assert profiles[0].id in parent_ids, f"dashboard parents={parent_ids}"
