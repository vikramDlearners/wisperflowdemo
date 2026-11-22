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
from app.services.replies import reply

from tests.test_parent_invites import email, family_setup  # noqa: F401

# 08:30 IST on 2026-11-22 == 03:00 UTC
NOW = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)
SETUP_AT = datetime(2026, 11, 1, tzinfo=timezone.utc)
# The profile exists from the start of the test day (00:00 IST), so no "No check-in" summary for the day before.
PROFILE_AT = datetime(2026, 11, 21, 18, 30, tzinfo=timezone.utc)
MEDS_LIST = "You have 2 medicine(s) now: Amlodipine, Metformin. Did you take them?"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "intent_mode", "offline_rules")


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
    assert turn.bot_messages[0] == "Okay, I've noted it."
    assert any(m.startswith("Tomorrow at 10:00 AM you have Doctor follow-up with Dr. Rao") for m in turn.bot_messages)
    assert not any("Cancelled visit" in m for m in turn.bot_messages)
    assert turn.checkin.step == "done"
    assert turn.bot_messages[-1] == "Take care, Amma. Talk to you soon!"


def test_done_step_appends_and_shares(db_session, world):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "my knee hurts", NOW)
    engine.handle_parent_text(db_session, world["ctx"], "yes", NOW)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I slept badly", NOW)
    assert turn.checkin.step == "done"
    assert "my knee hurts" in turn.checkin.health_text and "I slept badly" in turn.checkin.health_text
    assert turn.bot_messages[-1] == "Is there anything else you'd like to tell me?"
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
    assert turn.checkin.step == "done"
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
    assert turn.checkin.step == "done"
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
    assert turn.checkin.step == "done"


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
    assert turn.checkin.step == "done"


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
    assert turn.checkin.step == "done"
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
    assert turn.checkin.step == "done"
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
    assert turn.checkin.step == "done"
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
    assert turn.checkin.step == "done"
    turn = engine.handle_parent_text(db_session, world["ctx"], "I slept well", NOW + timedelta(minutes=5))
    assert turn.bot_messages[-1] == "Is there anything else you'd like to tell me?"
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
    assert "Okay, I've noted it." in turn.bot_messages
    assert {d.status for d in db_session.execute(select(MedicineDose)).scalars()} == {"taken"}
    assert turn.checkin.step == "done"
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
