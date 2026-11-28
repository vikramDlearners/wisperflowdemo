"""The weekly family summary and the early warnings built from the same week."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.models.dose import MedicineDose
from app.models.health_note import HealthNote
from app.models.notification import Notification
from app.services import fine_checkin as fine
from app.services import weekly_summary as ws
from app.services.auth import create_auth_session

from tests.test_checkin_engine import world  # noqa: F401
from tests.test_parent_invites import email, family_setup  # noqa: F401

# 2026-11-22 is a Sunday. Asia/Kolkata is UTC+5:30, so 13:30 UTC is 19:00 local.
SUNDAY_EVENING = datetime(2026, 11, 22, 13, 30, tzinfo=timezone.utc)


def _sent(db, type_):
    return [n for n in db.execute(select(Notification).where(Notification.type == type_)).scalars()]


def _missed(db, world, day, slot="08:00"):
    db.add(MedicineDose(family_id=world["family_id"], care_profile_id=world["profile"].id,
                        medicine_id=world["meds"][0].id, dose_date=day, slot=slot, status="missed",
                        source="system", recorded_at=SUNDAY_EVENING))
    db.commit()


def _bp(db, world, when, top, bottom=90):
    db.add(HealthNote(family_id=world["family_id"], care_profile_id=world["profile"].id, kind="reading",
                      label="bp", value=f"{top}/{bottom}", value_num=top, value_num2=bottom, source="family",
                      active=True, recorded_at=when))
    db.commit()


def test_same_dose_missed_three_times_warns_once(db_session, world, email):
    for d in (18, 19, 21):
        _missed(db_session, world, date(2026, 11, d))
    assert ws.send_pattern_warnings(db_session, SUNDAY_EVENING) == 1
    warned = _sent(db_session, "pattern.warning")
    assert {n.recipient_user_id for n in warned} == world["member_ids"]
    assert "missed the 08:00 dose 3 times" in warned[0].payload["text"]
    assert email.sent
    assert ws.send_pattern_warnings(db_session, SUNDAY_EVENING + timedelta(hours=3)) == 0


def test_two_misses_are_not_a_pattern(db_session, world):
    for d in (18, 19):
        _missed(db_session, world, date(2026, 11, d))
    week = ws.build_week(db_session, world["profile"], SUNDAY_EVENING)
    assert week.missed == 2 and not week.warnings


def test_bp_rising_day_after_day(db_session, world):
    for i, top in enumerate((132, 140, 151)):
        _bp(db_session, world, SUNDAY_EVENING - timedelta(days=3 - i), top)
    kinds = [w.kind for w in ws.build_week(db_session, world["profile"], SUNDAY_EVENING).warnings]
    assert "bp_rising" in kinds


def test_bp_going_down_is_fine(db_session, world):
    for i, top in enumerate((151, 140, 132)):
        _bp(db_session, world, SUNDAY_EVENING - timedelta(days=3 - i), top)
    assert not ws.build_week(db_session, world["profile"], SUNDAY_EVENING).warnings


def test_quiet_parent_after_a_day(db_session, world):
    fine.press_fine(db_session, world["ctx"], SUNDAY_EVENING - timedelta(hours=23))
    assert not ws.build_week(db_session, world["profile"], SUNDAY_EVENING).warnings
    later = SUNDAY_EVENING + timedelta(hours=2)
    assert [w.kind for w in ws.build_week(db_session, world["profile"], later).warnings] == ["quiet"]


def test_weekly_summary_goes_once_on_sunday_evening(db_session, world, email):
    _missed(db_session, world, date(2026, 11, 20))
    assert ws.send_weekly_summaries(db_session, SUNDAY_EVENING - timedelta(minutes=1)) == 0
    assert ws.send_weekly_summaries(db_session, SUNDAY_EVENING - timedelta(days=1)) == 0
    assert ws.send_weekly_summaries(db_session, SUNDAY_EVENING) >= 1
    assert ws.send_weekly_summaries(db_session, SUNDAY_EVENING + timedelta(hours=1)) == 0
    mine = [n for n in _sent(db_session, "summary.weekly") if n.payload["care_profile_id"] == world["profile"].id]
    assert sorted(n.recipient_user_id for n in mine) == sorted(world["member_ids"])
    assert email.sent


def test_api_returns_the_week(client, db_session, world):
    _bp(db_session, world, datetime.now(timezone.utc) - timedelta(hours=1), 150)
    url = f"/api/families/{world['family_id']}/care-profiles/{world['profile'].id}/weekly-summary"
    r = client.get(url, headers={"Authorization": f"Bearer {create_auth_session(db_session, world['manager'].id)}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent_name"] == "Amma" and "BP: 150/90" in body["lines"]
    r = client.get(url, headers={"Authorization": f"Bearer {create_auth_session(db_session, world['parent'].id)}"})
    assert r.status_code in (200, 403)
