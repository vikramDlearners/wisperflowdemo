"""resolve_parent finds the care profile, family and language of the signed-in parent."""

import pytest

from app.models.care_profile import CareProfile
from app.models.user import User
from app.services.auth import accept_parent_invite
from app.services.parent_context import ParentNotLinked, resolve_parent
from app.services.permissions import PermissionDenied

from tests.test_parent_invites import _token_from, email, family_setup  # noqa: F401


def _profile(db, family_id, name="Amma", greeting="", language="ta", linked=None):
    p = CareProfile(
        family_id=family_id,
        display_name=name,
        greeting_name=greeting,
        preferred_language=language,
        linked_user_id=linked,
    )
    db.add(p)
    db.commit()
    return p


def test_linked_profile_is_returned(db_session, family_setup):
    s = family_setup
    parent = db_session.get(User, s["membership"].user_id)
    p = _profile(db_session, s["family_id"], greeting="Amma ji", linked=parent.id)
    ctx = resolve_parent(db_session, parent)
    assert ctx.profile.id == p.id
    assert ctx.family_id == s["family_id"]
    assert ctx.user_id == parent.id
    assert ctx.language == "ta"
    assert ctx.greeting_name == "Amma ji"


def test_greeting_falls_back_to_display_name(db_session, family_setup):
    s = family_setup
    parent = db_session.get(User, s["membership"].user_id)
    _profile(db_session, s["family_id"], name="Amma", greeting="", linked=parent.id)
    assert resolve_parent(db_session, parent).greeting_name == "Amma"


def test_unlinked_parent_with_one_profile_is_linked(db_session, family_setup):
    s = family_setup
    parent = db_session.get(User, s["membership"].user_id)
    p = _profile(db_session, s["family_id"])
    ctx = resolve_parent(db_session, parent)
    assert ctx.profile.id == p.id
    db_session.refresh(p)
    assert p.linked_user_id == parent.id


def test_two_profiles_not_linked(db_session, family_setup):
    s = family_setup
    parent = db_session.get(User, s["membership"].user_id)
    _profile(db_session, s["family_id"], name="A")
    _profile(db_session, s["family_id"], name="B")
    with pytest.raises(ParentNotLinked):
        resolve_parent(db_session, parent)


def test_profile_linked_to_someone_else_not_taken(db_session, family_setup):
    s = family_setup
    parent = db_session.get(User, s["membership"].user_id)
    p = _profile(db_session, s["family_id"], linked=s["manager"].id)
    with pytest.raises(ParentNotLinked):
        resolve_parent(db_session, parent)
    db_session.refresh(p)
    assert p.linked_user_id == s["manager"].id


def test_viewer_linked_is_denied(db_session, family_setup):
    s = family_setup
    viewer = db_session.get(User, s["caregiver_membership"].user_id)
    _profile(db_session, s["family_id"], linked=viewer.id)
    with pytest.raises(PermissionDenied):
        resolve_parent(db_session, viewer)


def test_accept_invite_links_single_profile(client, db_session, family_setup, email):
    s = family_setup
    p = _profile(db_session, s["family_id"])
    from tests.test_parent_invites import _auth, _invite_url

    client.post(_invite_url(s["family_id"], s["membership"].id), headers=_auth(db_session, s["manager"]))
    accept_parent_invite(db_session, _token_from(email))
    db_session.refresh(p)
    assert p.linked_user_id == s["membership"].user_id


def test_accept_invite_does_not_link_with_two_profiles(client, db_session, family_setup, email):
    s = family_setup
    a = _profile(db_session, s["family_id"], name="A")
    _profile(db_session, s["family_id"], name="B")
    from tests.test_parent_invites import _auth, _invite_url

    client.post(_invite_url(s["family_id"], s["membership"].id), headers=_auth(db_session, s["manager"]))
    accept_parent_invite(db_session, _token_from(email))
    db_session.refresh(a)
    assert a.linked_user_id is None


def test_not_linked_maps_to_409():
    from app.main import _parent_not_linked

    response = _parent_not_linked(None, ParentNotLinked())
    assert response.status_code == 409
    assert response.body == b'{"detail":"Ask your family to link your profile"}'
