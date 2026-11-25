"""Ask for help: the LLM fallback that picks a page when the app's text rules are not sure."""

import re
from pathlib import Path

import pytest

from app.core.config import settings
from app.models.user import User
from app.services import families as families_svc
from app.services import understanding
from app.services.ask_help import DESTINATIONS, choose_destination
from app.services.auth import create_auth_session


@pytest.fixture
def gemini(monkeypatch):
    """Set the reply; the prompts that were sent are recorded."""
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    state = {"reply": {"destination": None}, "prompts": []}

    def fake(prompt):
        state["prompts"].append(prompt)
        if isinstance(state["reply"], Exception):
            raise state["reply"]
        return state["reply"]

    monkeypatch.setattr(understanding, "ask_gemini", fake)
    return state


def test_pages_match_the_frontend():
    source = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "askHelp.ts"
    block = source.read_text(encoding="utf-8").split("DESTINATIONS = {")[1].split("} satisfies")[0]
    assert set(re.findall(r'^\s*"?([a-z_.]+)"?: \{ label', block, re.MULTILINE)) == set(DESTINATIONS)


def test_picks_a_listed_page(gemini):
    gemini["reply"] = {"destination": "tasks.add"}
    assert choose_destination("somebody must pay the bill", []) == {"destination": "tasks.add", "available": True}
    assert "somebody must pay the bill" in gemini["prompts"][0]


@pytest.mark.parametrize("bad", ["/admin", "https://evil.example", "", None, 3, ["tasks.add"]])
def test_never_returns_an_unlisted_page(gemini, bad):
    gemini["reply"] = {"destination": bad}
    assert choose_destination("hello", []) == {"destination": None, "available": True}


def test_a_tried_page_is_not_offered_again(gemini):
    gemini["reply"] = {"destination": "tasks.add"}
    assert choose_destination("x", ["tasks.add"])["destination"] is None
    assert "tasks.add" not in gemini["prompts"][0]


def test_no_key_or_failure_is_unavailable(gemini, monkeypatch):
    gemini["reply"] = RuntimeError("down")
    assert choose_destination("x", []) == {"destination": None, "available": False}
    monkeypatch.setattr(settings, "gemini_api_key", None)
    assert choose_destination("x", []) == {"destination": None, "available": False}
    assert len(gemini["prompts"]) == 1


def test_endpoint_is_for_family_members_only(client, db_session, gemini):
    gemini["reply"] = {"destination": "records.view"}
    manager = User(email="m@example.com", display_name="Manager")
    stranger = User(email="s@example.com", display_name="Stranger")
    db_session.add_all([manager, stranger])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    url = f"/api/families/{family.id}/ask"

    def headers(user):
        return {"Authorization": f"Bearer {create_auth_session(db_session, user.id)}"}

    r = client.post(url, json={"text": "what did she say last week"}, headers=headers(manager))
    assert r.status_code == 200, r.text
    assert r.json() == {"destination": "records.view", "available": True}
    assert client.post(url, json={"text": ""}, headers=headers(manager)).status_code == 422
    assert client.post(url, json={"text": "x"}, headers=headers(stranger)).status_code in (403, 404)
    assert client.post(url, json={"text": "x"}).status_code == 401
    assert len(gemini["prompts"]) == 1
