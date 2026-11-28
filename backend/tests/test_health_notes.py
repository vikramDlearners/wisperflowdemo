"""Health notes: readings, conditions and allergies read from chat, notes and uploads, and food advice that uses them."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.health_note import HealthNote
from app.services import checkin as engine
from app.services import health_notes as hn
from app.services import prescription_scan as scan_svc
from app.services.auth import create_auth_session

from tests.test_checkin_engine import NOW, offline, world, no_meal_questions  # noqa: F401
from tests.test_parent_invites import email, family_setup  # noqa: F401


def _found(text):
    return {(f.kind, f.label, f.value) for f in hn.read_notes(text)}


# ---------- reading words ----------

@pytest.mark.parametrize("text,expected", [
    ("My BP is high now", {("reading", "bp", "high"), ("condition", "BP", "high")}),
    ("BP 150/95 this morning", {("reading", "bp", "150/95")}),
    ("weight 68.5 kg, pulse 78", {("reading", "weight", "68.5"), ("reading", "pulse", "78")}),
    ("I have an allergy to dust", {("allergy", "dust", None)}),
    ("I am allergic to peanuts and prawns", {("allergy", "peanuts", None), ("allergy", "prawns", None)}),
    ("मुझे मूंगफली से एलर्जी है", {("allergy", "मूंगफली", None)}),
    ("எனக்கு சுகர் அதிகம்", {("reading", "sugar", "high"), ("condition", "Sugar (diabetes)", "high")}),
])
def test_words_become_notes(text, expected):
    assert expected <= _found(text)


@pytest.mark.parametrize("text", ["no allergies", "I am not allergic to anything", "I am fine today",
                                  "my BP is not high"])
def test_nothing_or_negated_gives_nothing(text):
    assert not [f for f in hn.read_notes(text) if f.kind != hn.READING or f.value != hn.NORMAL]


def test_low_sugar_is_a_reading_not_diabetes():
    found = hn.read_notes("sugar is low today")
    assert [(f.kind, f.value) for f in found] == [("reading", "low")]


# ---------- the chat ----------

def test_chat_saves_and_says_what_it_will_track(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "My BP is high now", NOW)
    assert any("I've noted" in m and "BP high" in m for m in turn.bot_messages), turn.bot_messages
    notes = db_session.execute(select(HealthNote)).scalars().all()
    reading = next(n for n in notes if n.kind == "reading")
    assert (reading.label, reading.value, reading.source) == ("bp", "high", "chat")
    assert reading.recorded_at.date() == NOW.date()


def test_allergy_is_kept_once(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "I am allergic to peanuts", NOW)
    engine.handle_parent_text(db_session, world["ctx"], "I have peanut allergy", NOW)
    allergies = hn.active_notes(db_session, world["profile"].id, hn.ALLERGY)
    assert len(allergies) == 1


def test_food_advice_never_suggests_an_allergen(db_session, world):
    profile = world["profile"]
    hn.save_found(db_session, profile, hn.read_notes("allergic to peanuts and milk. I have sugar"), "chat", None,
                  None, NOW)
    db_session.commit()
    for meal_text in ("what can I eat for breakfast", "what should I have for lunch", "dinner ideas",
                      "snack ideas"):
        advice = hn.food_ideas(db_session, profile, meal_text, NOW, count=10)
        assert advice.foods, meal_text
        for food in (f for f in hn.FOODS if f.name in advice.foods):
            assert not {"peanut", "milk"} & set(food.contains), (meal_text, food.name)
            assert "tip_sugar" not in food.bad_for, (meal_text, food.name)


def test_can_i_eat_names_the_allergy(db_session, world):
    profile = world["profile"]
    hn.save_found(db_session, profile, hn.read_notes("I am allergic to peanuts"), "chat", None, None, NOW)
    db_session.commit()
    answer = hn.can_eat(db_session, profile, "can I eat peanut chikki?")
    assert answer is not None and answer.verdict == "allergy"


def test_food_question_in_chat_is_answered(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    hn.save_found(db_session, world["profile"], hn.read_notes("allergic to peanuts"), "chat", None, None, NOW)
    db_session.commit()
    turn = engine.handle_parent_text(db_session, world["ctx"], "what can I eat for lunch?", NOW)
    text = " ".join(turn.bot_messages)
    assert "you could have" in text and "peanut" in text.lower()


# ---------- uploads ----------

def test_scan_lists_what_it_tracks(client, db_session, world, monkeypatch):
    monkeypatch.setattr(scan_svc, "scan_document", lambda b, m: {
        "document_type": "prescription",
        "medicines": [{"name": "Amlodipine", "dose": "5 mg", "instructions": "", "times": ["08:00"]}],
        "health_notes": scan_svc._health_notes({"health_notes": {
            "conditions": ["Hypertension"], "allergies": ["Penicillin", "none"],
            "readings": [{"kind": "bp", "value": "150/95"}]}}),
    })
    url = f"/api/families/{world['family_id']}/care-profiles/{world['profile'].id}/prescription-scans"
    r = client.post(url, files={"file": ("rx.jpg", b"img", "image/jpeg")},
                    headers={"Authorization": f"Bearer {create_auth_session(db_session, world['manager'].id)}"})
    assert r.status_code == 201, r.text
    assert r.json()["tracking"] == ["Amlodipine 5 mg, reminders at 08:00", "Hypertension",
                                    "allergy to Penicillin", "BP 150/95 mmHg"]
    sources = {n.source for n in db_session.execute(select(HealthNote)).scalars()}
    assert sources == {"upload"}


# ---------- the API ----------

def _h(db, user):
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def test_family_adds_lists_graphs_and_removes(client, db_session, world):
    base = f"/api/families/{world['family_id']}/care-profiles/{world['profile'].id}/health"
    h = _h(db_session, world["manager"])
    r = client.post(base, json={"text": "Allergic to prawns. BP 140/90"}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["tracking"] == ["allergy to prawns", "BP 140/90 mmHg"]
    r = client.post(base, json={"kind": "sugar", "value": "180"}, headers=h)
    assert r.json()["tracking"] == ["Sugar 180 mg/dL"]
    assert client.post(base, json={"kind": "bp", "value": "lots"}, headers=h).status_code == 400

    listed = client.get(base, headers=h).json()
    assert [a["label"] for a in listed["allergies"]] == ["prawns"]
    assert "prawns" in listed["known_allergies"]
    assert len(listed["readings"]) == 2

    graph = client.get(f"{base}/readings?kind=bp", headers=h).json()
    assert [(g["value_num"], g["value_num2"]) for g in graph] == [(140, 90)]

    allergy_id = listed["allergies"][0]["id"]
    assert client.delete(f"{base}/{allergy_id}", headers=h).status_code == 204
    assert client.get(base, headers=h).json()["allergies"] == []


def test_parent_note_says_what_it_tracks(client, db_session, world):
    r = client.post("/api/parent/notes", json={"text": "Doctor said my sugar is high"},
                    headers=_h(db_session, world["parent"]))
    assert r.status_code == 201, r.text
    assert "Sugar high" in r.json()["tracking"]
    r = client.get("/api/parent/health", headers=_h(db_session, world["parent"]))
    assert r.status_code == 200 and r.json()["readings"][0]["value"] == "high"


def test_outsider_cannot_read_the_list(client, db_session, world):
    from app.models.user import User

    outsider = User(email="nobody@example.com", display_name="Nobody")
    db_session.add(outsider)
    db_session.commit()
    base = f"/api/families/{world['family_id']}/care-profiles/{world['profile'].id}/health"
    assert client.get(base, headers=_h(db_session, outsider)).status_code in (403, 404)


def test_old_readings_drop_out_of_the_graph(client, db_session, world):
    old = HealthNote(family_id=world["family_id"], care_profile_id=world["profile"].id, kind="reading",
                     label="pulse", value="70", value_num=70, source="family", active=True,
                     recorded_at=datetime.now(timezone.utc) - timedelta(days=200))
    db_session.add(old)
    db_session.commit()
    base = f"/api/families/{world['family_id']}/care-profiles/{world['profile'].id}/health"
    h = _h(db_session, world["manager"])
    assert client.get(f"{base}/readings?days=90", headers=h).json() == []
    assert len(client.get(f"{base}/readings?days=365", headers=h).json()) == 1
