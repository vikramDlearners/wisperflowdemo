import pytest

from app.models.user import User
from app.services import care
from app.services import families as families_svc
from app.services.languages import language_code


@pytest.fixture()
def manager_family(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    db_session.add(manager)
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    return manager, family


def test_care_profile_accepts_all_six_languages(db_session, manager_family):
    mgr, fam = manager_family
    for code in ("en", "ta", "hi", "te", "ml", "kn"):
        p = care.create_care_profile(db_session, mgr.id, fam.id, "P", "Amma", code)
        assert p.preferred_language == code


def test_language_code_maps_names():
    assert language_code("Telugu") == "te"
    assert language_code("malayalam") == "ml"
    assert language_code("kn") == "kn"
    assert language_code(None) == "en"
    assert language_code("French") == "en"


# ---------- timezone must be a real IANA zone ----------

def _auth(db, user):
    from app.services.auth import create_auth_session

    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def test_create_care_profile_rejects_unknown_timezone_with_422(client, db_session, manager_family):
    mgr, fam = manager_family
    r = client.post(f"/api/families/{fam.id}/care-profiles", headers=_auth(db_session, mgr),
                    json={"display_name": "P", "greeting_name": "Amma", "timezone": "Mars/Olympus"})
    assert r.status_code == 422
    r = client.post(f"/api/families/{fam.id}/care-profiles", headers=_auth(db_session, mgr),
                    json={"display_name": "P", "greeting_name": "Amma", "timezone": "Asia/Kolkata"})
    assert r.status_code == 201


def test_update_care_profile_rejects_unknown_timezone_with_422(client, db_session, manager_family):
    mgr, fam = manager_family
    p = care.create_care_profile(db_session, mgr.id, fam.id, "P", "Amma", "en")
    url = f"/api/families/{fam.id}/care-profiles/{p.id}"
    assert client.patch(url, headers=_auth(db_session, mgr), json={"timezone": "Not/AZone"}).status_code == 422
    r = client.patch(url, headers=_auth(db_session, mgr), json={"timezone": "Europe/London"})
    assert r.status_code == 200 and r.json()["timezone"] == "Europe/London"


def test_care_service_rejects_unknown_timezone(db_session, manager_family):
    mgr, fam = manager_family
    with pytest.raises(ValueError):
        care.create_care_profile(db_session, mgr.id, fam.id, "P", "Amma", "en", "Nowhere/City")
    p = care.create_care_profile(db_session, mgr.id, fam.id, "P", "Amma", "en")
    with pytest.raises(ValueError):
        care.update_care_profile(db_session, mgr.id, fam.id, p.id, {"timezone": "Nowhere/City"})
