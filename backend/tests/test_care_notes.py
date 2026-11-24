"""Soft end-of-conversation care notes from the parent profile's deficiencies and notes."""

from types import SimpleNamespace

import pytest

from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.services import care_notes
from app.services import checkin as engine
from app.services.replies import TEMPLATES

from tests.test_checkin_engine import NOW, offline, world, no_meal_questions  # noqa: F401
from tests.test_parent_invites import email, family_setup  # noqa: F401


def _profile(deficiencies=None, notes=None, allergies=None):
    return SimpleNamespace(deficiencies=deficiencies, notes=notes, allergies=allergies)


def _keys(p):
    return [key for key, _ in care_notes.care_tips(p)]


# ---------- what is noticed ----------

@pytest.mark.parametrize("text,key", [
    ("Sugar problem", "tip_sugar"),
    ("Diabetic", "tip_sugar"),
    ("BP", "tip_bp"),
    ("High blood pressure", "tip_bp"),
    ("Low calcium", "tip_calcium"),
    ("Anaemia (low iron)", "tip_iron"),
    ("Vitamin D deficiency", "tip_vitamin_d"),
    ("High cholesterol", "tip_cholesterol"),
    ("சர்க்கரை நோய்", "tip_sugar"),
    ("बीपी की समस्या", "tip_bp"),
])
def test_deficiencies_are_recognised(text, key):
    assert _keys(_profile(deficiencies=text)) == [key]


def test_negated_conditions_are_ignored():
    assert _keys(_profile(deficiencies="No sugar problem, no BP")) == []


def test_water_amount_from_notes():
    tips = care_notes.care_tips(_profile(notes="She needs to drink 3 litres of water daily."))
    assert tips == [("tip_water_amount", {"litres": "3"})]


def test_water_without_amount():
    assert care_notes.care_tips(_profile(notes="Remind her to drink water")) == [("tip_water", {})]


def test_allergy_from_notes_and_from_the_allergies_field():
    assert care_notes.care_tips(_profile(notes="Allergic to peanuts.")) == [("tip_allergy", {"item": "peanuts"})]
    assert care_notes.care_tips(_profile(allergies="Penicillin")) == [("tip_allergy", {"item": "Penicillin"})]
    assert care_notes.care_tips(_profile(allergies="None")) == []


def test_at_most_three_tips_with_allergy_first():
    p = _profile(deficiencies="sugar, BP, calcium, cholesterol", notes="Allergic to prawns. 2 litres of water")
    assert _keys(p) == ["tip_allergy", "tip_water_amount", "tip_sugar"]


def test_nothing_known_gives_no_note():
    assert care_notes.care_tips(_profile()) == []
    assert care_notes.care_tips(None) == []


@pytest.mark.parametrize("language", ["en", "ta", "hi", "te", "ml", "kn"])
def test_care_replies_translated(language):
    for key in ("care_intro", *care_notes.TIP_KEYS):
        assert key in TEMPLATES[language], key


# ---------- in the conversation ----------

def _set_profile(db, world, **fields):
    row = ParentOnboardingProfile(user_id=world["parent"].id, **fields)
    db.add(row)
    db.commit()


def _finish(db, world):
    engine.start_or_resume(db, world["ctx"], NOW)
    engine.handle_parent_text(db, world["ctx"], "I am fine", NOW)
    return engine.handle_parent_text(db, world["ctx"], "yes", NOW)


def test_note_comes_softly_before_goodbye(db_session, world):
    _set_profile(db_session, world, deficiencies="Sugar", notes="Drink 3 litres of water daily")
    turn = _finish(db_session, world)
    assert turn.bot_messages[-2:] == [
        "Before you go, Amma, a small note from your family: "
        "Please remember to drink about 3 litres of water today. "
        "Did you check your sugar today? Please go easy on sweets.",
        "Is there anything you would like to tell me or note down?",
    ]


def test_note_is_said_once_a_day(db_session, world):
    _set_profile(db_session, world, deficiencies="BP")
    _finish(db_session, world)
    # A later dose question reopens and finishes the check-in again: no second note.
    turn = engine.handle_parent_text(db_session, world["ctx"], "ok", NOW)
    assert not any("small note from your family" in m for m in turn.bot_messages)


def test_no_note_without_profile_information(db_session, world):
    turn = _finish(db_session, world)
    assert turn.bot_messages[-1] == "Is there anything you would like to tell me or note down?"
    assert not any("small note" in m for m in turn.bot_messages)


def test_note_in_the_parents_language(db_session, world):
    world["profile"].preferred_language = "ta"
    db_session.commit()
    from app.services.parent_context import resolve_parent
    world["ctx"] = resolve_parent(db_session, world["parent"])
    _set_profile(db_session, world, deficiencies="BP")
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "நலம்", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "ஆமா", NOW)
    assert any(m.startswith("போகும் முன், Amma") for m in turn.bot_messages)
