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
