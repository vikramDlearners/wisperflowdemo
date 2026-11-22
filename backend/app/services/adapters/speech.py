"""Speech-to-text and text-to-speech through ElevenLabs.

The parent voice chatbot turns a voice clip into text and speaks replies back.
Tests mock get_speech_to_text() / get_text_to_speech(), or urllib.request.urlopen.
The API key is never logged or put in an exception message.
"""

import http.client
import json
import re
import urllib.error
import urllib.request
import uuid
from typing import Protocol

from app.core.config import settings

STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
TIMEOUT_SECONDS = 20


class SpeechUnavailable(Exception):
    """Speech is not configured, or the ElevenLabs request failed."""


class SpeechToText(Protocol):
    def transcribe(self, audio: bytes, language: str, mime_type: str) -> str: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str, language: str) -> tuple[bytes, str]: ...


def _api_key() -> str:
    key = settings.elevenlabs_api_key
    if not key:
        raise SpeechUnavailable("ElevenLabs is not configured")
    return key


def _send(request: urllib.request.Request) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        raise SpeechUnavailable(f"ElevenLabs request failed with HTTP status {status}") from None
    except urllib.error.URLError:
        raise SpeechUnavailable("ElevenLabs request failed (network error)") from None
    except (OSError, http.client.HTTPException):
        raise SpeechUnavailable("ElevenLabs request failed (could not read response)") from None


_AUDIO_MIME = re.compile(r"^audio/[a-z0-9.+-]+$")
_EXTENSIONS = {"webm": "webm", "mp4": "mp4"}


def _clean_audio_mime(mime_type: str) -> tuple[str, str]:
    """Whitelist the browser-supplied mime type; return (content_type, filename)."""
    base = (mime_type or "").split(";", 1)[0].strip().lower()
    if not _AUDIO_MIME.fullmatch(base):
        return "application/octet-stream", "audio.bin"
    return base, f"audio.{_EXTENSIONS.get(base.split('/', 1)[1], 'bin')}"


def _multipart(fields: dict[str, str], file_field: str, filename: str, content_type: str, data: bytes):
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(data)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class ElevenLabsSpeechToText:
    def transcribe(self, audio: bytes, language: str, mime_type: str) -> str:
        api_key = _api_key()
        file_type, filename = _clean_audio_mime(mime_type)
        body, content_type = _multipart(
            {"model_id": settings.elevenlabs_stt_model, "language_code": language},
            "file",
            filename,
            file_type,
            audio,
        )
        request = urllib.request.Request(
            STT_URL,
            data=body,
            headers={"xi-api-key": api_key, "Content-Type": content_type},
            method="POST",
        )
        raw = _send(request)
        try:
            text = json.loads(raw.decode("utf-8"))["text"]
        except (KeyError, TypeError, ValueError):
            raise SpeechUnavailable("ElevenLabs returned an unreadable transcript") from None
        if not isinstance(text, str):
            raise SpeechUnavailable("ElevenLabs returned an unreadable transcript")
        return text.strip()


class ElevenLabsTextToSpeech:
    def synthesize(self, text: str, language: str) -> tuple[bytes, str]:
        api_key = _api_key()
        voice_id = settings.elevenlabs_voice_id
        if not voice_id:
            raise SpeechUnavailable("ElevenLabs voice is not configured")
        # language_code is only accepted on Turbo/Flash v2.5; multilingual v2 detects it from the text.
        body = {"text": text, "model_id": settings.elevenlabs_tts_model}
        request = urllib.request.Request(
            TTS_URL.format(voice_id=voice_id),
            data=json.dumps(body).encode("utf-8"),
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        return _send(request), "audio/mpeg"


def get_speech_to_text() -> SpeechToText:
    return ElevenLabsSpeechToText()


def get_text_to_speech() -> TextToSpeech:
    return ElevenLabsTextToSpeech()
