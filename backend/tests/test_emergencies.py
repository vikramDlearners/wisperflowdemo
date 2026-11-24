"""Emergencies: noted when raised, shown on the overview until marked as completed."""

import pytest
from sqlalchemy import select

from app.models.care_profile import CareProfile
from app.models.emergency import Emergency
from app.models.checkin import HealthCheckin
from app.models.family import Family
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.models.user import User
from app.services import checkin as engine
from app.services.replies import TEMPLATES

from tests.test_checkin_engine import NOW, offline, world, no_meal_questions  # noqa: F401
from tests.test_parent_invites import _auth, email, family_setup  # noqa: F401


def _open_list(client, db, world, user="manager"):
    r = client.get(f"/api/families/{world['family_id']}/dashboard", headers=_auth(db, world[user]))
    assert r.status_code == 200, r.text
    return r.json()["emergencies"]


def _user(db, world, who):
    emails = {"caregiver": "carer@example.com", "viewer": "viewer@example.com"}
    if who not in emails:
        return world[who]
    return db.execute(select(User).where(User.email == emails[who])).scalar_one()


def _complete(client, db, world, emergency_id, user="manager", family_id=None):
    return client.post(
        f"/api/families/{family_id or world['family_id']}/emergencies/{emergency_id}/complete",
        headers=_auth(db, _user(db, world, user)),
    )


def _urgent(db, world, text="I have chest pain"):
    engine.start_or_resume(db, world["ctx"], NOW)
    return engine.handle_parent_text(db, world["ctx"], text, NOW)


def test_urgent_words_are_noted_and_the_parent_told_the_family_knows(client, db_session, world):
    assert _open_list(client, db_session, world) == []
    turn = _urgent(db_session, world)
    assert "family" in turn.bot_messages[0] or "alerted" in turn.bot_messages[0]
    [item] = _open_list(client, db_session, world)
    assert item["text"] == "I have chest pain" and item["source"] == "chat"
    assert item["parent_name"] == world["profile"].display_name


def test_ordinary_health_news_is_not_an_emergency(client, db_session, world):
    _urgent(db_session, world, "my knee hurts a little")
    assert _open_list(client, db_session, world) == []


def test_more_urgent_words_add_to_the_open_emergency(client, db_session, world):
    _urgent(db_session, world)
    engine.handle_parent_text(db_session, world["ctx"], "I fell down, chest pain again", NOW)
    [item] = _open_list(client, db_session, world)
    assert item["text"].split("\n") == ["I have chest pain", "I fell down, chest pain again"]


def test_button_is_noted(client, db_session, world, email):
    client.post("/api/parent/emergency", headers=_auth(db_session, world["parent"]))
    [item] = _open_list(client, db_session, world)
    assert item["source"] == "button"


@pytest.mark.parametrize("who", ["manager", "caregiver"])
def test_completing_removes_it_from_the_overview(client, db_session, world, who):
    _urgent(db_session, world)
    [item] = _open_list(client, db_session, world)
    assert _complete(client, db_session, world, item["id"], who).status_code == 204
    assert _complete(client, db_session, world, item["id"], who).status_code == 204  # again: harmless
    assert _open_list(client, db_session, world) == []
    row = db_session.execute(select(Emergency)).scalar_one()
    db_session.refresh(row)
    assert row.status == "completed" and row.completed_by_user_id == _user(db_session, world, who).id and row.completed_at
    # A new emergency the same day shows again.
    engine.handle_parent_text(db_session, world["ctx"], "chest pain again", NOW)
    assert len(_open_list(client, db_session, world)) == 1


def test_viewers_and_other_families_cannot_complete(client, db_session, world):
    _urgent(db_session, world)
    [item] = _open_list(client, db_session, world)
    assert _complete(client, db_session, world, item["id"], "viewer").status_code == 403
    assert _complete(client, db_session, world, "nope").status_code == 404
    assert _complete(client, db_session, world, item["id"], family_id="other").status_code in (403, 404)
    assert len(_open_list(client, db_session, world)) == 1


# ---------- "anything to tell me or note down?" ----------

NOTE_ASK = "Is there anything you would like to tell me or note down?"
GOODBYE = "Take care, Amma. Talk to you soon!"


def _to_note(db, world):
    engine.start_or_resume(db, world["ctx"], NOW)
    engine.handle_parent_text(db, world["ctx"], "I am fine", NOW)
    turn = engine.handle_parent_text(db, world["ctx"], "yes", NOW)
    assert turn.bot_messages[-1] == NOTE_ASK and turn.checkin.step == "note"


def _say(db, world, text):
    return engine.handle_parent_text(db, world["ctx"], text, NOW)


@pytest.mark.parametrize("answer", ["No", "no thank you", "nothing", "வேண்டாம்", "नहीं", "లేదు", "ഇല്ല", "ಇಲ್ಲ"])
def test_nothing_to_note_says_goodbye(db_session, world, answer):
    _to_note(db_session, world)
    turn = _say(db_session, world, answer)
    assert turn.bot_messages == [GOODBYE] and turn.checkin.step == "done"
    assert turn.checkin.health_text == "I am fine"


@pytest.mark.parametrize("answer", ["Yes", "yes please"])
def test_yes_waits_for_the_note(db_session, world, answer):
    _to_note(db_session, world)
    turn = _say(db_session, world, answer)
    assert turn.bot_messages == ["Please tell me. I am listening."] and turn.checkin.step == "note"
    turn = _say(db_session, world, "Please buy my glasses")
    assert turn.bot_messages[-1] == GOODBYE and turn.checkin.step == "done"
    assert "Please buy my glasses" in turn.checkin.health_text


def test_urgent_note_is_an_emergency_without_a_goodbye(client, db_session, world):
    _to_note(db_session, world)
    turn = _say(db_session, world, "I have chest pain")
    assert GOODBYE not in turn.bot_messages and turn.checkin.step == "note"
    assert len(_open_list(client, db_session, world)) == 1


def test_note_replies_translated():
    for language, texts in TEMPLATES.items():
        assert texts["note_ask"] and texts["note_listening"], language
        if language != "en":
            assert texts["note_ask"] != TEMPLATES["en"]["note_ask"]


# ---------- whose profile ----------

def _second(db, world, name="Appa", family_id=None):
    profile = CareProfile(family_id=family_id or world["family_id"], display_name=name, greeting_name=name, preferred_language="en",
                          timezone="Asia/Kolkata")
    db.add(profile)
    db.commit()
    return profile


def _checkin(client, db, world, profile=None):
    headers = _auth(db, world["parent"])
    if profile is not None:
        headers["X-Care-Profile-Id"] = profile.id if hasattr(profile, "id") else profile
    return client.get("/api/parent/checkin", headers=headers), headers


def test_profiles_are_listed_and_children_left_out(client, db_session, world):
    appa, child = _second(db_session, world), _second(db_session, world, "Kid")
    db_session.add(ParentOnboardingProfile(care_profile_id=child.id, relationship="Son"))
    db_session.commit()
    r = client.get("/api/parent/profiles", headers=_auth(db_session, world["parent"]))
    assert r.status_code == 200, r.text
    own = {p["id"]: p["own"] for p in r.json()}
    assert own[world["profile"].id] is True and own[appa.id] is False and child.id not in own
    assert _checkin(client, db_session, world, child)[0].status_code == 404


def test_each_profile_has_its_own_conversation(client, db_session, world):
    appa = _second(db_session, world)
    _, headers = _checkin(client, db_session, world, appa)
    client.post("/api/parent/checkin/text", json={"text": "my back hurts"}, headers=headers)
    own, _ = _checkin(client, db_session, world)
    assert all("back hurts" not in m["text"] for m in own.json()["messages"])
    rows = {c.care_profile_id: c.health_text for c in db_session.execute(select(HealthCheckin)).scalars()}
    assert rows == {appa.id: "my back hurts", world["profile"].id: None}


def test_another_family_s_profile_is_refused(client, db_session, world):
    other = Family(name="Other", created_by_user_id=world["manager"].id) if hasattr(Family, "created_by_user_id") else Family(name="Other")
    db_session.add(other)
    db_session.commit()
    stranger = _second(db_session, world, "Stranger", other.id)
    assert _checkin(client, db_session, world, stranger)[0].status_code == 404
    assert _checkin(client, db_session, world, "nope")[0].status_code == 404
    headers = {**_auth(db_session, world["parent"])}
    assert client.get(f"/api/parent/profiles/{stranger.id}/photo", headers=headers).status_code == 404


def test_a_manager_cannot_chat_as_a_parent(client, db_session, world):
    headers = {**_auth(db_session, world["manager"]), "X-Care-Profile-Id": world["profile"].id}
    assert client.get("/api/parent/checkin", headers=headers).status_code in (403, 409)
    assert client.get("/api/parent/profiles", headers=headers).status_code in (403, 409)
