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

from tests.test_checkin_engine import SETUP_AT, offline, world  # noqa: F401
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
    assert row.status == "missed" and row.source == "system"
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


# ---------- one bad item never stops the run ----------

def test_one_failing_summary_does_not_stop_the_others(db_session, world, email, monkeypatch):
    bad = _checkin(db_session, world, day=date(2026, 11, 21), health="bad one")
    good = _checkin(db_session, world, health="good one")
    real = alerts._summary_body

    def flaky(db, checkin, profile):
        if checkin.id == bad.id:
            raise ValueError("broken data")
        return real(db, checkin, profile)

    monkeypatch.setattr(alerts, "_summary_body", flaky)
    alerts.send_daily_summaries(db_session, IST_2000)
    assert len(email.sent) == 3
    assert all("good one" in body for _, _, body in email.sent)
    db_session.refresh(bad)
    db_session.refresh(good)
    assert bad.summary_sent_at is None
    assert good.summary_sent_at is not None


def test_one_failing_profile_does_not_stop_missed_alerts(db_session, world, email, monkeypatch):
    from app.models.care_profile import CareProfile
    from app.models.medicine import Medicine
    from app.models.prescription_scan import MedicineReminder

    # Appa's chatbot user is the caregiver member here, so the caregiver is not emailed about Appa.
    other = CareProfile(family_id=world["family_id"], display_name="Appa", greeting_name="",
                        preferred_language="en", timezone="Asia/Kolkata", created_at=SETUP_AT,
                        linked_user_id=world["caregiver_membership"].user_id)
    db_session.add(other)
    db_session.commit()
    med = Medicine(care_profile_id=other.id, display_name="Aspirin", active=True, created_at=SETUP_AT)
    db_session.add(med)
    db_session.commit()
    db_session.add(MedicineReminder(medicine_id=med.id, time_of_day="08:00", active=True, created_at=SETUP_AT))
    db_session.commit()
    real = alerts.doses_today

    def flaky(db, profile, now):
        if profile.id == world["profile"].id:
            raise ValueError("bad timezone")
        return real(db, profile, now)

    monkeypatch.setattr(alerts, "doses_today", flaky)
    alerts.alert_missed_doses(db_session, IST_0900)
    assert {s for _, s, _ in email.sent} == {"Medicine not taken: Appa - Aspirin"}
    assert len(email.sent) == 3  # every member except Appa's own chatbot user


# ---------- missed doses: who and which slots ----------

def test_missed_dose_row_is_marked_missed_by_the_system(db_session, world, email):
    alerts.alert_missed_doses(db_session, IST_0900)
    rows = db_session.execute(select(MedicineDose)).scalars().all()
    assert len(rows) == 2
    assert {(r.status, r.source) for r in rows} == {("missed", "system")}
    assert all(r.family_alerted_at is not None and r.recorded_by_user_id is None for r in rows)


def test_parent_not_taken_answer_is_kept_when_alerted(db_session, world, email):
    amlodipine, _ = world["meds"]
    doses_svc.record_dose(db_session, world["profile"], amlodipine.id, "08:00", "not_taken", world["parent"].id,
                          "chatbot", IST_0859 - timedelta(minutes=45))
    alerts.alert_missed_doses(db_session, IST_0900)
    row = db_session.execute(select(MedicineDose).where(MedicineDose.medicine_id == amlodipine.id)).scalar_one()
    assert (row.status, row.source) == ("not_taken", "chatbot")
    assert row.family_alerted_at is not None


def test_no_missed_alerts_for_a_profile_without_a_chatbot_parent(db_session, world, email):
    world["profile"].linked_user_id = None
    db_session.commit()
    assert alerts.alert_missed_doses(db_session, IST_0900) == 0
    assert email.sent == []
    assert db_session.execute(select(Notification)).scalars().all() == []
    assert db_session.execute(select(MedicineDose)).scalars().all() == []


def test_no_missed_alert_for_a_slot_due_before_the_medicine_was_added(db_session, world, email):
    from app.models.prescription_scan import MedicineReminder

    amlodipine, metformin = world["meds"]
    # Metformin was added at 08:30 IST, after its 08:00 slot; Amlodipine's 08:00 reminder was set at 08:30 too.
    metformin.created_at = IST_0859 - timedelta(minutes=29)
    reminder = db_session.execute(
        select(MedicineReminder).where(MedicineReminder.medicine_id == amlodipine.id)
    ).scalar_one()
    reminder.created_at = IST_0859 - timedelta(minutes=29)
    db_session.commit()
    assert alerts.alert_missed_doses(db_session, IST_0900 + timedelta(hours=3)) == 0
    assert email.sent == []


def test_missed_dose_is_still_asked_and_the_parent_answer_overrides_it(db_session, world, email):
    from app.services import checkin as engine

    alerts.alert_missed_doses(db_session, IST_0900)
    later = IST_0900 + timedelta(hours=1)
    engine.start_or_resume(db_session, world["ctx"], later)
    engine.handle_parent_text(db_session, world["ctx"], "fine", later)
    turn = engine.handle_parent_text(db_session, world["ctx"], "yes took both", later)
    assert "Okay, I've noted that you took Amlodipine, Metformin at 10:00 AM." in turn.bot_messages
    rows = db_session.execute(select(MedicineDose)).scalars().all()
    assert {(r.status, r.source) for r in rows} == {("taken", "chatbot")}
    # Already alerted once: no second alert.
    sent = len(email.sent)
    alerts.alert_missed_doses(db_session, later + timedelta(hours=2))
    assert len(email.sent) == sent


def test_missed_shows_as_not_taken_in_the_summary(db_session, world, email):
    alerts.alert_missed_doses(db_session, IST_0900)
    email.sent.clear()
    _checkin(db_session, world)
    alerts.send_daily_summaries(db_session, IST_2000)
    assert "Not taken: Amlodipine (08:00), Metformin (08:00)" in email.sent[0][2]


# ---------- no double sends with several workers ----------

def test_missed_alert_not_sent_when_another_worker_claimed_the_row(db_session, world, email, monkeypatch):
    from sqlalchemy import text

    for med in world["meds"]:
        doses_svc.record_dose(db_session, world["profile"], med.id, "08:00", "not_taken", world["parent"].id,
                              "chatbot", IST_0859 - timedelta(minutes=45))
    real = alerts._members_except

    def racing(db, family_id, parent_user_id):
        # Another worker alerts the same doses after this run decided they were missed.
        db.execute(text("UPDATE medicine_doses SET family_alerted_at = '2026-11-22 03:30:00'"))
        db.commit()  # the other worker's work is committed
        return real(db, family_id, parent_user_id)

    monkeypatch.setattr(alerts, "_members_except", racing)
    assert alerts.alert_missed_doses(db_session, IST_0900) == 0
    assert email.sent == []
    assert db_session.execute(select(Notification)).scalars().all() == []


def test_missed_alert_not_sent_when_another_worker_inserted_the_row(db_session, world, email, monkeypatch):
    from sqlalchemy import text

    real = alerts._members_except

    def racing(db, family_id, parent_user_id):
        for med in world["meds"]:
            db.execute(text(
                "INSERT INTO medicine_doses (id, family_id, care_profile_id, medicine_id, dose_date, slot, status,"
                " recorded_at, source, family_alerted_at) VALUES (:id, :f, :p, :m, '2026-11-22', '08:00', 'missed',"
                " '2026-11-22 03:30:00', 'system', '2026-11-22 03:30:00')"
            ), {"id": f"other-{med.id}"[:36], "f": world["family_id"], "p": world["profile"].id, "m": med.id})
        db.commit()  # the other worker's work is committed
        return real(db, family_id, parent_user_id)

    monkeypatch.setattr(alerts, "_members_except", racing)
    assert alerts.alert_missed_doses(db_session, IST_0900) == 0
    assert email.sent == []
    assert db_session.execute(select(Notification)).scalars().all() == []


def test_summary_not_sent_when_another_worker_marked_it(db_session, world, email, monkeypatch):
    from sqlalchemy import text

    c = _checkin(db_session, world)
    real = alerts._summary_body

    def racing(db, checkin, profile):
        db.execute(text("UPDATE health_checkins SET summary_sent_at = '2026-11-22 14:30:00'"))
        db.commit()  # the other worker's work is committed
        return real(db, checkin, profile)

    monkeypatch.setattr(alerts, "_summary_body", racing)
    assert alerts.send_daily_summaries(db_session, IST_2000) == 0
    assert email.sent == []
    db_session.refresh(c)
    assert c.summary_sent_at is not None


# ---------- daily summary timing and days without a check-in ----------

IST_2329 = datetime(2026, 11, 22, 17, 59, tzinfo=timezone.utc)
IST_2330 = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)


def test_unfinished_checkin_waits_for_the_end_of_the_day(db_session, world, email):
    c = _checkin(db_session, world)
    c.step = "medicines"
    db_session.commit()
    alerts.send_daily_summaries(db_session, IST_2000)
    alerts.send_daily_summaries(db_session, IST_2329)
    assert email.sent == []
    alerts.send_daily_summaries(db_session, IST_2330)
    assert len(email.sent) == 3
    alerts.send_daily_summaries(db_session, IST_2330 + timedelta(minutes=30))
    assert len(email.sent) == 3


def test_day_without_a_checkin_still_gets_a_summary_at_the_end_of_the_day(db_session, world, email):
    alerts.send_daily_summaries(db_session, IST_2000)
    assert email.sent == []
    assert alerts.send_daily_summaries(db_session, IST_2330) == 1
    assert sorted(to for to, _, _ in email.sent) == MEMBER_EMAILS
    _, subject, body = email.sent[0]
    assert subject == "No check-in today with Amma"
    assert "No check-in today" in body
    assert "Not taken: Amlodipine (08:00), Metformin (08:00)" in body
    alerts.send_daily_summaries(db_session, IST_2330 + timedelta(minutes=30))
    alerts.send_daily_summaries(db_session, IST_0900 + timedelta(days=1))
    assert len(email.sent) == 3


def test_missed_end_of_day_tick_is_caught_up_next_day(db_session, world, email):
    # The app was down at 23:30 IST; the first tick the next morning sends yesterday's summary.
    assert alerts.send_daily_summaries(db_session, IST_0900 + timedelta(days=1)) == 1
    assert "22 Nov 2026" in email.sent[0][2]


def test_no_summary_for_a_profile_without_a_chatbot_parent(db_session, world, email):
    world["profile"].linked_user_id = None
    db_session.commit()
    assert alerts.send_daily_summaries(db_session, IST_2330) == 0
    assert email.sent == []


def test_no_summary_for_a_day_before_the_profile_existed(db_session, world, email):
    world["profile"].created_at = IST_0900 + timedelta(days=1)
    db_session.commit()
    assert alerts.send_daily_summaries(db_session, IST_0900 + timedelta(days=1)) == 0
    assert email.sent == []


def test_editing_reminder_times_later_keeps_the_earlier_slot_alert(db_session, world, email):
    from app.services.reminders import set_reminder_times

    amlodipine, metformin = world["meds"]
    doses_svc.record_dose(db_session, world["profile"], metformin.id, "08:00", "taken", world["parent"].id,
                          "chatbot", IST_0859)
    # Later the manager re-saves Amlodipine's times (08:00 kept, 20:00 added): the 08:00 reminder row is
    # recreated with a new created_at, but 08:00 existed all along, so its slot still counts.
    set_reminder_times(db_session, world["manager"].id, world["family_id"], amlodipine.id, ["08:00", "20:00"])
    assert alerts.alert_missed_doses(db_session, IST_0900) == 1
    assert {s for _, s, _ in email.sent} == {"Medicine not taken: Amma - Amlodipine"}
