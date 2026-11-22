"""After a conversation finishes, Gemini summarises it into a table and important points become tasks
for the family's caretakers and managers."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.conversation_summary import ConversationSummary
from app.models.notification import Notification
from app.models.task import Task
from app.services import checkin as engine
from app.services import conversation_summary as svc
from app.services import understanding

from tests.test_checkin_engine import NOW, offline, world, no_meal_questions  # noqa: F401
from tests.test_parent_invites import email, family_setup  # noqa: F401

LATER = NOW + timedelta(minutes=2)


@pytest.fixture()
def gemini(monkeypatch):
    calls = []
    result = {
        "summary": "Amma said her knee hurts. She took both morning medicines.",
        "important": [{"title": "Check on Amma's knee pain", "detail": "She said her knee hurts today.",
                       "priority": "normal"}],
    }

    def fake(prompt):
        calls.append(prompt)
        return result

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(understanding, "ask_gemini", fake)
    return {"calls": calls, "result": result}


def _finish(db, world, when=NOW):
    engine.start_or_resume(db, world["ctx"], when)
    engine.handle_parent_text(db, world["ctx"], "my knee hurts", when)
    return engine.handle_parent_text(db, world["ctx"], "yes", when)


def _summaries(db):
    return db.execute(select(ConversationSummary)).scalars().all()


def _tasks(db):
    return db.execute(select(Task).order_by(Task.created_at)).scalars().all()


def test_finished_conversation_is_summarised_and_saved(db_session, world, gemini):
    _finish(db_session, world)
    assert svc.summarise_conversations(db_session, LATER) == 1
    [row] = _summaries(db_session)
    assert row.summary == "Amma said her knee hurts. She took both morning medicines."
    assert row.source == "gemini"
    assert row.care_profile_id == world["profile"].id
    assert row.important == gemini["result"]["important"]
    # Gemini saw the conversation, both sides.
    assert "Parent: my knee hurts" in gemini["calls"][0]
    assert "Assistant: How are you feeling today?" in gemini["calls"][0]


def test_important_points_become_tasks_for_caretakers_and_managers(db_session, world, gemini):
    _finish(db_session, world)
    svc.summarise_conversations(db_session, LATER)
    tasks = _tasks(db_session)
    assignees = {t.assigned_to_user_id for t in tasks}
    manager_id = world["manager"].id
    carer_id = next(u for u in world["member_ids"] if u not in (manager_id, world["caregiver_membership"].user_id))
    # The Family manager and the Caregiver get it; the Viewer and the parent do not.
    assert assignees == {manager_id, carer_id}
    assert all(t.title == "Check on Amma's knee pain" and t.status == "OPEN" for t in tasks)
    assert all(t.care_profile_id == world["profile"].id for t in tasks)
    notes = db_session.execute(select(Notification).where(Notification.type == "task.assigned")).scalars().all()
    assert {n.recipient_user_id for n in notes} == assignees


def test_not_summarised_while_the_parent_may_still_be_talking(db_session, world, gemini):
    _finish(db_session, world)
    assert svc.summarise_conversations(db_session, NOW + timedelta(seconds=20)) == 0
    assert _summaries(db_session) == []


def test_unfinished_conversation_is_summarised_after_a_long_pause(db_session, world, gemini):
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "my knee hurts", NOW)  # left in the medicines step
    assert svc.summarise_conversations(db_session, NOW + timedelta(minutes=5)) == 0
    assert svc.summarise_conversations(db_session, NOW + timedelta(minutes=31)) == 1


def test_each_part_of_the_conversation_is_summarised_once(db_session, world, gemini):
    _finish(db_session, world)
    svc.summarise_conversations(db_session, LATER)
    assert svc.summarise_conversations(db_session, LATER + timedelta(minutes=5)) == 0
    # The parent says more later: only the new part is summarised; the same task is not created twice.
    later = NOW + timedelta(hours=3)
    engine.handle_parent_text(db_session, world["ctx"], "my knee still hurts", later)
    assert svc.summarise_conversations(db_session, later + timedelta(minutes=2)) == 1
    rows = _summaries(db_session)
    assert len(rows) == 2
    assert rows[1].from_seq > rows[0].to_seq
    assert "my knee still hurts" in gemini["calls"][1] and "Parent: yes" not in gemini["calls"][1]
    assert len(_tasks(db_session)) == 2  # still one per assignee


def test_no_important_points_means_no_tasks(db_session, world, gemini):
    gemini["result"]["important"] = []
    _finish(db_session, world)
    svc.summarise_conversations(db_session, LATER)
    assert len(_summaries(db_session)) == 1
    assert _tasks(db_session) == []


def test_without_gemini_a_simple_summary_is_saved_and_urgent_becomes_a_task(db_session, world, email):
    # offline fixture: no Gemini key
    engine.start_or_resume(db_session, world["ctx"], NOW)
    engine.handle_parent_text(db_session, world["ctx"], "I fell down", NOW)
    engine.handle_parent_text(db_session, world["ctx"], "yes", NOW)
    svc.summarise_conversations(db_session, LATER)
    [row] = _summaries(db_session)
    assert row.source == "rules"
    assert "I fell down" in row.summary
    tasks = _tasks(db_session)
    assert tasks and all(t.priority == "high" for t in tasks)
    assert all(t.title == "Call Amma now: something needed attention" for t in tasks)


def test_gemini_failure_falls_back_to_the_simple_summary(db_session, world, monkeypatch):
    def boom(prompt):
        raise RuntimeError("Gemini request failed")

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(understanding, "ask_gemini", boom)
    _finish(db_session, world)
    assert svc.summarise_conversations(db_session, LATER) == 1
    assert _summaries(db_session)[0].source == "rules"


def test_gemini_answer_is_cleaned(db_session, world, gemini):
    gemini["result"]["important"] = [
        {"title": "  ", "detail": "no title"},
        {"title": "x" * 400, "priority": "urgent!!"},
        "not a dict",
        {"title": "A"}, {"title": "B"}, {"title": "C"}, {"title": "D"},
    ]
    _finish(db_session, world)
    svc.summarise_conversations(db_session, LATER)
    titles = sorted({t.title for t in _tasks(db_session)})
    assert len(titles) == 3  # at most three tasks per conversation part
    assert all(len(t) <= 200 for t in titles)
    assert {t.priority for t in _tasks(db_session)} <= {"normal", "high"}
