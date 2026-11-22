"""Scheduled family alerts: the daily check-in summary and missed-dose alerts."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.models.appointment import Appointment
from app.models.checkin import HealthCheckin
from app.models.dose import MedicineDose
from app.models.notification import Notification
from app.services import doses as doses_svc
from app.services import family_alerts as alerts
from app.services import scheduler as scheduler_svc

from tests.test_checkin_engine import offline, world  # noqa: F401
from tests.test_parent_invites import email, family_setup  # noqa: F401

# Times are in UTC; the profile lives in Asia/Kolkata (UTC+5:30). Doses are due at 08:00 IST == 02:30 UTC.
IST_0859 = datetime(2026, 11, 22, 3, 29, tzinfo=timezone.utc)
IST_0900 = datetime(2026, 11, 22, 3, 30, tzinfo=timezone.utc)
IST_1959 = datetime(2026, 11, 22, 14, 29, tzinfo=timezone.utc)
IST_2000 = datetime(2026, 11, 22, 14, 30, tzinfo=timezone.utc)
MEMBER_EMAILS = ["carer@example.com", "manager@example.com", "viewer@example.com"]


def _checkin(db, w, day=date(2026, 11, 22), health="my knee hurts"):
    c = HealthCheckin(
        family_id=w["family_id"], care_profile_id=w["profile"].id, parent_user_id=w["parent"].id,
        checkin_date=day, step="done", health_text=health, urgent=False,
    )
    db.add(c)
    db.commit()
    return c


# ---------- daily summary ----------

def test_summary_waits_until_8pm_local(db_session, world, email):
    _checkin(db_session, world)
    alerts.send_daily_summaries(db_session, IST_1959)
    assert email.sent == []


def test_summary_sent_once_per_member_at_8pm(db_session, world, email):
    c = _checkin(db_session, world)
    amlodipine, metformin = world["meds"]
    doses_svc.record_dose(db_session, world["profile"], amlodipine.id, "08:00", "taken", world["parent"].id,
                          "chatbot", IST_0900)
    db_session.add(Appointment(
        family_id=world["family_id"], care_profile_id=world["profile"].id, scheduled_date=date(2026, 11, 23),
        start_time="10:00", provider="Dr. Rao", reason="BP check",
    ))
    db_session.commit()

    alerts.send_daily_summaries(db_session, IST_2000)
    assert sorted(to for to, _, _ in email.sent) == MEMBER_EMAILS  # never the parent
    _, subject, body = email.sent[0]
    assert subject == "Today's check-in with Amma"
    assert "my knee hurts" in body
    assert "Taken: Amlodipine (08:00)" in body
    assert "Not taken: Metformin (08:00)" in body
    assert "Dr. Rao" in body and "BP check" in body
    db_session.refresh(c)
    assert c.summary_sent_at is not None

    alerts.send_daily_summaries(db_session, IST_2000 + timedelta(minutes=30))
    assert len(email.sent) == 3


def test_yesterdays_checkin_summarised_next_morning(db_session, world, email):
    c = _checkin(db_session, world, day=date(2026, 11, 21), health="feeling fine")
    alerts.send_daily_summaries(db_session, IST_0900)
    assert len(email.sent) == 3
    assert "feeling fine" in email.sent[0][2]
    db_session.refresh(c)
    assert c.summary_sent_at is not None


# ---------- missed doses ----------

def test_missed_dose_not_alerted_before_60_minutes(db_session, world, email):
    alerts.alert_missed_doses(db_session, IST_0859)
    assert email.sent == []
    assert db_session.execute(select(Notification)).scalars().all() == []


def test_missed_dose_alerted_once(db_session, world, email):
    amlodipine, metformin = world["meds"]
    doses_svc.record_dose(db_session, world["profile"], amlodipine.id, "08:00", "taken", world["parent"].id,
                          "chatbot", IST_0859)
    alerts.alert_missed_doses(db_session, IST_0900)

    missed = db_session.execute(select(Notification).where(Notification.type == "medicine.missed")).scalars().all()
    assert {n.recipient_user_id for n in missed} == world["member_ids"]
    assert len(missed) == 3
    assert {n.payload["medicine_name"] for n in missed} == {"Metformin"}
    assert sorted(to for to, _, _ in email.sent) == MEMBER_EMAILS
    assert {s for _, s, _ in email.sent} == {"Medicine not taken: Amma - Metformin"}
    row = db_session.execute(select(MedicineDose).where(MedicineDose.medicine_id == metformin.id)).scalar_one()
    assert row.status == "not_taken" and row.source == "chatbot"
    assert row.family_alerted_at is not None

    alerts.alert_missed_doses(db_session, IST_0900 + timedelta(minutes=10))
    assert len(email.sent) == 3
    assert len(db_session.execute(select(Notification)).scalars().all()) == 3


def test_skipped_is_never_missed(db_session, world, email):
    for med in world["meds"]:
        doses_svc.record_dose(db_session, world["profile"], med.id, "08:00", "skipped", world["parent"].id,
                              "chatbot", IST_0859)
    alerts.alert_missed_doses(db_session, IST_0900)
    assert email.sent == []


def test_remind_later_moves_the_deadline(db_session, world, email):
    amlodipine, metformin = world["meds"]
    doses_svc.record_dose(db_session, world["profile"], amlodipine.id, "08:00", "taken", world["parent"].id,
                          "chatbot", IST_0859)
    # At 08:50 IST the parent asked to be reminded in 30 min -> reminder 09:20, alert from 10:20 IST.
    doses_svc.set_remind_later(db_session, world["profile"], metformin.id, "08:00", 30,
                               IST_0900 - timedelta(minutes=10))
    alerts.alert_missed_doses(db_session, IST_0900 + timedelta(minutes=79))
    assert email.sent == []
    alerts.alert_missed_doses(db_session, IST_0900 + timedelta(minutes=80))
    assert len(email.sent) == 3


# ---------- scheduler ----------

def test_scheduler_has_both_jobs_and_is_not_started():
    sched = scheduler_svc.build_scheduler()
    jobs = {j.id: j for j in sched.get_jobs()}
    assert set(jobs) == {"alert_missed_doses", "send_daily_summaries"}
    assert jobs["alert_missed_doses"].trigger.interval == timedelta(minutes=10)
    assert jobs["send_daily_summaries"].trigger.interval == timedelta(minutes=30)
    assert sched.running is False


def test_run_job_opens_and_closes_its_own_session(monkeypatch):
    seen = []

    class FakeSession:
        closed = False

        def rollback(self):
            pass

        def close(self):
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr(scheduler_svc, "SessionLocal", lambda: session)
    scheduler_svc.run_job(lambda db, now: seen.append((db, now)))
    assert seen[0][0] is session and seen[0][1].tzinfo is not None
    assert session.closed is True

    def boom(db, now):
        raise RuntimeError("x")

    scheduler_svc.run_job(boom)  # errors are logged, never raised into the scheduler thread


def test_scheduler_disabled_in_tests():
    from app.core.config import settings

    assert settings.scheduler_enabled is False
