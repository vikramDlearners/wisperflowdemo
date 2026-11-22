"""Every time the parent opens or reloads the chat, a new conversation starts on screen.

Answers already saved today (health, doses, meals) are kept and not asked again.
"""

from datetime import datetime, timedelta, timezone

from app.api import parent as parent_api

from tests.test_checkin_engine import offline, world, no_meal_questions  # noqa: F401
from tests.test_parent_api import no_real_tts  # noqa: F401
from tests.test_parent_invites import _auth, email, family_setup  # noqa: F401

# 08:30 IST on 2026-11-22
NOW = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)


def _at(monkeypatch, when):
    monkeypatch.setattr(parent_api, "_now", lambda: when)


def _open(client, headers):
    r = client.get("/api/parent/checkin", params={"new_session": "true"}, headers=headers)
    assert r.status_code == 200, r.text
    return [m["text"] for m in r.json()["messages"]]


def _say(client, headers, text):
    return client.post("/api/parent/checkin/text", json={"text": text}, headers=headers).json()


def test_first_open_greets_and_asks_health(client, db_session, world, monkeypatch):
    _at(monkeypatch, NOW)
    assert _open(client, _auth(db_session, world["parent"])) == ["Good morning, Amma!", "How are you feeling today?"]


def test_reopening_starts_a_new_conversation_without_the_old_messages(client, db_session, world, monkeypatch):
    headers = _auth(db_session, world["parent"])
    _at(monkeypatch, NOW)
    _open(client, headers)
    _say(client, headers, "I am fine")  # health saved, medicines asked
    _at(monkeypatch, NOW + timedelta(minutes=5))
    texts = _open(client, headers)
    # A fresh greeting, then the open question (medicines) - not the health question again, no old messages.
    assert texts == ["Good morning, Amma!", "You have 2 medicine(s) now: Amlodipine, Metformin. Did you take them?"]


def test_finished_day_reopens_with_a_greeting_and_anything_else(client, db_session, world, monkeypatch):
    headers = _auth(db_session, world["parent"])
    _at(monkeypatch, NOW)
    _open(client, headers)
    _say(client, headers, "I am fine")
    _say(client, headers, "yes")
    _at(monkeypatch, NOW + timedelta(hours=1))
    assert _open(client, headers) == ["Good morning, Amma!", "Is there anything else you'd like to tell me?"]


def test_answers_continue_in_the_new_conversation(client, db_session, world, monkeypatch):
    headers = _auth(db_session, world["parent"])
    _at(monkeypatch, NOW)
    _open(client, headers)
    _say(client, headers, "I am fine")
    _at(monkeypatch, NOW + timedelta(minutes=5))
    _open(client, headers)
    turn = _say(client, headers, "yes")
    assert turn["messages"][0]["text"].startswith("Okay, I've noted that you took Amlodipine, Metformin")
    # A plain reload of the same session (no new_session) shows only this session's messages.
    r = client.get("/api/parent/checkin", headers=headers)
    texts = [m["text"] for m in r.json()["messages"]]
    assert texts[0] == "Good morning, Amma!"
    assert "How are you feeling today?" not in texts
    assert "yes" in texts


def test_opening_twice_within_seconds_greets_once(client, db_session, world, monkeypatch):
    headers = _auth(db_session, world["parent"])
    _at(monkeypatch, NOW)
    first = _open(client, headers)
    _at(monkeypatch, NOW + timedelta(seconds=3))
    assert _open(client, headers) == first


def test_greeting_follows_the_time_of_the_new_session(client, db_session, world, monkeypatch):
    headers = _auth(db_session, world["parent"])
    _at(monkeypatch, NOW)
    _open(client, headers)
    _at(monkeypatch, datetime(2026, 11, 22, 13, 30, tzinfo=timezone.utc))  # 19:00 IST
    assert _open(client, headers)[0] == "Good evening, Amma!"
