"""Spoken asks in the parent chat: "When is my doctor visit?" and "Call my son"."""

from datetime import date

from sqlalchemy import select

from app.models.appointment import Appointment
from app.models.membership import FamilyMember
from app.models.user import User
from app.services import checkin as engine
from app.services import parent_asks
from tests.test_checkin_engine import NOW, no_meal_questions, offline, world  # noqa: F401
from tests.test_parent_invites import email, family_setup  # noqa: F401


def _say(db, w, text):
    engine.start_or_resume(db, w["ctx"], NOW)
    return engine.handle_parent_text(db, w["ctx"], text, NOW)


def _make_son(db, w, phone):
    carer = db.execute(select(User).where(User.email == "carer@example.com")).scalar_one()
    fm = db.execute(select(FamilyMember).where(FamilyMember.user_id == carer.id)).scalar_one()
    fm.relationship = "son"
    carer.phone = phone
    db.commit()
    return carer


def _visit(db, w, day, reason="Eye check-up", status="scheduled"):
    db.add(Appointment(family_id=w["family_id"], care_profile_id=w["profile"].id, scheduled_date=day,
                       start_time="11:30", provider="Dr. Mehta", reason=reason, status=status))
    db.commit()


def test_call_my_son_puts_his_number_on_the_call_button(db_session, world):
    _make_son(db_session, world, "+91 90000 11111")
    turn = _say(db_session, world, "Please call my son")
    assert turn.bot_messages == ["Tap the green button to call Carer Doe."]
    assert turn.call_number == "+91 90000 11111"
    assert not turn.urgent


def test_call_by_first_name_uses_onboarding_phone_when_user_has_none(db_session, world):
    turn = _say(db_session, world, "phone Manager")
    assert turn.call_number == "+91 98765 43210"
    assert "Manager" in turn.bot_messages[0]


def test_call_member_without_a_number_says_so(db_session, world):
    _make_son(db_session, world, None)
    turn = _say(db_session, world, "call my son")
    assert turn.call_number is None
    assert turn.bot_messages == ["I don't have Carer Doe's number. Please ask your family to add it."]


def test_call_for_relation_no_one_has_points_to_help(db_session, world):
    turn = _say(db_session, world, "call my daughter")
    assert turn.call_number is None
    assert "Help" in turn.bot_messages[0]


def test_ordinary_sentences_are_not_call_requests(db_session, world):
    for text in ("I'll call you later", "my phone is broken", "I am fine"):
        assert parent_asks.call_ask(db_session, world["ctx"], text) is None, text


def test_tamil_call_request_finds_the_son(db_session, world):
    _make_son(db_session, world, "+91 90000 11111")
    ask = parent_asks.call_ask(db_session, world["ctx"], "மகன் கிட்ட போன் பண்ணு")
    assert ask is not None and ask.number == "+91 90000 11111"


def test_visit_question_names_the_next_booked_visit(db_session, world):
    _visit(db_session, world, date(2026, 11, 28))
    _visit(db_session, world, date(2026, 11, 25), reason="Old visit", status="cancelled")
    turn = _say(db_session, world, "When is my next doctor visit?")
    assert turn.bot_messages[0] == "On 28 Nov at 11:30 AM you have Eye check-up with Dr. Mehta."


def test_visit_tomorrow_uses_tomorrow_wording(db_session, world):
    _visit(db_session, world, date(2026, 11, 23))
    turn = _say(db_session, world, "do I have a doctor appointment?")
    assert turn.bot_messages[0].startswith("Tomorrow")


def test_no_visit_booked(db_session, world):
    turn = _say(db_session, world, "When is my doctor visit?")
    assert turn.bot_messages[0] == "You have no doctor visits booked."


def test_visit_word_without_a_question_is_not_a_visit_ask():
    assert not parent_asks.is_visit_question("The doctor said I am fine")
    assert parent_asks.is_visit_question("டாக்டர் எப்போ?")
