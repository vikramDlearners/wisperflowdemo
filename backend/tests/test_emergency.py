"""The parent's Help -> "Yes, it's an emergency" button: the family is alerted at once."""

from sqlalchemy import select

from app.core.config import settings
from app.models.activity import ActivityLog
from app.models.checkin import ChatMessage
from app.models.notification import Notification
from app.services.replies import TEMPLATES

from tests.test_checkin_engine import offline, world  # noqa: F401
from tests.test_parent_api import fixed_now, no_real_tts  # noqa: F401
from tests.test_parent_invites import _auth, email, family_setup  # noqa: F401


def test_emergency_alerts_every_family_member(client, db_session, world, email):
    r = client.post("/api/parent/emergency", headers=_auth(db_session, world["parent"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["emergency_number"] == settings.emergency_number
    assert body["channels"] == ["WhatsApp", "Email", "Text message"]
    assert sorted(body["notified"]) == ["Carer Doe", "Manager", "Viewer Doe"]

    notes = db_session.execute(select(Notification).where(Notification.type == "checkin.urgent")).scalars().all()
    assert {n.recipient_user_id for n in notes} == world["member_ids"]
    assert all(n.payload["text"] == "Pressed the emergency button" for n in notes)
    # One email per family member, never to the parent.
    assert len(email.sent) == 3
    assert all("EMERGENCY" in subject for _, subject, _ in email.sent)
    assert world["parent"].email not in [to for to, _, _ in email.sent]


def test_emergency_marks_the_day_urgent_and_shows_in_the_chat(client, db_session, world, email):
    headers = _auth(db_session, world["parent"])
    client.post("/api/parent/emergency", headers=headers)
    checkin = client.get("/api/parent/checkin", headers=headers).json()
    assert checkin["call_number"] == "+91 98765 43210"  # the urgent Call button stays for the day
    assert "I've alerted your family because you pressed the emergency button." in [
        m["text"] for m in checkin["messages"]
    ]
    assert db_session.execute(
        select(ActivityLog).where(ActivityLog.action == "checkin.emergency")
    ).scalar_one_or_none() is not None


def test_emergency_twice_alerts_twice(client, db_session, world, email):
    headers = _auth(db_session, world["parent"])
    client.post("/api/parent/emergency", headers=headers)
    client.post("/api/parent/emergency", headers=headers)
    assert len(email.sent) == 6
    bot = db_session.execute(select(ChatMessage).where(ChatMessage.sender == "bot")).scalars().all()
    assert sum("emergency button" in m.text for m in bot) == 2


def test_emergency_needs_a_signed_in_parent(client, db_session, world):
    assert client.post("/api/parent/emergency").status_code == 401
    r = client.post("/api/parent/emergency", headers=_auth(db_session, world["manager"]))
    assert r.status_code in (403, 409)


def test_emergency_reply_translated():
    for language in ("en", "ta", "hi", "te", "ml", "kn"):
        assert "emergency_logged" in TEMPLATES[language]
