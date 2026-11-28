"""The daily "I'm fine" button: one tap tells the family; a missed day asks the parent first, then the family."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.notification import Notification
from app.services import fine_checkin as fine
from app.services.auth import create_auth_session

from tests.test_checkin_engine import world  # noqa: F401
from tests.test_parent_invites import email, family_setup  # noqa: F401

# Asia/Kolkata is UTC+5:30, so 05:30 UTC is 11:00 local.
MORNING = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)
ELEVEN = datetime(2026, 11, 22, 5, 30, tzinfo=timezone.utc)


def _sent(db, type_):
    return [n.recipient_user_id for n in db.execute(select(Notification).where(Notification.type == type_)).scalars()]


def test_tap_tells_the_family_once(db_session, world):
    fine.press_fine(db_session, world["ctx"], MORNING)
    fine.press_fine(db_session, world["ctx"], MORNING + timedelta(minutes=5))
    assert sorted(_sent(db_session, "checkin.fine")) == sorted(world["member_ids"])
    assert world["parent"].id not in _sent(db_session, "checkin.fine")


def test_nothing_before_eleven(db_session, world, email):
    assert fine.nudge_fine_checkins(db_session, ELEVEN - timedelta(minutes=1)) == 0
    assert _sent(db_session, "checkin.fine_ask") == []


def test_parent_is_asked_first_then_family_after_grace(db_session, world, email):
    assert fine.nudge_fine_checkins(db_session, ELEVEN) == 1
    assert _sent(db_session, "checkin.fine_ask") == [world["parent"].id]
    assert fine.status(db_session, world["ctx"], ELEVEN).asked
    assert _sent(db_session, "checkin.fine_missed") == []

    assert fine.nudge_fine_checkins(db_session, ELEVEN + timedelta(minutes=29)) == 0
    assert fine.nudge_fine_checkins(db_session, ELEVEN + timedelta(minutes=30)) == 1
    assert sorted(_sent(db_session, "checkin.fine_missed")) == sorted(world["member_ids"])
    assert email.sent, "the family is emailed too"
    assert fine.nudge_fine_checkins(db_session, ELEVEN + timedelta(hours=2)) == 0
    assert len(_sent(db_session, "checkin.fine_missed")) == len(world["member_ids"])


def test_tap_after_the_ask_stops_the_family_alert(db_session, world, email):
    fine.nudge_fine_checkins(db_session, ELEVEN)
    fine.press_fine(db_session, world["ctx"], ELEVEN + timedelta(minutes=10))
    assert fine.nudge_fine_checkins(db_session, ELEVEN + timedelta(hours=1)) == 0
    assert _sent(db_session, "checkin.fine_missed") == []


def test_next_day_starts_fresh(db_session, world, email):
    fine.press_fine(db_session, world["ctx"], MORNING)
    assert fine.nudge_fine_checkins(db_session, ELEVEN + timedelta(days=1)) == 1


def test_api(client, db_session, world):
    h = {"Authorization": f"Bearer {create_auth_session(db_session, world['parent'].id)}"}
    r = client.get("/api/parent/fine", headers=h)
    assert r.status_code == 200 and r.json()["fine_at"] is None
    r = client.post("/api/parent/fine", headers=h)
    assert r.status_code == 200 and r.json()["fine_at"] is not None
