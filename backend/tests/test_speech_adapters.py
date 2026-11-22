import http.client
import io
import json
import urllib.error

import pytest

from app.core.config import settings
from app.services.adapters import speech
from app.services.adapters.speech import (
    ElevenLabsSpeechToText,
    ElevenLabsTextToSpeech,
    SpeechUnavailable,
    get_speech_to_text,
    get_text_to_speech,
)


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def captured(monkeypatch):
    calls = {}

    def install(body: bytes):
        def fake_urlopen(request, timeout=None):
            calls["request"] = request
            calls["timeout"] = timeout
            return FakeResponse(body)

        monkeypatch.setattr(speech.urllib.request, "urlopen", fake_urlopen)

    calls["install"] = install
    return calls


@pytest.fixture(autouse=True)
def keyed(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "secret-key-123")
    monkeypatch.setattr(settings, "elevenlabs_voice_id", "voice-abc")


def test_stt_request_and_text(captured):
    captured["install"](json.dumps({"text": "hello there"}).encode())
    text = ElevenLabsSpeechToText().transcribe(b"AUDIO", "ta", "audio/webm")
    assert text == "hello there"
    req = captured["request"]
    assert req.full_url == "https://api.elevenlabs.io/v1/speech-to-text"
    assert req.get_header("Xi-api-key") == "secret-key-123"
    assert req.get_header("Content-type").startswith("multipart/form-data; boundary=")
    assert b'name="language_code"' in req.data and b"\r\n\r\nta\r\n" in req.data
    assert b'name="model_id"' in req.data and b"scribe_v1" in req.data
    assert b'name="file"; filename="audio.webm"' in req.data
    assert b"Content-Type: audio/webm" in req.data and b"AUDIO" in req.data
    assert captured["timeout"] == 20


def test_tts_request_and_bytes(captured):
    captured["install"](b"MP3DATA")
    audio, mime = ElevenLabsTextToSpeech().synthesize("Namaste", "hi")
    assert (audio, mime) == (b"MP3DATA", "audio/mpeg")
    req = captured["request"]
    assert req.full_url == "https://api.elevenlabs.io/v1/text-to-speech/voice-abc"
    assert req.get_header("Xi-api-key") == "secret-key-123"
    assert req.get_header("Accept") == "audio/mpeg"
    assert json.loads(req.data) == {
        "text": "Namaste",
        "model_id": "eleven_multilingual_v2",
    }


def test_missing_key(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", None)
    with pytest.raises(SpeechUnavailable):
        ElevenLabsSpeechToText().transcribe(b"a", "en", "audio/webm")
    with pytest.raises(SpeechUnavailable):
        ElevenLabsTextToSpeech().synthesize("hi", "en")


def test_missing_voice(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_voice_id", None)
    with pytest.raises(SpeechUnavailable):
        ElevenLabsTextToSpeech().synthesize("hi", "en")


def test_http_error_hides_key(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b""))

    monkeypatch.setattr(speech.urllib.request, "urlopen", boom)
    with pytest.raises(SpeechUnavailable) as info:
        ElevenLabsSpeechToText().transcribe(b"a", "en", "audio/webm")
    assert "secret-key-123" not in str(info.value)
    with pytest.raises(SpeechUnavailable):
        ElevenLabsTextToSpeech().synthesize("hi", "en")


def test_network_error(monkeypatch):
    def boom(request, timeout=None):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(speech.urllib.request, "urlopen", boom)
    with pytest.raises(SpeechUnavailable):
        ElevenLabsTextToSpeech().synthesize("hi", "en")


def test_bad_stt_response(captured):
    captured["install"](b"not json")
    with pytest.raises(SpeechUnavailable):
        ElevenLabsSpeechToText().transcribe(b"a", "en", "audio/webm")


def test_factories():
    assert isinstance(get_speech_to_text(), ElevenLabsSpeechToText)
    assert isinstance(get_text_to_speech(), ElevenLabsTextToSpeech)


def test_incomplete_read_becomes_speech_unavailable(monkeypatch):
    def boom(request, timeout=None):
        raise http.client.IncompleteRead(b"x")

    monkeypatch.setattr(speech.urllib.request, "urlopen", boom)
    with pytest.raises(SpeechUnavailable):
        ElevenLabsSpeechToText().transcribe(b"a", "en", "audio/webm")
    with pytest.raises(SpeechUnavailable):
        ElevenLabsTextToSpeech().synthesize("hi", "en")


def test_mime_parameters_stripped(captured):
    captured["install"](json.dumps({"text": "x"}).encode())
    ElevenLabsSpeechToText().transcribe(b"A", "en", "Audio/WebM;codecs=opus")
    data = captured["request"].data
    assert b"Content-Type: audio/webm\r\n" in data and b"codecs" not in data
    assert b'filename="audio.webm"' in data


def test_mime_crlf_not_injected(captured):
    captured["install"](json.dumps({"text": "x"}).encode())
    ElevenLabsSpeechToText().transcribe(b"A", "en", "audio/webm\r\nX-Evil: 1")
    data = captured["request"].data
    assert b"X-Evil" not in data
    assert b"Content-Type: application/octet-stream\r\n" in data
    assert b'filename="audio.bin"' in data


def test_mime_mp4_and_unknown_subtype(captured):
    captured["install"](json.dumps({"text": "x"}).encode())
    ElevenLabsSpeechToText().transcribe(b"A", "en", "audio/mp4")
    assert b'filename="audio.mp4"' in captured["request"].data
    ElevenLabsSpeechToText().transcribe(b"A", "en", "audio/ogg")
    assert b'filename="audio.bin"' in captured["request"].data
