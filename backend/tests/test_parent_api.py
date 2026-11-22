"""Parent check-in API: start/resume, text turns, voice turns, spoken replies."""

import base64
from datetime import datetime, timedelta, timezone

import pytest

from app.api import parent as parent_api
from app.models.care_profile import CareProfile
from app.models.user import User
from app.services import doses as doses_svc
from app.services.adapters.speech import SpeechUnavailable

from tests.test_checkin_engine import offline, world  # noqa: F401
from tests.test_parent_invites import _auth, email, family_setup  # noqa: F401

# 08:30 IST on 2026-11-22
NOW = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)
VOICE_DOWN = {"detail": "Voice isn't available right now. Please type instead."}


class FakeTTS:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def synthesize(self, text, language):
        self.calls.append((text, language))
        if self.fail:
            raise SpeechUnavailable("down")
        return b"MP3DATA", "audio/mpeg"


class FakeSTT:
    def __init__(self, text="I am fine", fail=False):
        self.text, self.fail = text, fail
        self.calls = []

    def transcribe(self, audio, language, mime_type):
        self.calls.append((audio, language, mime_type))
        if self.fail:
            raise SpeechUnavailable("down")
        return self.text


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    monkeypatch.setattr(parent_api, "_now", lambda: NOW)


@pytest.fixture(autouse=True)
def no_real_tts(monkeypatch):
    # GET now speaks too: never reach the real TTS service from tests (the `tts` fixture overrides this).
    monkeypatch.setattr(parent_api, "get_text_to_speech", lambda: FakeTTS(fail=True))


@pytest.fixture()
def tts(monkeypatch):
    fake = FakeTTS()
    monkeypatch.setattr(parent_api, "get_text_to_speech", lambda: fake)
    return fake


def _stt(monkeypatch, **kw):
    fake = FakeSTT(**kw)
    monkeypatch.setattr(parent_api, "get_speech_to_text", lambda: fake)
    return fake


def test_get_checkin_starts_today(client, db_session, world):
    r = client.get("/api/parent/checkin", headers=_auth(db_session, world["parent"]))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "checkin_id", "step", "messages", "call_number", "help_number", "language", "reminders_due",
        "audio", "audio_type",
    }
    assert body["step"] == "health"
    assert body["language"] == "en"
    assert [(m["sender"], m["text"]) for m in body["messages"]] == [
        ("bot", "Good morning, Amma!"), ("bot", "How are you feeling today?"),
    ]
    assert all(m["created_at"] for m in body["messages"])
    assert body["call_number"] is None
    assert body["reminders_due"] == []


def test_get_checkin_lists_future_reminders(client, db_session, world):
    amlodipine = world["meds"][0]
    doses_svc.set_remind_later(db_session, world["profile"], amlodipine.id, "08:00", 30, NOW)
    r = client.get("/api/parent/checkin", headers=_auth(db_session, world["parent"]))
    due = r.json()["reminders_due"]
    assert len(due) == 1
    assert due[0]["medicine_id"] == amlodipine.id
    assert due[0]["name"] == "Amlodipine"
    assert due[0]["slot"] == "08:00"
    assert datetime.fromisoformat(due[0]["remind_at"].replace("Z", "+00:00")) == NOW + timedelta(minutes=30)


def test_text_turn_returns_messages_and_audio(client, db_session, world, tts):
    headers = _auth(db_session, world["parent"])
    client.get("/api/parent/checkin", headers=headers)
    r = client.post("/api/parent/checkin/text", json={"text": "my knee hurts"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"messages", "step", "language", "urgent", "call_number", "help_number", "audio", "audio_type"}
    assert body["messages"][0] == {
        "sender": "bot",
        "text": "Thank you for telling me. I've shared it with Carer Doe, Manager and Viewer Doe.",
    }
    assert body["step"] == "medicines"
    assert body["urgent"] is False and body["call_number"] is None
    assert base64.b64decode(body["audio"]) == b"MP3DATA"
    assert body["audio_type"] == "audio/mpeg"
    # calls[0] is the greeting spoken by the GET; the turn's reply is spoken last.
    assert tts.calls[-1] == (" ".join(m["text"] for m in body["messages"]), "en")


def test_text_turn_audio_null_when_tts_fails(client, db_session, world, monkeypatch):
    monkeypatch.setattr(parent_api, "get_text_to_speech", lambda: FakeTTS(fail=True))
    r = client.post("/api/parent/checkin/text", json={"text": "my knee hurts"},
                    headers=_auth(db_session, world["parent"]))
    assert r.status_code == 200
    assert r.json()["audio"] is None and r.json()["audio_type"] is None
    assert r.json()["messages"]


def test_urgent_turn_exposes_call_number(client, db_session, world, tts, email):
    r = client.post("/api/parent/checkin/text", json={"text": "I fell"}, headers=_auth(db_session, world["parent"]))
    assert r.json()["urgent"] is True
    assert r.json()["call_number"] == "+91 98765 43210"


def test_voice_turn_returns_transcript(client, db_session, world, tts, monkeypatch):
    stt = _stt(monkeypatch, text="my knee hurts")
    r = client.post(
        "/api/parent/checkin/voice",
        files={"file": ("clip.webm", b"AUDIO", "audio/webm")},
        headers=_auth(db_session, world["parent"]),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["transcript"] == "my knee hurts"
    assert body["step"] == "medicines"
    assert body["messages"][0]["text"].startswith("Thank you for telling me.")
    assert stt.calls == [(b"AUDIO", "en", "audio/webm")]


def test_voice_stt_failure_is_503(client, db_session, world, tts, monkeypatch):
    _stt(monkeypatch, fail=True)
    r = client.post("/api/parent/checkin/voice", files={"file": ("c.webm", b"AUDIO", "audio/webm")},
                    headers=_auth(db_session, world["parent"]))
    assert r.status_code == 503
    assert r.json() == VOICE_DOWN


def test_voice_empty_transcript_is_503(client, db_session, world, tts, monkeypatch):
    _stt(monkeypatch, text="   ")
    r = client.post("/api/parent/checkin/voice", files={"file": ("c.webm", b"AUDIO", "audio/webm")},
                    headers=_auth(db_session, world["parent"]))
    assert r.status_code == 503
    assert r.json() == VOICE_DOWN


def test_voice_over_2mb_is_rejected(client, db_session, world, tts, monkeypatch):
    stt = _stt(monkeypatch)
    big = b"x" * (2 * 1024 * 1024 + 1)
    r = client.post("/api/parent/checkin/voice", files={"file": ("c.webm", big, "audio/webm")},
                    headers=_auth(db_session, world["parent"]))
    assert r.status_code == 413
    assert stt.calls == []


def test_viewer_is_forbidden(client, db_session, family_setup):
    s = family_setup
    viewer = db_session.get(User, s["caregiver_membership"].user_id)
    db_session.add(CareProfile(family_id=s["family_id"], display_name="Amma", greeting_name="", linked_user_id=viewer.id))
    db_session.commit()
    r = client.get("/api/parent/checkin", headers=_auth(db_session, viewer))
    assert r.status_code == 403


def test_unlinked_parent_with_two_profiles_is_409(client, db_session, family_setup):
    s = family_setup
    parent = db_session.get(User, s["membership"].user_id)
    for name in ("A", "B"):
        db_session.add(CareProfile(family_id=s["family_id"], display_name=name, greeting_name=""))
    db_session.commit()
    r = client.get("/api/parent/checkin", headers=_auth(db_session, parent))
    assert r.status_code == 409
    assert r.json() == {"detail": "Ask your family to link your profile"}


def test_requires_sign_in(client):
    assert client.get("/api/parent/checkin").status_code == 401


def _texts(body):
    return [m["text"] for m in body["messages"]]


def test_reloading_does_not_greet_again(client, db_session, world):
    headers = _auth(db_session, world["parent"])
    client.get("/api/parent/checkin", headers=headers)
    body = client.get("/api/parent/checkin", headers=headers).json()
    assert _texts(body) == ["Good morning, Amma!", "How are you feeling today?"]
    assert body["step"] == "health"


def test_reload_after_reminder_time_asks_once(client, db_session, world, tts, monkeypatch):
    world["meds"][1].active = False
    db_session.commit()
    headers = _auth(db_session, world["parent"])
    client.get("/api/parent/checkin", headers=headers)
    client.post("/api/parent/checkin/text", json={"text": "fine"}, headers=headers)
    r = client.post("/api/parent/checkin/text", json={"text": "remind me in 10 minutes"}, headers=headers)
    assert r.json()["messages"][0]["text"] == "I'll remind you in 10 minutes."
    ask = "Did you take Amlodipine?"

    monkeypatch.setattr(parent_api, "_now", lambda: NOW + timedelta(minutes=5))
    assert _texts(client.get("/api/parent/checkin", headers=headers).json()).count(ask) == 1

    monkeypatch.setattr(parent_api, "_now", lambda: NOW + timedelta(minutes=11))
    body = client.get("/api/parent/checkin", headers=headers).json()
    assert _texts(body)[-1] == ask
    assert _texts(body).count(ask) == 2
    assert body["step"] == "medicines"
    body = client.get("/api/parent/checkin", headers=headers).json()
    assert _texts(body).count(ask) == 2
    assert _texts(body).count("Good morning, Amma!") == 1


PHONE = "+91 98765 43210"


def test_help_number_on_get_without_anything_urgent(client, db_session, world):
    body = client.get("/api/parent/checkin", headers=_auth(db_session, world["parent"])).json()
    assert body["call_number"] is None
    assert body["help_number"] == PHONE


def test_help_number_on_text_turn_without_anything_urgent(client, db_session, world, tts):
    r = client.post("/api/parent/checkin/text", json={"text": "I am fine"},
                    headers=_auth(db_session, world["parent"]))
    body = r.json()
    assert body["urgent"] is False and body["call_number"] is None
    assert body["help_number"] == PHONE


def test_help_number_on_voice_turn(client, db_session, world, tts, monkeypatch):
    _stt(monkeypatch, text="I am fine")
    r = client.post("/api/parent/checkin/voice", files={"file": ("v.webm", b"abc", "audio/webm")},
                    headers=_auth(db_session, world["parent"]))
    assert r.status_code == 200
    assert r.json()["help_number"] == PHONE


def test_first_get_speaks_the_greeting_and_reload_is_silent(client, db_session, world, tts):
    headers = _auth(db_session, world["parent"])
    body = client.get("/api/parent/checkin", headers=headers).json()
    assert base64.b64decode(body["audio"]) == b"MP3DATA"
    assert body["audio_type"] == "audio/mpeg"
    assert tts.calls == [("Good morning, Amma! How are you feeling today?", "en")]

    body = client.get("/api/parent/checkin", headers=headers).json()
    assert body["audio"] is None and body["audio_type"] is None
    assert len(tts.calls) == 1


def test_get_audio_null_when_tts_fails(client, db_session, world):
    # no_real_tts makes synthesize raise SpeechUnavailable.
    r = client.get("/api/parent/checkin", headers=_auth(db_session, world["parent"]))
    assert r.status_code == 200
    assert r.json()["audio"] is None and r.json()["audio_type"] is None
    assert r.json()["messages"]


def test_get_audio_null_when_tts_crashes(client, db_session, world, monkeypatch):
    class Broken:
        def synthesize(self, text, language):
            raise RuntimeError("boom")

    monkeypatch.setattr(parent_api, "get_text_to_speech", lambda: Broken())
    r = client.get("/api/parent/checkin", headers=_auth(db_session, world["parent"]))
    assert r.status_code == 200
    assert r.json()["audio"] is None


def test_reminder_reload_speaks_the_new_question(client, db_session, world, tts, monkeypatch):
    world["meds"][1].active = False
    db_session.commit()
    headers = _auth(db_session, world["parent"])
    client.get("/api/parent/checkin", headers=headers)
    client.post("/api/parent/checkin/text", json={"text": "fine"}, headers=headers)
    client.post("/api/parent/checkin/text", json={"text": "remind me in 10 minutes"}, headers=headers)
    monkeypatch.setattr(parent_api, "_now", lambda: NOW + timedelta(minutes=11))
    body = client.get("/api/parent/checkin", headers=headers).json()
    assert body["audio"] is not None
    assert tts.calls[-1] == ("Did you take Amlodipine?", "en")


# ---------- medicine photos for the parent ----------

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def test_parent_medicines_list_names_and_photo_flag(client, db_session, world):
    world["meds"][0].image_data = PNG
    world["meds"][0].image_content_type = "image/png"
    db_session.commit()
    r = client.get("/api/parent/medicines", headers=_auth(db_session, world["parent"]))
    assert r.status_code == 200
    assert r.json() == [
        {"id": world["meds"][0].id, "name": "Amlodipine", "has_image": True},
        {"id": world["meds"][1].id, "name": "Metformin", "has_image": False},
    ]


def test_parent_medicines_skip_inactive(client, db_session, world):
    world["meds"][1].active = False
    db_session.commit()
    r = client.get("/api/parent/medicines", headers=_auth(db_session, world["parent"]))
    assert [m["name"] for m in r.json()] == ["Amlodipine"]


def test_parent_medicine_image_returns_bytes(client, db_session, world):
    world["meds"][0].image_data = PNG
    world["meds"][0].image_content_type = "image/png"
    db_session.commit()
    r = client.get(f"/api/parent/medicines/{world['meds'][0].id}/image", headers=_auth(db_session, world["parent"]))
    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"


def test_parent_medicine_image_404_without_photo(client, db_session, world):
    r = client.get(f"/api/parent/medicines/{world['meds'][1].id}/image", headers=_auth(db_session, world["parent"]))
    assert r.status_code == 404


def test_parent_medicine_image_404_for_another_profile(client, db_session, world):
    other = CareProfile(family_id=world["family_id"], display_name="Appa", greeting_name="Appa", preferred_language="en",
                        timezone="Asia/Kolkata")
    db_session.add(other)
    db_session.commit()
    from app.models.medicine import Medicine
    med = Medicine(care_profile_id=other.id, display_name="Secret", active=True,
                   image_data=PNG, image_content_type="image/png")
    db_session.add(med)
    db_session.commit()
    r = client.get(f"/api/parent/medicines/{med.id}/image", headers=_auth(db_session, world["parent"]))
    assert r.status_code == 404


def test_parent_medicines_need_a_parent(client, db_session, world):
    r = client.get("/api/parent/medicines", headers=_auth(db_session, world["manager"]))
    assert r.status_code in (403, 409)


def test_turn_reports_the_current_language(client, db_session, world):
    headers = _auth(db_session, world["parent"])
    client.get("/api/parent/checkin", headers=headers)
    world["profile"].preferred_language = "hi"
    db_session.commit()
    r = client.post("/api/parent/checkin/text", json={"text": "I am fine"}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["language"] == "hi"
    # The very next reply is already in the new language.
    assert body["messages"][0]["text"].startswith("बताने के लिए धन्यवाद")
