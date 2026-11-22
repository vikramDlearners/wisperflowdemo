"""Notification summary API: a Gemini summary of the last 7 days, with a fixed message when Gemini is unavailable."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models.notification import Notification
from app.models.user import User
from app.services import notifications as notifications_svc
from app.services import understanding

from tests.test_parent_invites import _auth, family_setup  # noqa: F401

KEY = "secret-key-123"


@pytest.fixture()
def parent(db_session, family_setup):  # noqa: F811
    return db_session.get(User, family_setup["membership"].user_id)


@pytest.fixture()
def key_set(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", KEY)


def _boom(prompt):
    raise AssertionError("ask_gemini must not be called")


def _notify_now(db, parent, family_id):
    notifications_svc.notify(db, parent.id, "medicine_taken", family_id=family_id, payload={"medicine": "Amlodipine"})
    db.commit()


def test_summary_returned_from_gemini(client, db_session, family_setup, parent, key_set, monkeypatch):  # noqa: F811
    _notify_now(db_session, parent, family_setup["family_id"])
    seen = []

    def fake(prompt):
        seen.append(prompt)
        return {"summary": "ok"}

    monkeypatch.setattr(understanding, "ask_gemini", fake)
    r = client.get("/api/notifications/summary", headers=_auth(db_session, parent))
    assert r.status_code == 200
    assert r.json() == {"summary": "ok", "count": 1, "days": 7, "error": None}
    assert "medicine_taken" in seen[0] and "Amlodipine" in seen[0]


def test_no_notifications_in_window_skips_gemini(client, db_session, family_setup, parent, key_set,  # noqa: F811
                                                 monkeypatch):
    old = Notification(
        recipient_user_id=parent.id, family_id=family_setup["family_id"], type="old", payload=None,
        status="unread", created_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(old)
    db_session.commit()
    monkeypatch.setattr(understanding, "ask_gemini", _boom)
    r = client.get("/api/notifications/summary", headers=_auth(db_session, parent))
    assert r.status_code == 200
    assert r.json() == {"summary": "No notifications in the last 7 days.", "count": 0, "days": 7, "error": None}


def test_key_unset_returns_error_without_calling_gemini(client, db_session, family_setup, parent,  # noqa: F811
                                                        monkeypatch):
    _notify_now(db_session, parent, family_setup["family_id"])
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(understanding, "ask_gemini", _boom)
    r = client.get("/api/notifications/summary", headers=_auth(db_session, parent))
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] is None and body["count"] == 1
    assert body["error"] == "Summary is unavailable: the Gemini key is not configured."


def test_gemini_failure_returns_fixed_error_without_secret(client, db_session, family_setup, parent,  # noqa: F811
                                                           key_set, monkeypatch):
    _notify_now(db_session, parent, family_setup["family_id"])

    def boom(prompt):
        raise RuntimeError("Gemini request failed with HTTP status 500")

    monkeypatch.setattr(understanding, "ask_gemini", boom)
    r = client.get("/api/notifications/summary", headers=_auth(db_session, parent))
    assert r.status_code == 200
    body = r.json()
    assert body == {"summary": None, "count": 1, "days": 7, "error": "Summary is unavailable right now."}
    assert KEY not in r.text
