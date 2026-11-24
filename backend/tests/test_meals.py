"""The chatbot asks what the parent ate (breakfast / lunch / dinner by time of day) and saves it."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.meal import MealLog
from app.services import checkin as engine
from app.services import family_alerts
from app.services.parent_context import resolve_parent
from app.services.replies import TEMPLATES

from tests.test_checkin_engine import NOW, offline, world  # noqa: F401
from tests.test_parent_invites import email, family_setup  # noqa: F401

# NOW is 08:30 IST (morning). 13:30 IST == 08:00 UTC; 20:30 IST == 15:00 UTC.
AFTERNOON = datetime(2026, 11, 22, 8, 0, tzinfo=timezone.utc)
NIGHT = datetime(2026, 11, 22, 15, 0, tzinfo=timezone.utc)
NOTE_ASK = "Is there anything you would like to tell me or note down?"


def _meals(db):
    return [(r.meals, r.text) for r in db.execute(select(MealLog).order_by(MealLog.recorded_at)).scalars()]


def _to_meal_question(db, world, when=NOW):
    engine.start_or_resume(db, world["ctx"], when)
    engine.handle_parent_text(db, world["ctx"], "I am fine", when)
    return engine.handle_parent_text(db, world["ctx"], "yes", when)


def test_morning_asks_about_breakfast_after_medicines(db_session, world):
    turn = _to_meal_question(db_session, world)
    assert turn.bot_messages[-1] == "What did you have for breakfast today?"
    assert turn.checkin.step == "meals"


def test_answer_is_saved_then_the_conversation_finishes(db_session, world):
    _to_meal_question(db_session, world)
    turn = engine.handle_parent_text(db_session, world["ctx"], "Two idlis and coffee", NOW)
    assert turn.bot_messages[0] == "Thank you, I've noted what you ate."
    assert turn.bot_messages[-1] == NOTE_ASK
    assert turn.checkin.step == "note"
    assert _meals(db_session) == [("breakfast", "Two idlis and coffee")]
    # The meal answer is not a health note and is not shared as one.
    assert "idli" not in (turn.checkin.health_text or "")


def test_afternoon_asks_about_breakfast_and_lunch(db_session, world):
    turn = _to_meal_question(db_session, world, AFTERNOON)
    assert turn.bot_messages[-1] == "What did you have for breakfast and lunch today?"


def test_night_with_nothing_told_asks_about_the_whole_day(db_session, world):
    turn = _to_meal_question(db_session, world, NIGHT)
    assert turn.bot_messages[-1] == "What did you have for breakfast, lunch and dinner today?"
    engine.handle_parent_text(db_session, world["ctx"], "Dosa, rice and sambar, chapati", NIGHT)
    assert _meals(db_session) == [("breakfast,lunch,dinner", "Dosa, rice and sambar, chapati")]


def test_night_after_breakfast_was_told_asks_only_the_rest(db_session, world):
    _to_meal_question(db_session, world)
    engine.handle_parent_text(db_session, world["ctx"], "Idli", NOW)
    # Opening the chat at night asks about lunch and dinner, once.
    turn = engine.start_or_resume(db_session, world["ctx"], NIGHT)
    assert turn.bot_messages[-1] == "What did you have for lunch and dinner today?"
    again = engine.start_or_resume(db_session, world["ctx"], NIGHT)
    assert again.bot_messages == []
    engine.handle_parent_text(db_session, world["ctx"], "Rice and curd, then soup", NIGHT)
    assert _meals(db_session) == [("breakfast", "Idli"), ("lunch,dinner", "Rice and curd, then soup")]


def test_nothing_more_to_ask_once_all_meals_are_told(db_session, world):
    _to_meal_question(db_session, world, NIGHT)
    engine.handle_parent_text(db_session, world["ctx"], "Everything as usual", NIGHT)
    assert engine.start_or_resume(db_session, world["ctx"], NIGHT).bot_messages == []


def test_urgent_message_in_the_meal_step_alerts_and_asks_again(db_session, world, email):
    _to_meal_question(db_session, world)
    turn = engine.handle_parent_text(db_session, world["ctx"], "I fell down", NOW)
    assert turn.urgent is True
    assert turn.bot_messages[-1] == "What did you have for breakfast today?"
    assert _meals(db_session) == []


def test_medicine_question_in_the_meal_step_then_meal_again(db_session, world):
    _to_meal_question(db_session, world)
    turn = engine.handle_parent_text(db_session, world["ctx"], "which tablets do I take tonight?", NOW)
    assert turn.bot_messages[-1] == "What did you have for breakfast today?"
    assert _meals(db_session) == []


def test_meal_question_in_tamil(db_session, world):
    world["profile"].preferred_language = "ta"
    db_session.commit()
    world["ctx"] = resolve_parent(db_session, world["parent"])
    turn = _to_meal_question(db_session, world, NIGHT)
    assert turn.bot_messages[-1] == "இன்று காலை உணவு, மதிய உணவு மற்றும் இரவு உணவு என்ன சாப்பிட்டீர்கள்?"


def test_daily_summary_lists_meals(db_session, world):
    _to_meal_question(db_session, world)
    engine.handle_parent_text(db_session, world["ctx"], "Idli", NOW)
    checkin = engine.start_or_resume(db_session, world["ctx"], NOW).checkin
    body = family_alerts._summary_body(db_session, checkin, world["profile"])
    assert "Meals:\n- Breakfast: Idli" in body


@pytest.mark.parametrize("language", ["en", "ta", "hi", "te", "ml", "kn"])
def test_meal_replies_translated(language):
    for key in ("meal_ask", "meal_breakfast", "meal_lunch", "meal_dinner", "word_and", "meal_saved"):
        assert key in TEMPLATES[language], key


def test_appointment_is_not_repeated_when_the_meal_question_reopens(db_session, world):
    from datetime import date
    from app.models.appointment import Appointment
    db_session.add(Appointment(
        family_id=world["family_id"], care_profile_id=world["profile"].id, reason="Doctor follow-up",
        provider="Dr. Rao", scheduled_date=date(2026, 11, 23), start_time="10:00", status="scheduled",
    ))
    db_session.commit()
    _to_meal_question(db_session, world)
    first = engine.handle_parent_text(db_session, world["ctx"], "Idli", NOW)
    reminder = "Tomorrow at 10:00 AM you have Doctor follow-up with Dr. Rao."
    assert reminder in first.bot_messages
    engine.start_or_resume(db_session, world["ctx"], NIGHT)
    later = engine.handle_parent_text(db_session, world["ctx"], "Rice and soup", NIGHT)
    assert reminder not in later.bot_messages
    assert later.bot_messages[-1] == NOTE_ASK
