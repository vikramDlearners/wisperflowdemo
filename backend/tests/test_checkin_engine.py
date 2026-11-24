"""Parent check-in engine: greeting, health answer, due medicines, appointments, family alerts."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.activity import ActivityLog
from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.models.checkin import ChatMessage, HealthCheckin
from app.models.dose import MedicineDose
from app.models.medicine import Medicine
from app.models.notification import Notification
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.models.prescription_scan import MedicineReminder
from app.models.role import Role
from app.models.user import User
from app.services import checkin as engine
from app.services import doses as doses_svc
from app.services import families as families_svc
from app.services.parent_context import resolve_parent
from app.services.replies import TEMPLATES, reply, reply_list, shows_photos, spoken

from tests.test_parent_invites import email, family_setup  # noqa: F401

# 08:30 IST on 2026-11-22 == 03:00 UTC
NOW = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)
SETUP_AT = datetime(2026, 11, 1, tzinfo=timezone.utc)
# The profile exists from the start of the test day (00:00 IST), so no "No check-in" summary for the day before.
PROFILE_AT = datetime(2026, 11, 21, 18, 30, tzinfo=timezone.utc)
MEDS_LIST = "You have 2 medicine(s) now:\n• Amlodipine\n• Metformin\nDid you take them?"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "intent_mode", "offline_rules")


@pytest.fixture(autouse=True)
def no_meal_questions(monkeypatch):
    """These tests are about health, medicines and appointments; the meal question is tested in test_meals.py."""
    monkeypatch.setattr(engine, "meals_due", lambda *args, **kwargs: [])


def _role(db, family_id, name):
    return db.execute(select(Role).where(Role.family_id == family_id, Role.name == name)).scalar_one()


@pytest.fixture()
def world(db_session, family_setup):
    s = family_setup
    caregiver_role = _role(db_session, s["family_id"], "Caregiver")
    caregiver = families_svc.add_member(
        db_session, s["manager"].id, s["family_id"], "carer@example.com", caregiver_role.id, "Carer Doe"
    )
    parent = db_session.get(User, s["membership"].user_id)
    profile = CareProfile(
        family_id=s["family_id"], display_name="Amma", greeting_name="Amma",
        preferred_language="en", timezone="Asia/Kolkata", linked_user_id=parent.id, created_at=PROFILE_AT,
    )
    db_session.add(profile)
    db_session.add(ParentOnboardingProfile(user_id=s["manager"].id, caregiver_phone="+91 98765 43210"))
    db_session.commit()
    meds = []
    for i, name in enumerate(("Amlodipine", "Metformin")):
        # Set up well before the test day, so every 08:00 slot counts (missed-dose alerts ignore earlier slots).
        m = Medicine(care_profile_id=profile.id, display_name=name, active=True,
                     created_at=SETUP_AT + timedelta(minutes=i))
        db_session.add(m)
        db_session.commit()
        db_session.add(MedicineReminder(medicine_id=m.id, time_of_day="08:00", active=True, created_at=SETUP_AT))
        db_session.commit()
        meds.append(m)
    ctx = resolve_parent(db_session, parent)
    member_ids = {s["manager"].id, caregiver.user_id, s["caregiver_membership"].user_id}
    return {**s, "ctx": ctx, "profile": profile, "meds": meds, "parent": parent, "member_ids": member_ids}


def test_start_greets_and_asks_health(db_session, world):
    turn = engine.start_or_resume(db_session, world["ctx"], NOW)
    assert turn.bot_messages == ["Good morning, Amma!", "How are you feeling today?"]
    assert turn.checkin.step == "health"
    assert turn.checkin.checkin_date == date(2026, 11, 22)
    msgs = db_session.execute(select(ChatMessage)).scalars().all()
    assert [m.sender for m in msgs] == ["bot", "bot"]


def test_second_start_same_day_no_new_row(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.start_or_resume(db_session, world["ctx"], NOW)
    assert len(db_session.execute(select(HealthCheckin)).scalars().all()) == 1
    # A resume never greets again or repeats the question.
    assert turn.bot_messages == []
    assert turn.checkin.step == "health"
    assert len(db_session.execute(select(ChatMessage)).scalars().all()) == 2


def test_greeting_by_local_hour(db_session, world):
    # 14:00 IST == 08:30 UTC; 19:00 IST == 13:30 UTC
    t = engine.start_or_resume(db_session, world["ctx"], datetime(2026, 11, 22, 8, 30, tzinfo=timezone.utc))
    assert t.bot_messages[0] == "Good afternoon, Amma!"
    # The next day's first check-in at 19:00 IST (13:30 UTC).
    t = engine.start_or_resume(db_session, world["ctx"], datetime(2026, 11, 23, 13, 30, tzinfo=timezone.utc))
    assert t.bot_messages[0] == "Good evening, Amma!"


def test_feeling_well_gets_only_a_thank_you(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I am feeling good.", NOW)
    assert turn.bot_messages[0] == "Thank you for telling me."
    # The family still gets the update.
    assert db_session.execute(select(Notification).where(Notification.type == "checkin.update")).scalars().all()


def test_health_answer_saved_and_medicines_listed(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "my knee hurts", NOW)
    assert turn.checkin.health_text == "my knee hurts"
    assert turn.checkin.urgent is False
    assert turn.urgent is False and turn.call_number is None
    assert turn.checkin.step == "medicines"
    assert turn.bot_messages[0] == (
        "Thank you for telling me. I've shared it with Carer Doe, Manager and Viewer Doe."
    )
    assert turn.bot_messages[-1] == MEDS_LIST
    updates = db_session.execute(select(Notification).where(Notification.type == "checkin.update")).scalars().all()
    assert {n.recipient_user_id for n in updates} == world["member_ids"]
    parent_msgs = db_session.execute(select(ChatMessage).where(ChatMessage.sender == "parent")).scalars().all()
    assert [m.text for m in parent_msgs] == ["my knee hurts"]
    actions = db_session.execute(select(ActivityLog).where(ActivityLog.action == "checkin.updated")).scalars().all()
    assert sorted(a.metadata_json["step"] for a in actions) == ["health", "medicines"]
    assert {(a.object_type, a.object_id, a.actor_id) for a in actions} == {
        ("health_checkin", turn.checkin.id, world["parent"].id)
    }


def test_urgent_alerts_every_member(db_session, world, email):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I fell", NOW)
    assert turn.checkin.urgent is True and turn.urgent is True
    assert turn.call_number == "+91 98765 43210"
    assert turn.bot_messages[0] == (
        "I've alerted Carer Doe, Manager and Viewer Doe right now. You can also call them using the button below."
    )
    assert turn.bot_messages[-1] == MEDS_LIST
    urgent = db_session.execute(select(Notification).where(Notification.type == "checkin.urgent")).scalars().all()
    assert {n.recipient_user_id for n in urgent} == world["member_ids"]
    assert len(urgent) == 3
    assert sorted(to for to, _, _ in email.sent) == ["carer@example.com", "manager@example.com", "viewer@example.com"]
    assert {subject for _, subject, _ in email.sent} == {"Needs attention now: Amma"}


def test_call_number_falls_back_to_doctor(db_session, world):
    row = db_session.execute(select(ParentOnboardingProfile)).scalar_one()
    row.caregiver_phone = None
    row.doctor_contact_number = "044 1234"
    db_session.commit()
    assert engine.call_number(db_session, world["ctx"]) == "044 1234"


def test_full_flow_medicines_then_appointment_then_goodbye(db_session, world):
    db_session.add(Appointment(
        family_id=world["family_id"], care_profile_id=world["profile"].id,
        scheduled_date=date(2026, 11, 23), start_time="10:00", provider="Dr. Rao",
        reason="Doctor follow-up", status="scheduled",
    ))
    db_session.add(Appointment(
        family_id=world["family_id"], care_profile_id=world["profile"].id,
        scheduled_date=date(2026, 11, 23), start_time="15:00", provider="Dr. X",
        reason="Cancelled visit", status="cancelled",
    ))
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "my knee hurts", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "yes took both", NOW)
    doses = db_session.execute(select(MedicineDose)).scalars().all()
    assert len(doses) == 2 and {d.status for d in doses} == {"taken"}
    assert turn.bot_messages[0] == "Okay, I've noted that you took Amlodipine, Metformin at 8:30 AM."
    assert any(m.startswith("Tomorrow at 10:00 AM you have Doctor follow-up with Dr. Rao") for m in turn.bot_messages)
    assert not any("Cancelled visit" in m for m in turn.bot_messages)
    assert turn.checkin.step == "note"
    assert turn.bot_messages[-1] == "Is there anything you would like to tell me or note down?"


def test_done_step_appends_and_shares(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "my knee hurts", NOW)
    engine.handle_parent_text(db_session, world["ctx"], "yes", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I slept badly", NOW)
    assert turn.checkin.step == "done"
    assert "my knee hurts" in turn.checkin.health_text and "I slept badly" in turn.checkin.health_text
    assert turn.bot_messages[-1] == "Take care, Amma. Talk to you soon!"
    updates = db_session.execute(select(Notification).where(Notification.type == "checkin.update")).scalars().all()
    assert len(updates) == 6


def test_resume_in_medicines_asks_reminder_dose_not_yet_asked(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    engine.handle_parent_text(db_session, world["ctx"], "remind me later", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "remind me in 10 minutes", NOW)
    assert turn.bot_messages == ["I'll remind you in 10 minutes.", "Did you take Metformin?"]
    # Amlodipine's reminder is due and it has not been asked since the parent's last message.
    turn = engine.start_or_resume(db_session, world["ctx"], NOW + timedelta(minutes=11))
    assert turn.bot_messages == [MEDS_LIST]
    assert engine.start_or_resume(db_session, world["ctx"], NOW + timedelta(minutes=12)).bot_messages == []


def test_unclear_asks_first_medicine_then_answer_applies_to_it(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "remind me later", NOW)
    assert turn.bot_messages == ["Did you take Amlodipine?"]
    assert turn.checkin.step == "medicines"
    turn = engine.handle_parent_text(db_session, world["ctx"], "remind me in 10 minutes", NOW)
    assert turn.bot_messages == ["I'll remind you in 10 minutes.", "Did you take Metformin?"]
    turn = engine.handle_parent_text(db_session, world["ctx"], "yes", NOW)
    assert turn.checkin.step == "note"
    rows = {d.medicine_id: d for d in db_session.execute(select(MedicineDose)).scalars()}
    assert rows[world["meds"][0].id].remind_at is not None
    assert rows[world["meds"][1].id].status == "taken"


def test_finished_alerts_family(db_session, world, email):
    world["meds"][1].active = False
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "it ran out", NOW)
    assert turn.bot_messages[0] == "I've told Carer Doe, Manager and Viewer Doe that Amlodipine has run out."
    rows = db_session.execute(select(Notification).where(Notification.type == "medicine.finished")).scalars().all()
    assert {n.recipient_user_id for n in rows} == world["member_ids"]
    assert len(email.sent) == 3
    assert turn.checkin.step == "note"
    dose = db_session.execute(select(MedicineDose)).scalar_one()
    assert dose.status == "skipped"
    # Later the same day it is never asked again and the family is not alerted twice.
    later = engine.start_or_resume(db_session, world["ctx"], NOW + timedelta(hours=2))
    assert later.bot_messages == []
    rows = db_session.execute(select(Notification).where(Notification.type == "medicine.finished")).scalars().all()
    assert len(rows) == 3 and len(email.sent) == 3


def test_no_medicines_due_says_none_and_skips_skipped(db_session, world):
    doses_svc.record_dose(db_session, world["profile"], world["meds"][0].id, "08:00", "skipped",
                          world["manager"].id, "manual", NOW)
    doses_svc.record_dose(db_session, world["profile"], world["meds"][1].id, "08:00", "taken",
                          world["manager"].id, "manual", NOW)
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    assert "You have no medicines due right now." in turn.bot_messages
    assert turn.checkin.step == "note"


def test_resume_in_medicines_step_recomputes(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    doses_svc.record_dose(db_session, world["profile"], world["meds"][0].id, "08:00", "taken",
                          world["manager"].id, "manual", NOW)
    # Metformin was already asked about since the parent's last message, so nothing new is stored.
    turn = engine.start_or_resume(db_session, world["ctx"], NOW)
    assert turn.bot_messages == []
    assert turn.checkin.step == "medicines"
    turn = engine.handle_parent_text(db_session, world["ctx"], "yes", NOW)
    assert turn.checkin.step == "note"


def test_tamil_profile_greets_in_tamil(db_session, world):
    world["profile"].preferred_language = "ta"
    db_session.commit()
    ctx = resolve_parent(db_session, world["parent"])
    turn = engine.start_or_resume(db_session, ctx, NOW)
    assert turn.bot_messages[0] == reply("greet_morning", "ta", name="Amma")
    assert turn.bot_messages[0] != "Good morning, Amma!"
    msg = db_session.execute(select(ChatMessage)).scalars().first()
    assert msg.language == "ta"


def test_replies_fall_back_to_english_and_keep_placeholders():
    from app.services import replies as r

    assert reply("goodbye", "xx", name="Amma") == "Take care, Amma. Talk to you soon!"
    for lang in ("ta", "hi", "te", "ml", "kn"):
        for key, english in r.TEMPLATES["en"].items():
            translated = r.TEMPLATES[lang].get(key)
            assert translated, (lang, key)
            assert sorted(r._fields(translated)) == sorted(r._fields(english)), (lang, key)


def test_time_12_hour():
    assert engine.format_time("10:00") == "10:00 AM"
    assert engine.format_time("14:30") == "2:30 PM"
    assert engine.format_time("00:05") == "12:05 AM"
    assert engine.format_time("12:00") == "12:00 PM"


def _steps(db):
    return [a.metadata_json["step"] for a in db.execute(
        select(ActivityLog).where(ActivityLog.action == "checkin.updated")).scalars()]


def test_remind_later_dose_asked_again_after_done(db_session, world):
    world["meds"][1].active = False
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "remind me in 10 minutes", NOW)
    assert turn.bot_messages[0] == "I'll remind you in 10 minutes."
    assert turn.checkin.step == "note"
    # Before the reminder time nothing is due.
    early = engine.start_or_resume(db_session, world["ctx"], NOW + timedelta(minutes=5))
    assert early.bot_messages == []
    turn = engine.start_or_resume(db_session, world["ctx"], NOW + timedelta(minutes=11))
    assert turn.bot_messages == ["Did you take Amlodipine?"]
    assert turn.checkin.step == "medicines"
    assert _steps(db_session).count("medicines") == 2
    again = engine.start_or_resume(db_session, world["ctx"], NOW + timedelta(minutes=11))
    assert again.bot_messages == []
    turn = engine.handle_parent_text(db_session, world["ctx"], "yes", NOW + timedelta(minutes=12))
    assert turn.checkin.step == "note"
    assert db_session.execute(select(MedicineDose)).scalar_one().status == "taken"


def test_evening_dose_asked_after_morning_done(db_session, world):
    evening = Medicine(care_profile_id=world["profile"].id, display_name="Atorvastatin", active=True)
    db_session.add(evening)
    db_session.commit()
    db_session.add(MedicineReminder(medicine_id=evening.id, time_of_day="20:00", active=True))
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "yes took both", NOW)
    assert turn.checkin.step == "note"
    # 20:30 IST == 15:00 UTC
    turn = engine.start_or_resume(db_session, world["ctx"], datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc))
    assert turn.bot_messages == ["Did you take Atorvastatin?"]
    assert turn.checkin.step == "medicines"


def test_evening_dose_asked_in_done_turn_and_text_still_shared(db_session, world):
    evening = Medicine(care_profile_id=world["profile"].id, display_name="Atorvastatin", active=True)
    db_session.add(evening)
    db_session.commit()
    db_session.add(MedicineReminder(medicine_id=evening.id, time_of_day="20:00", active=True))
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    engine.handle_parent_text(db_session, world["ctx"], "yes", NOW)
    evening_now = datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I feel tired", evening_now)
    assert turn.bot_messages[-1] == "Did you take Atorvastatin?"
    assert "I feel tired" in turn.checkin.health_text
    assert turn.checkin.step == "medicines"


def test_not_taken_not_reasked_same_exchange_but_after_30_minutes(db_session, world):
    world["meds"][1].active = False
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "not yet", NOW)
    assert turn.bot_messages[0] == "Okay, I've noted it."
    assert not any("Amlodipine" in m for m in turn.bot_messages)
    assert turn.checkin.step == "note"
    turn = engine.handle_parent_text(db_session, world["ctx"], "I slept well", NOW + timedelta(minutes=5))
    assert turn.bot_messages[-1] == "Take care, Amma. Talk to you soon!"
    turn = engine.start_or_resume(db_session, world["ctx"], NOW + timedelta(minutes=29))
    assert turn.bot_messages == []
    turn = engine.start_or_resume(db_session, world["ctx"], NOW + timedelta(minutes=30))
    assert turn.bot_messages == ["Did you take Amlodipine?"]
    assert turn.checkin.step == "medicines"


def test_record_dose_value_error_does_not_crash_or_alert(db_session, world, email, monkeypatch):
    world["meds"][1].active = False
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)

    def boom(*args, **kwargs):
        raise ValueError("Medicine is not an active medicine of this care profile")

    monkeypatch.setattr(engine, "record_dose", boom)
    turn = engine.handle_parent_text(db_session, world["ctx"], "it ran out", NOW)
    assert turn.bot_messages == ["Did you take Amlodipine?"]
    assert db_session.execute(select(Notification).where(Notification.type == "medicine.finished")).scalars().all() == []
    assert email.sent == []
    turn = engine.handle_parent_text(db_session, world["ctx"], "yes", NOW)
    assert turn.bot_messages == ["Did you take Amlodipine?"]
    assert db_session.execute(select(MedicineDose)).scalars().all() == []


# ---------- urgent words in any step ----------

URGENT_EN = "I've alerted Carer Doe, Manager and Viewer Doe right now. You can also call them using the button below."


def _urgent_notes(db):
    return db.execute(select(Notification).where(Notification.type == "checkin.urgent")).scalars().all()


def test_urgent_during_medicines_alerts_and_still_asks_the_medicine(db_session, world, email):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "my knee hurts", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "help, I fell", NOW)
    assert turn.urgent is True and turn.checkin.urgent is True
    assert turn.call_number == "+91 98765 43210"
    assert turn.bot_messages[0] == URGENT_EN
    assert turn.bot_messages[-1] == "Did you take Amlodipine?"
    assert turn.checkin.step == "medicines"
    assert len(_urgent_notes(db_session)) == 3  # one alert per member, not two
    assert {s for _, s, _ in email.sent} == {"Needs attention now: Amma"} and len(email.sent) == 3


def test_urgent_during_medicines_still_records_the_answer(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I took both but I feel dizzy", NOW)
    assert turn.bot_messages[0] == URGENT_EN
    assert "Okay, I've noted that you took Amlodipine, Metformin at 8:30 AM." in turn.bot_messages
    assert {d.status for d in db_session.execute(select(MedicineDose)).scalars()} == {"taken"}
    assert turn.checkin.step == "note"
    assert len(_urgent_notes(db_session)) == 3


def test_urgent_in_health_step_alerts_once(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "help, I fell", NOW)
    assert len(_urgent_notes(db_session)) == 3


# ---------- urgent reply never promises what is not there ----------

def test_urgent_reply_without_a_phone_number_mentions_no_button(db_session, world):
    row = db_session.execute(select(ParentOnboardingProfile)).scalar_one()
    row.caregiver_phone = None
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I fell", NOW)
    assert turn.call_number is None
    assert turn.bot_messages[0] == reply("health_urgent_no_phone", "en", family="Carer Doe, Manager and Viewer Doe")
    assert "button" not in turn.bot_messages[0]
    assert "Carer Doe" in turn.bot_messages[0]


def test_urgent_reply_with_no_family_to_alert_does_not_claim_an_alert(db_session, world):
    from app.models.membership import FamilyMember

    for m in db_session.execute(select(FamilyMember)).scalars():
        if m.user_id != world["parent"].id:
            m.status = "removed"
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I fell", NOW)
    assert turn.call_number is None
    assert turn.bot_messages[0] == reply("health_urgent_alone", "en")
    assert "alerted" not in turn.bot_messages[0]
    assert _urgent_notes(db_session) == []


@pytest.mark.parametrize("language", ["en", "ta", "hi", "te", "ml", "kn"])
def test_urgent_variants_translated(language):
    from app.services.replies import TEMPLATES

    for key in ("health_urgent", "health_urgent_no_phone", "health_urgent_alone", "health_urgent_call_only"):
        assert key in TEMPLATES[language], (language, key)


# ---------- closings after "done" are not health news ----------

@pytest.mark.parametrize("closing", ["ok", "Okay, bye!", "thank you", "Thanks", "நன்றி", "धन्यवाद", "ठीक है", "no"])
def test_done_step_closing_is_not_shared(db_session, world, closing):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "my knee hurts", NOW)
    engine.handle_parent_text(db_session, world["ctx"], "yes", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], closing, NOW)
    assert turn.checkin.step == "done"
    assert turn.checkin.health_text == "my knee hurts"
    assert turn.bot_messages == ["Take care, Amma. Talk to you soon!"]
    updates = db_session.execute(select(Notification).where(Notification.type == "checkin.update")).scalars().all()
    assert len(updates) == 3  # only the first health answer


# ---------- message order does not depend on the database ----------

def test_messages_get_a_sequence_number_per_checkin(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "my knee hurts", NOW)
    msgs = engine.conversation(db_session, engine._today(db_session, world["ctx"], NOW))
    assert [m.seq for m in msgs] == list(range(1, len(msgs) + 1))
    assert [m.sender for m in msgs][:3] == ["bot", "bot", "parent"]


def test_conversation_orders_by_sequence_not_insert_order(db_session, world):
    turn = engine.start_or_resume(db_session, world["ctx"], NOW)
    same_time = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)
    for m in db_session.execute(select(ChatMessage)).scalars():
        db_session.delete(m)
    db_session.commit()
    # Inserted in reverse order with one timestamp: only seq can tell the order.
    for seq, text in ((3, "third"), (2, "second"), (1, "first")):
        db_session.add(ChatMessage(checkin_id=turn.checkin.id, sender="bot", text=text, language="en",
                                   created_at=same_time, seq=seq))
    db_session.commit()
    assert [m.text for m in engine.conversation(db_session, turn.checkin)] == ["first", "second", "third"]


def test_indexes_for_dose_and_message_lookups():
    assert "ix_chat_messages_checkin_id" in {i.name for i in ChatMessage.__table__.indexes}
    assert "ix_medicine_doses_profile_date" in {i.name for i in MedicineDose.__table__.indexes}


def test_is_closing_only_for_pure_closings():
    assert engine.is_closing("ok, bye. Thank you!") is True
    assert engine.is_closing("சரி நன்றி") is True
    assert engine.is_closing("yes") is False  # "anything else?" -> "yes" means more is coming
    assert engine.is_closing("ok but my knee hurts") is False
    assert engine.is_closing("") is False


# ---------- round 2 ----------

def test_racing_dose_insert_keeps_the_turn_state(db_session, world, email, monkeypatch):
    """A dose row created by another request mid-turn must not undo this turn's urgent alert or messages."""
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    amlodipine, _ = world["meds"]
    # Another request (e.g. the missed-dose job) has written Amlodipine's row; this turn does not see it at first.
    db_session.add(MedicineDose(
        family_id=world["family_id"], care_profile_id=world["profile"].id, medicine_id=amlodipine.id,
        dose_date=date(2026, 11, 22), slot="08:00", status="missed", source="system", recorded_at=NOW,
    ))
    db_session.commit()
    real = doses_svc._existing
    seen = []

    def stale_once(db, medicine_id, day, slot):
        if medicine_id == amlodipine.id and not seen:
            seen.append(1)
            return None
        return real(db, medicine_id, day, slot)

    monkeypatch.setattr(doses_svc, "_existing", stale_once)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I took both but I feel dizzy", NOW)
    assert seen  # the race happened
    db_session.expire_all()
    checkin = db_session.get(HealthCheckin, turn.checkin.id)
    assert checkin.urgent is True
    assert "I feel dizzy" in (checkin.health_text or "")
    assert len(_urgent_notes(db_session)) == 3
    parent_texts = [m.text for m in engine.conversation(db_session, checkin) if m.sender == "parent"]
    assert parent_texts[-1] == "I took both but I feel dizzy"
    rows = db_session.execute(select(MedicineDose)).scalars().all()
    assert len(rows) == 2 and {r.status for r in rows} == {"taken"}


def _without_family(db, world):
    from app.models.membership import FamilyMember

    for m in db.execute(select(FamilyMember)).scalars():
        if m.user_id != world["parent"].id:
            m.status = "removed"
    db.commit()


def test_health_noted_without_family_does_not_claim_sharing(db_session, world):
    _without_family(db_session, world)
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "my knee hurts", NOW)
    assert turn.bot_messages[0] == reply("health_noted_alone", "en")
    assert "shared" not in turn.bot_messages[0] and "family" not in turn.bot_messages[0]


def test_meds_finished_without_family_does_not_claim_telling(db_session, world):
    _without_family(db_session, world)
    world["meds"][1].active = False
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "fine", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "it ran out", NOW)
    assert turn.bot_messages[0] == reply("meds_finished_alone", "en", name="Amlodipine")
    assert "told" not in turn.bot_messages[0]


@pytest.mark.parametrize("language", ["en", "ta", "hi", "te", "ml", "kn"])
def test_alone_variants_translated(language):
    from app.services.replies import TEMPLATES

    for key in ("health_ok", "health_noted_alone", "meds_finished_alone"):
        assert key in TEMPLATES[language], (language, key)


# ---------- "which medicine do I take?" questions ----------

def _add_evening_dose(db, world):
    db.add(MedicineReminder(medicine_id=world["meds"][1].id, time_of_day="20:00", active=True, created_at=SETUP_AT))
    db.commit()


def test_medicine_question_in_health_step_answers_schedule_and_is_not_shared(db_session, world):
    _add_evening_dose(db_session, world)
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(
        db_session, world["ctx"], "What medicine do I need to take now or in the night?", NOW
    )
    assert turn.bot_messages == [
        "Now:\n• Amlodipine\n• Metformin",
        "At 8:00 PM: Metformin.",
        "How are you feeling today?",
    ]
    assert turn.checkin.step == "health"
    assert turn.checkin.health_text is None
    notes = db_session.execute(select(Notification)).scalars().all()
    assert notes == []
    assert db_session.execute(select(MedicineDose)).scalars().all() == []


def test_medicine_question_in_medicines_step_records_nothing_and_asks_again(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "I am fine", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "which tablets should I take?", NOW)
    assert turn.bot_messages == ["Now:\n• Amlodipine\n• Metformin", MEDS_LIST]
    assert turn.checkin.step == "medicines"
    assert db_session.execute(select(MedicineDose)).scalars().all() == []


def test_medicine_question_after_done_lists_taken_and_later(db_session, world):
    _add_evening_dose(db_session, world)
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "I am fine", NOW)
    engine.handle_parent_text(db_session, world["ctx"], "yes I took both", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "when is my next medicine?", NOW)
    assert turn.bot_messages == [
        "Already taken today:\n• Amlodipine\n• Metformin",
        "At 8:00 PM: Metformin.",
        "Is there anything you would like to tell me or note down?",
    ]
    assert turn.checkin.step == "note"
    assert "next medicine" not in (turn.checkin.health_text or "")


def test_medicine_question_with_everything_taken(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "I am fine", NOW)
    engine.handle_parent_text(db_session, world["ctx"], "yes I took both", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "what medicines do I have today?", NOW)
    assert turn.bot_messages[0] == "Already taken today:\n• Amlodipine\n• Metformin"
    assert turn.bot_messages[1] == "You've taken all your medicines for today."


def test_medicine_question_with_no_medicines(db_session, world):
    for m in world["meds"]:
        m.active = False
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "what tablets do I take?", NOW)
    assert turn.bot_messages[0] == "You don't have any medicines on your list."


def test_medicine_question_shows_instructions(db_session, world):
    world["meds"][0].instructions_text = "After breakfast"
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "which medicine now?", NOW)
    assert turn.bot_messages[0] == "Now:\n• Amlodipine (After breakfast)\n• Metformin"


def test_urgent_question_is_still_urgent(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I fell, which medicine should I take?", NOW)
    assert turn.urgent is True


@pytest.mark.parametrize("language", ["en", "ta", "hi", "te", "ml", "kn"])
def test_schedule_replies_translated(language):
    from app.services.replies import TEMPLATES
    for key in ("sched_now", "sched_at", "sched_anytime", "sched_taken", "sched_all_done", "sched_none"):
        assert key in TEMPLATES[language]


# ---------- "I took my medicine": how many, which dose, and when ----------

def test_medicine_lists_are_bulleted_in_every_language_and_read_as_a_sentence():
    for lang in TEMPLATES:
        for key in ("meds_list", "meds_how_many", "meds_which", "sched_now", "sched_at", "sched_anytime", "sched_taken"):
            text = reply_list(key, lang, ["A", "B"], count=2, time="8:00 PM")
            assert "\n• A\n• B" in text, (lang, key)
            assert "•" not in spoken(text) and "\n" not in spoken(text)
    assert spoken(MEDS_LIST) == "You have 2 medicine(s) now: Amlodipine, Metformin. Did you take them?"


HOW_MANY_Q = ("How many of your 2 medicines did you take?\n• Amlodipine\n• Metformin\n"
              "You can say all of them, or tell me which ones.")
# 19:45 IST == 14:15 UTC
EVENING_NOW = datetime(2026, 11, 22, 14, 15, tzinfo=timezone.utc)


def _to_medicines_step(db, world, when=NOW):
    engine.start_or_resume(db, world["ctx"], when)
    engine.handle_parent_text(db, world["ctx"], "I am fine", when)


def _doses(db):
    return {(d.medicine_id, d.slot): d.status for d in db.execute(select(MedicineDose)).scalars()}


def test_took_medicine_asks_how_many_and_records_nothing_yet(db_session, world):
    _to_medicines_step(db_session, world)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I took my medicine", NOW)
    assert turn.bot_messages == [HOW_MANY_Q]
    assert _doses(db_session) == {}


def test_how_many_all_records_both_with_the_time(db_session, world):
    _to_medicines_step(db_session, world)
    engine.handle_parent_text(db_session, world["ctx"], "I took my medicine", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "both", NOW)
    assert turn.bot_messages[0] == "Okay, I've noted that you took Amlodipine, Metformin at 8:30 AM."
    a, m = world["meds"]
    assert _doses(db_session) == {(a.id, "08:00"): "taken", (m.id, "08:00"): "taken"}


def test_how_many_one_then_which(db_session, world):
    _to_medicines_step(db_session, world)
    engine.handle_parent_text(db_session, world["ctx"], "I took my medicine", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "only one", NOW)
    assert turn.bot_messages == ["Which ones did you take?\n• Amlodipine\n• Metformin"]
    turn = engine.handle_parent_text(db_session, world["ctx"], "Metformin", NOW)
    assert turn.bot_messages == ["Okay, I've noted that you took Metformin at 8:30 AM.", "Did you take Amlodipine?"]
    a, m = world["meds"]
    assert _doses(db_session) == {(m.id, "08:00"): "taken"}


def test_naming_one_medicine_records_only_that_one(db_session, world):
    _to_medicines_step(db_session, world)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I took the Amlodipine", NOW)
    assert turn.bot_messages == ["Okay, I've noted that you took Amlodipine at 8:30 AM.", "Did you take Metformin?"]


def test_how_many_none_is_not_taken(db_session, world):
    _to_medicines_step(db_session, world)
    engine.handle_parent_text(db_session, world["ctx"], "I took my medicine", NOW)
    engine.handle_parent_text(db_session, world["ctx"], "none", NOW)
    assert set(_doses(db_session).values()) == {"not_taken"}


def test_how_many_unclear_asks_again(db_session, world):
    _to_medicines_step(db_session, world)
    engine.handle_parent_text(db_session, world["ctx"], "I took my medicine", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "hmm", NOW)
    assert turn.bot_messages == ["Sorry, I didn't catch that. Could you say it again?", HOW_MANY_Q]


def test_bare_yes_to_the_list_means_all(db_session, world):
    _to_medicines_step(db_session, world)
    turn = engine.handle_parent_text(db_session, world["ctx"], "yes", NOW)
    assert turn.bot_messages[0] == "Okay, I've noted that you took Amlodipine, Metformin at 8:30 AM."


def test_evening_report_marks_only_the_night_dose_for_medicines_without_times(db_session, world):
    for r in db_session.execute(select(MedicineReminder)).scalars():
        r.active = False
    db_session.commit()
    a, m = world["meds"]
    # Morning: both taken (morning dose).
    _to_medicines_step(db_session, world)
    engine.handle_parent_text(db_session, world["ctx"], "yes took both", NOW)
    assert _doses(db_session) == {(a.id, "morning"): "taken", (m.id, "morning"): "taken"}
    # Evening, after the check-in finished: "I took my medicine" asks how many, then records the night dose.
    turn = engine.handle_parent_text(db_session, world["ctx"], "I took my evening tablets", EVENING_NOW)
    assert turn.bot_messages == [HOW_MANY_Q]
    turn = engine.handle_parent_text(db_session, world["ctx"], "all", EVENING_NOW)
    assert turn.bot_messages == [
        "Okay, I've noted that you took Amlodipine, Metformin at 7:45 PM.",
        "Is there anything else you'd like to tell me?",
    ]
    assert turn.checkin.step == "done"
    assert _doses(db_session) == {
        (a.id, "morning"): "taken", (m.id, "morning"): "taken",
        (a.id, "night"): "taken", (m.id, "night"): "taken",
    }
    assert "evening tablets" not in (turn.checkin.health_text or "")


def test_timed_evening_report_leaves_the_missed_morning_dose_alone(db_session, world):
    a, m = world["meds"]
    for med in world["meds"]:
        db_session.add(MedicineReminder(medicine_id=med.id, time_of_day="20:00", active=True,
                                        created_at=SETUP_AT))
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], EVENING_NOW)
    engine.handle_parent_text(db_session, world["ctx"], "I am fine", EVENING_NOW)
    engine.handle_parent_text(db_session, world["ctx"], "I took both", EVENING_NOW)
    # 19:45: the 20:00 doses are current (within an hour); the unanswered 08:00 doses stay unanswered.
    assert _doses(db_session) == {(a.id, "20:00"): "taken", (m.id, "20:00"): "taken"}


# ---------- medicine photos ----------

def _ask(db, world, text):
    return engine.handle_parent_text(db, world["ctx"], text, NOW)


def _to_medicines(db, world):
    engine.start_or_resume(db, world["ctx"], NOW)
    _ask(db, world, "I am feeling good.")


def test_photo_of_a_named_medicine(db_session, world):
    world["meds"][1].display_name = "Vitamin D3 60000 IU"
    world["meds"][1].image_data = b"x"
    world["meds"][1].image_content_type = "image/png"
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    before = len(db_session.execute(select(Notification)).scalars().all())
    turn = _ask(db_session, world, "Which medicine do I need to take for vitamin D3? Can you send me the photo?")
    assert turn.bot_messages == [
        "Here is the photo of Vitamin D3 60000 IU. Now: Vitamin D3 60000 IU.", "How are you feeling today?",
    ]
    # Nothing is recorded or shared.
    assert turn.checkin.step == "health" and not turn.checkin.health_text
    assert len(db_session.execute(select(Notification)).scalars().all()) == before
    assert db_session.execute(select(MedicineDose)).scalars().all() == []


OFFER = "Do you want to see the images of the medicines for reference?"


def _with_offer(db_session, world):
    world["meds"][0].image_data = b"x"
    world["meds"][0].image_content_type = "image/png"
    db_session.commit()
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = _ask(db_session, world, "I am fine")
    assert turn.bot_messages[-2:] == [MEDS_LIST, OFFER]


@pytest.mark.parametrize("answer", ["Yes", "yes please", "show me the images", "Okay", "ஆமா", "हाँ"])
def test_yes_to_the_images_shows_them_and_records_no_dose(db_session, world, answer):
    _with_offer(db_session, world)
    turn = _ask(db_session, world, answer)
    assert turn.bot_messages == [
        "Here is the photo of Amlodipine.",
        "There is no photo of Metformin yet. Please ask your family to add one.",
        MEDS_LIST,
    ]
    assert db_session.execute(select(MedicineDose)).scalars().all() == []
    # The next "yes" answers "Did you take them?".
    _ask(db_session, world, "Yes")
    assert {d.status for d in db_session.execute(select(MedicineDose)).scalars()} == {"taken"}


@pytest.mark.parametrize("answer", ["No", "no thanks", "don't show", "വേണ്ട"])
def test_no_to_the_images_records_nothing_and_asks_about_the_doses(db_session, world, answer):
    _with_offer(db_session, world)
    assert _ask(db_session, world, answer).bot_messages == [MEDS_LIST]
    assert db_session.execute(select(MedicineDose)).scalars().all() == []


@pytest.mark.parametrize("answer,status", [("Yes I took them all", "taken"), ("yes i did", "taken"),
                                           ("I did not take them", "not_taken")])
def test_a_dose_answer_to_the_images_question_is_recorded(db_session, world, answer, status):
    _with_offer(db_session, world)
    _ask(db_session, world, answer)
    assert {d.status for d in db_session.execute(select(MedicineDose)).scalars()} == {status}


def test_images_are_not_offered_without_photos_and_only_once(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    assert _ask(db_session, world, "I am fine").bot_messages[-1] == MEDS_LIST
    world["meds"][0].image_data = b"x"
    db_session.commit()
    assert OFFER in _ask(db_session, world, "Which medicines do I take?").bot_messages
    assert OFFER not in _ask(db_session, world, "Which medicines do I take?").bot_messages


def test_only_photo_here_messages_show_photos():
    for lang in TEMPLATES:
        assert shows_photos(reply("photo_here", lang, names="Dolo"))
        for key in ("photo_missing", "photo_which", "photo_offer", "meds_one", "meds_list"):
            assert not shows_photos(reply(key, lang, names="Dolo", name="Dolo", count=1)), (lang, key)


def test_photo_not_added_yet_is_said_plainly(db_session, world):
    _to_medicines(db_session, world)
    turn = _ask(db_session, world, "send me the metformin photo")
    assert turn.bot_messages[0].startswith("There is no photo of Metformin yet.")
    assert turn.bot_messages[-1] == MEDS_LIST
    assert db_session.execute(select(MedicineDose)).scalars().all() == []


def test_confused_while_asked_about_medicines_lists_them(db_session, world):
    _to_medicines(db_session, world)
    turn = _ask(db_session, world, "I'm confused")
    assert turn.bot_messages == [
        "Let me help. Here are today's medicines.", "Now:\n• Amlodipine\n• Metformin", MEDS_LIST,
    ]


def test_photo_of_a_medicine_not_on_the_list_does_not_guess(db_session, world):
    _to_medicines(db_session, world)
    turn = _ask(db_session, world, "Show me the photo of vitamin B12")
    assert turn.bot_messages[0] == "I'm not sure which medicine you mean. Here are today's medicines."


def test_confused_as_a_health_answer_reaches_the_family(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    turn = _ask(db_session, world, "I'm confused")
    assert turn.checkin.health_text == "I'm confused"
    assert "shared" in turn.bot_messages[0]
    assert turn.bot_messages[-1] == MEDS_LIST


def test_urgent_words_win_over_a_photo_request(db_session, world):
    _to_medicines(db_session, world)
    turn = _ask(db_session, world, "I fell down, send me the metformin photo")
    assert turn.urgent


@pytest.mark.parametrize("key", ["photo_here", "photo_missing"])
def test_photo_replies_name_the_medicine_in_every_language(key):
    for lang in ("en", "ta", "hi", "te", "ml", "kn"):
        assert "Dolo 650" in reply(key, lang, names="Dolo 650")
