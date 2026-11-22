"""Parent profile switcher: each parent's profile is read and saved through their own care profile."""

import pytest

from app.models.care_profile import CareProfile
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session


@pytest.fixture()
def switch_setup(db_session):
    manager = User(email="manager@example.com", display_name="Vikram")
    mom_user = User(email="mom@example.com", display_name="Mom")
    dad_user = User(email="dad@example.com", display_name="Dad")
    stranger = User(email="stranger@example.com", display_name="Stranger")
    db_session.add_all([manager, mom_user, dad_user, stranger])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Singh family")
    other_family = families_svc.create_family(db_session, stranger, "Other family")

    mom = CareProfile(
        family_id=family.id, display_name="Mom", greeting_name="Mom",
        timezone="Asia/Kolkata", linked_user_id=mom_user.id,
    )
    dad = CareProfile(
        family_id=family.id, display_name="Dad", greeting_name="Dad",
        timezone="Asia/Kolkata", linked_user_id=dad_user.id,
    )
    unlinked = CareProfile(
        family_id=family.id, display_name="Uncle", greeting_name="Uncle", timezone="Asia/Kolkata",
    )
    rival = CareProfile(
        family_id=other_family.id, display_name="Rival", greeting_name="Rival", timezone="Asia/Kolkata",
    )
    db_session.add_all([mom, dad, unlinked, rival])
    db_session.commit()

    db_session.add_all([
        ParentOnboardingProfile(
            user_id=mom_user.id, parent_full_name="Mom Full Name", preferred_name="Mom",
            relationship="mother",
        ),
        ParentOnboardingProfile(
            user_id=dad_user.id, parent_full_name="Dad Full Name", preferred_name="Dad",
            relationship="father",
        ),
    ])
    db_session.commit()

    return {
        "manager": manager,
        "family": family,
        "other_family": other_family,
        "mom": mom,
        "dad": dad,
        "unlinked": unlinked,
        "rival": rival,
    }


def _auth(db, user: User) -> dict:
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _url(family_id, care_profile_id) -> str:
    return f"/api/families/{family_id}/parents/{care_profile_id}/profile"


def test_get_returns_selected_parents_profile(client, db_session, switch_setup):
    s = switch_setup
    response = client.get(_url(s["family"].id, s["dad"].id), headers=_auth(db_session, s["manager"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parent_full_name"] == "Dad Full Name"
    assert body["relationship"] == "father"
    assert body["parent_full_name"] != "Mom Full Name"


def test_get_with_care_profile_from_other_family_is_not_found(client, db_session, switch_setup):
    s = switch_setup
    response = client.get(_url(s["family"].id, s["rival"].id), headers=_auth(db_session, s["manager"]))
    assert response.status_code == 404
    assert response.json()["detail"] == "Parent not found in this family"


def test_patch_changes_only_the_selected_parent(client, db_session, switch_setup):
    s = switch_setup
    response = client.patch(
        _url(s["family"].id, s["dad"].id),
        json={
            "section": "parent",
            "parent_full_name": "Dad Renamed",
            "preferred_name": "Papa",
            "relationship": "father",
        },
        headers=_auth(db_session, s["manager"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["parent_full_name"] == "Dad Renamed"

    mom_view = client.get(_url(s["family"].id, s["mom"].id), headers=_auth(db_session, s["manager"]))
    assert mom_view.status_code == 200, mom_view.text
    assert mom_view.json()["parent_full_name"] == "Mom Full Name"
    assert mom_view.json()["preferred_name"] == "Mom"


def test_patch_on_unlinked_care_profile_saves_details(client, db_session, switch_setup):
    s = switch_setup
    response = client.patch(
        _url(s["family"].id, s["unlinked"].id),
        json={"section": "parent", "parent_full_name": "Uncle", "preferred_name": "Uncle", "relationship": "other"},
        headers=_auth(db_session, s["manager"]),
    )
    assert response.status_code == 200, response.text
    view = client.get(_url(s["family"].id, s["unlinked"].id), headers=_auth(db_session, s["manager"]))
    assert view.status_code == 200, view.text
    assert view.json()["parent_full_name"] == "Uncle"


# ---------- the parent's language drives the chatbot ----------

def test_patch_language_changes_the_chatbot_language(client, db_session, switch_setup):
    s = switch_setup
    s["mom"].preferred_language = "ta"
    db_session.commit()
    response = client.patch(
        _url(s["family"].id, s["mom"].id),
        json={"section": "parent", "parent_full_name": "Mom Full Name", "preferred_name": "Mom",
              "relationship": "mother", "preferred_language": "Hindi"},
        headers=_auth(db_session, s["manager"]),
    )
    assert response.status_code == 200, response.text
    db_session.refresh(s["mom"])
    assert s["mom"].preferred_language == "hi"
    db_session.refresh(s["dad"])
    assert s["dad"].preferred_language == "en"  # another parent is untouched


def test_patch_without_language_keeps_the_chatbot_language(client, db_session, switch_setup):
    s = switch_setup
    s["mom"].preferred_language = "ta"
    db_session.commit()
    client.patch(
        _url(s["family"].id, s["mom"].id),
        json={"section": "communication", "parent_mobile": "+91 90000 00000"},
        headers=_auth(db_session, s["manager"]),
    )
    db_session.refresh(s["mom"])
    assert s["mom"].preferred_language == "ta"


def test_care_profile_language_change_shows_on_the_parent_profile(client, db_session, switch_setup):
    s = switch_setup
    response = client.patch(
        f"/api/families/{s['family'].id}/care-profiles/{s['mom'].id}",
        json={"preferred_language": "ta"},
        headers=_auth(db_session, s["manager"]),
    )
    assert response.status_code == 200, response.text
    view = client.get(_url(s["family"].id, s["mom"].id), headers=_auth(db_session, s["manager"]))
    assert view.json()["preferred_language"] == "Tamil"


def test_delete_removes_only_the_selected_parents_profile(client, db_session, switch_setup):
    s = switch_setup
    response = client.delete(_url(s["family"].id, s["dad"].id), headers=_auth(db_session, s["manager"]))
    assert response.status_code == 204, response.text

    dad_view = client.get(_url(s["family"].id, s["dad"].id), headers=_auth(db_session, s["manager"]))
    assert dad_view.status_code == 200, dad_view.text
    assert dad_view.json()["parent_full_name"] != "Dad Full Name"
    assert dad_view.json()["preferred_name"] != "Dad"

    mom_view = client.get(_url(s["family"].id, s["mom"].id), headers=_auth(db_session, s["manager"]))
    assert mom_view.status_code == 200, mom_view.text
    assert mom_view.json()["parent_full_name"] == "Mom Full Name"
    assert mom_view.json()["preferred_name"] == "Mom"


def test_delete_with_care_profile_from_other_family_is_not_found(client, db_session, switch_setup):
    s = switch_setup
    response = client.delete(_url(s["family"].id, s["rival"].id), headers=_auth(db_session, s["manager"]))
    assert response.status_code == 404
    assert response.json()["detail"] == "Parent not found in this family"


def test_delete_on_unlinked_care_profile_is_conflict(client, db_session, switch_setup):
    s = switch_setup
    response = client.delete(_url(s["family"].id, s["unlinked"].id), headers=_auth(db_session, s["manager"]))
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "This parent has no linked account yet, so their profile cannot be deleted."
    )

