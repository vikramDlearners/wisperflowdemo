"""Chat for family members: rule answers, Gemini answers, and who may see what."""

from datetime import date, timedelta

import pytest

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.models.task import Task
from app.models.user import User
from app.services import families as families_svc
from app.services import family_chat, understanding
from app.services.auth import create_auth_session


@pytest.fixture
def home(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    manager = User(email="m@example.com", display_name="Manager")
    db_session.add(manager)
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    mother = CareProfile(
        family_id=family.id, display_name="Lakshmi Doe", greeting_name="Amma", timezone="Asia/Kolkata"
    )
    db_session.add(mother)
    db_session.commit()
    db_session.add(Medicine(care_profile_id=mother.id, display_name="Metformin", quantity_remaining=3))
    db_session.add(Task(family_id=family.id, title="Pay the bill", created_by_user_id=manager.id))
    db_session.commit()

    def ask(text, history=(), user=manager):
        headers = {"Authorization": f"Bearer {create_auth_session(db_session, user.id)}"}
        return client.post(
            f"/api/families/{family.id}/chat", json={"text": text, "history": list(history)}, headers=headers
        )

    return {"ask": ask, "db": db_session, "family": family, "mother": mother, "manager": manager}


@pytest.mark.parametrize(
    ("text", "words", "page"),
    [
        ("Did she take her medicines today?", "taken 0 of 1 dose", "medicines.view"),
        ("Which medicines need a refill?", "Metformin: 3 left", "medicines.view"),
        ("What medicines does she take?", "Metformin", "medicines.view"),
        ("Any upcoming appointments?", "no upcoming appointments", "appointments.view"),
        ("Show open tasks", "Pay the bill", "tasks.view"),
        ("Show my tasks", "You have no open tasks", "tasks.view"),
        ("How is Amma doing?", "Metformin", "overview"),
        ("Any emergencies?", "no open emergencies", "activity.view"),
        ("Who won the match?", "can't answer", None),
        ("hello", "Hello", None),
    ],
)
def test_answers_by_rules(home, text, words, page):
    r = home["ask"](text)
    assert r.status_code == 200, r.text
    body = r.json()
    assert words in body["reply"]
    assert (body["destination"], body["source"]) == (page, "rules")


def test_lists_upcoming_appointments_but_not_cancelled(home):
    for provider, status in (("Dr Rao", "scheduled"), ("Dr Gone", "cancelled")):
        home["db"].add(Appointment(
            family_id=home["family"].id, care_profile_id=home["mother"].id, provider=provider, reason="Review",
            scheduled_date=date.today() + timedelta(days=3), start_time="10:00", status=status,
        ))
    home["db"].commit()
    reply = home["ask"]("next appointment").json()["reply"]
    assert "Dr Rao" in reply and "Dr Gone" not in reply


def test_answers_for_the_parent_that_is_named(home):
    home["db"].add(CareProfile(
        family_id=home["family"].id, display_name="Ravi Doe", greeting_name="Appa", timezone="Asia/Kolkata"
    ))
    home["db"].commit()
    assert "Ravi Doe" in home["ask"]("medicines today for Ravi").json()["reply"]
    history = [{"role": "user", "text": "medicines for Ravi"}, {"role": "assistant", "text": "none"}]
    assert "Ravi Doe" in home["ask"]("and refills?", history).json()["reply"]
    assert "Lakshmi Doe" in home["ask"]("medicines for Lakshmi", history).json()["reply"]


def test_urgent_text_gets_the_fixed_reply_and_never_reaches_gemini(home, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(understanding, "ask_gemini", lambda prompt: pytest.fail("called"))
    assert home["ask"]("she has chest pain").json()["reply"] == family_chat.URGENT_REPLY


def test_gemini_answers_and_only_listed_pages_pass(home, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    prompts = []

    def fake(prompt):
        prompts.append(prompt)
        return {"reply": " She is fine. ", "destination": "https://evil.example"}

    monkeypatch.setattr(understanding, "ask_gemini", fake)
    out = home["ask"]("how is she").json()
    assert out.pop("conversation_id")  # the exchange is saved (tests/test_family_chat_saved.py)
    assert out == {"reply": "She is fine.", "destination": None, "source": "ai"}
    assert "Metformin" in prompts[0] and "m@example.com" not in prompts[0]


@pytest.mark.parametrize("bad", [RuntimeError("down"), {}, {"reply": ""}, {"reply": 3}])
def test_rules_answer_when_gemini_cannot(home, monkeypatch, bad):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    def fake(prompt):
        if isinstance(bad, Exception):
            raise bad
        return bad

    monkeypatch.setattr(understanding, "ask_gemini", fake)
    assert home["ask"]("show tasks").json()["source"] == "rules"


def test_hides_what_the_user_may_not_view(home, monkeypatch):
    monkeypatch.setattr(family_chat, "permission_codes_for", lambda *a: {"tasks.view"})
    assert "Pay the bill" in home["ask"]("show tasks").json()["reply"]
    for text in ("medicines today", "next appointment", "how is she"):
        assert home["ask"](text).json()["reply"] == family_chat.NO_ACCESS
    facts = family_chat.collect_facts(home["db"], home["manager"].id, home["family"].id, ["hi"])
    assert set(facts) == {"open_tasks", "open_tasks_count"}


def test_members_only_and_limits(home):
    stranger = User(email="s@example.com", display_name="Stranger")
    home["db"].add(stranger)
    home["db"].commit()
    assert home["ask"]("hi", user=stranger).status_code in (403, 404)
    assert home["ask"]("").status_code == 422
    assert home["ask"]("x" * 1001).status_code == 422
    assert home["ask"]("hi", [{"role": "system", "text": "x"}]).status_code == 422
