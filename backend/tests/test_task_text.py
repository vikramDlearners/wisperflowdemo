"""Voice mode for New task: one spoken sentence becomes the task's title, notes, due date, urgency and assignee."""

from datetime import date

import pytest

from app.core.config import settings
from app.models.membership import FamilyMember
from app.models.user import User
from app.services import families as families_svc
from app.services import understanding
from app.services.auth import create_auth_session
from app.services.task_text import parse_task_text

TODAY = date(2026, 11, 24)  # a Tuesday
MEMBERS = [("u-deepak", "Deepak Kumar"), ("u-priya", "Priya"), ("u-me", "Sudha")]


@pytest.fixture(autouse=True)
def no_gemini(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)


def parse(text):
    return parse_task_text(text, TODAY, MEMBERS, me_id="u-me")


# ---- rules ----


def test_rules_read_the_example():
    out = parse("Get the medicine from the store next week and assign it to deepek")
    assert out["source"] == "rules"
    assert out["title"] == "Get the medicine from the store"
    assert out["due_date"] == "2026-12-01"
    assert out["assignee_user_id"] == "u-deepak"
    assert out["assignee_name"] == "Deepak Kumar"


@pytest.mark.parametrize(
    "text, due",
    [
        ("pay the bill today", "2026-11-24"),
        ("call the doctor tomorrow", "2026-11-25"),
        ("book a cab day after tomorrow", "2026-11-26"),
        ("refill tablets in 3 days", "2026-11-27"),
        ("renew insurance in 2 weeks", "2026-12-08"),
        ("pick up reports on friday", "2026-11-27"),
        ("visit amma next monday", "2026-11-30"),
        ("buy diapers by 5 december", "2026-12-05"),
        ("buy diapers by dec 5th", "2026-12-05"),
        ("get groceries this weekend", "2026-11-28"),
        ("clean the room", None),
    ],
)
def test_rules_read_due_dates(text, due):
    assert parse(text)["due_date"] == due


@pytest.mark.parametrize(
    "text, user",
    [
        ("Buy fruits, assign to Priya", "u-priya"),
        ("Ask deepak to fix the fan", "u-deepak"),
        ("give this to priyaa: water the plants", "u-priya"),
        ("Call the plumber, assign it to me", "u-me"),
        ("Call the plumber, assign it to Ramesh", None),
        ("Call the plumber", None),
    ],
)
def test_rules_find_the_assignee(text, user):
    assert parse(text)["assignee_user_id"] == user


def test_ask_x_to_becomes_the_title():
    out = parse("Ask deepak to fix the fan tomorrow")
    assert out["title"] == "Fix the fan"


@pytest.mark.parametrize(
    "text, priority",
    [("urgent: refill BP tablets", "high"), ("buy bulbs, no rush", "low"), ("buy bulbs", "normal")],
)
def test_rules_read_urgency(text, priority):
    assert parse(text)["priority"] == priority


def test_rules_keep_extra_sentences_as_notes():
    out = parse(
        "Get the medicine from the store next week, assign it to Deepak. "
        "Take the old prescription and ask for the 30 tablet strip."
    )
    assert out["title"] == "Get the medicine from the store"
    assert out["description"] == "Take the old prescription and ask for the 30 tablet strip."


def test_empty_text_is_rejected():
    with pytest.raises(ValueError):
        parse("  ")


# ---- Gemini ----


def test_gemini_answer_is_checked(monkeypatch):
    seen = {}

    def fake(prompt):
        seen["prompt"] = prompt
        return {
            "title": "Get medicine from the store",
            "description": "",
            "due_date": "2026-12-01",
            "priority": "URGENT",
            "assignee_name": "deepek",
        }

    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(understanding, "ask_gemini", fake)
    out = parse("Get the medicine from the store next week and assign it to deepek")
    assert "Deepak Kumar" in seen["prompt"] and "2026-11-24" in seen["prompt"]
    assert out == {
        "title": "Get medicine from the store",
        "description": None,
        "due_date": "2026-12-01",
        "priority": "normal",
        "assignee_user_id": "u-deepak",
        "assignee_name": "Deepak Kumar",
        "source": "gemini",
    }


def test_gemini_bad_date_and_unknown_person(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(
        understanding, "ask_gemini",
        lambda p: {"title": "Fix fan", "due_date": "next week", "priority": "high", "assignee_name": "Ramesh"},
    )
    out = parse("fix fan")
    assert out["due_date"] is None
    assert out["priority"] == "high"
    assert out["assignee_user_id"] is None


def test_gemini_without_title_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(understanding, "ask_gemini", lambda p: {"title": ""})
    out = parse("call the doctor tomorrow")
    assert out["source"] == "rules"
    assert out["title"] == "Call the doctor"


def test_gemini_failure_falls_back_to_rules(monkeypatch):
    def boom(prompt):
        raise RuntimeError("down")

    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(understanding, "ask_gemini", boom)
    assert parse("call the doctor tomorrow")["source"] == "rules"


# ---- API ----


def test_parse_text_endpoint_matches_family_members(client, db_session):
    manager = User(email="m@example.com", display_name="Manager")
    deepak = User(email="d@example.com", display_name="Deepak")
    db_session.add_all([manager, deepak])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    member = db_session.query(FamilyMember).filter_by(family_id=family.id, user_id=manager.id).one()
    db_session.add(FamilyMember(family_id=family.id, user_id=deepak.id, role_id=member.role_id, status="active"))
    db_session.commit()

    r = client.post(
        f"/api/families/{family.id}/tasks/parse-text",
        json={"text": "Get the medicine from the store next week and assign it to deepek", "today": "2026-11-24"},
        headers={"Authorization": f"Bearer {create_auth_session(db_session, manager.id)}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assignee_user_id"] == deepak.id
    assert body["due_date"] == "2026-12-01"
    assert body["title"] == "Get the medicine from the store"
