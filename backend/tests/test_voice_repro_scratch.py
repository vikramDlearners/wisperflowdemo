"""SCRATCH reproduction for the voice 503 report. Delete after use."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.adapters import speech

from tests.test_checkin_engine import offline, world  # noqa: F401
from tests.test_parent_invites import _auth, email, family_setup  # noqa: F401

VOICE_URL = "/api/parent/checkin/voice"
FILES = {"file": ("clip.webm", b"AUDIO", "audio/webm")}


class FakeTTS:
    def synthesize(self, text, language):
        return b"MP3DATA", "audio/mpeg"


class _Resp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


@pytest.fixture(autouse=True)
def stub_tts(monkeypatch):
    from app.api import parent as parent_api
    monkeypatch.setattr(parent_api, "get_text_to_speech", lambda: FakeTTS())


def test_env_and_dotenv_booleans():
    backend_dir = Path(__file__).resolve().parents[1]
    print("\nENV ELEVENLABS_API_KEY set:", "ELEVENLABS_API_KEY" in os.environ)
    print("ENV ELEVENLABS_VOICE_ID set:", "ELEVENLABS_VOICE_ID" in os.environ)
    print("backend\\.env exists:", (backend_dir / ".env").exists())
    print("settings.elevenlabs_api_key truthy (loaded config):", bool(settings.elevenlabs_api_key))


def test_case_a_key_unset(client, db_session, world, monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", None)

    def no_network(*args, **kwargs):
        raise AssertionError("urlopen must not be called when key is unset")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    r = client.post(VOICE_URL, files=FILES, headers=_auth(db_session, world["parent"]))
    print("\nCASE A status:", r.status_code, "body:", r.text)
    assert r.status_code == 503
    assert r.json() == {"detail": "Voice isn't available right now. Please type instead."}


def test_case_b_key_set_upstream_401(client, db_session, world, monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "dummy-key")

    def http_401(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", http_401)
    r = client.post(VOICE_URL, files=FILES, headers=_auth(db_session, world["parent"]))
    print("\nCASE B status:", r.status_code, "body:", r.text)
    assert r.status_code == 503


def test_case_c_key_set_valid_transcript(client, db_session, world, monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "dummy-key")
    seen = {}

    def ok(request, timeout=None):
        seen["url"] = request.full_url
        return _Resp(b'{"text": "hello"}')

    monkeypatch.setattr(urllib.request, "urlopen", ok)
    r = client.post(VOICE_URL, files=FILES, headers=_auth(db_session, world["parent"]))
    body = r.json() if r.status_code == 200 else {}
    print("\nCASE C status:", r.status_code, "upstream url:", seen.get("url"))
    print("CASE C transcript:", body.get("transcript"))
    print("CASE C reply message count:", len(body.get("messages", [])))
    assert r.status_code == 200
    assert body["transcript"] == "hello"
