import pytest

from app.core.config import settings
from app.services import understanding
from app.services.adapters.intent import OFFLINE_RULES, ONLINE_LLM
from app.services.doses import DueDose
from app.services.understanding import is_urgent, understand_medicines


def _dose(mid: str, name: str = "Med") -> DueDose:
    return DueDose(medicine_id=mid, name=name, slot="08:00", due_at=None, status=None)


@pytest.mark.parametrize(
    "text",
    ["I fell in the bathroom", "விழுந்துட்டேன்", "मैं गिर गई", "I have chest pain", "I can't breathe", "I feel DIZZY", "help me"],
)
def test_urgent_true(text):
    assert is_urgent(text) is True


@pytest.mark.parametrize("text", ["my knee hurts a little", "I have some pain", "all fine", "", "that was helpful"])
def test_urgent_false(text):
    assert is_urgent(text) is False


def test_rules_one_med_taken():
    r = understand_medicines("I took it", [_dose("a")], OFFLINE_RULES)
    assert [(i.medicine_id, i.outcome) for i in r.items] == [("a", "taken")]
    assert r.unclear is False


def test_rules_one_med_remind_later_default_delay():
    r = understand_medicines("remind me later", [_dose("a")], OFFLINE_RULES)
    assert r.items[0].outcome == "remind_later"
    assert r.delay_minutes == 15


def test_rules_one_med_finished():
    r = understand_medicines("I ran out", [_dose("a")], OFFLINE_RULES)
    assert r.items[0].outcome == "finished"


def test_rules_two_meds_yes_all():
    r = understand_medicines("yes took both", [_dose("a"), _dose("b")], OFFLINE_RULES)
    assert [(i.medicine_id, i.outcome) for i in r.items] == [("a", "taken"), ("b", "taken")]


def test_rules_two_meds_no_all():
    r = understand_medicines("not yet", [_dose("a"), _dose("b")], OFFLINE_RULES)
    assert [i.outcome for i in r.items] == ["not_taken", "not_taken"]


def test_rules_two_meds_partial_unclear():
    r = understand_medicines("the BP one only", [_dose("a"), _dose("b")], OFFLINE_RULES)
    assert r.unclear is True
    assert r.items == []


def test_rules_unknown_unclear():
    r = understand_medicines("banana", [_dose("a")], OFFLINE_RULES)
    assert r.unclear is True


def test_gemini_mapped(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(
        understanding,
        "ask_gemini",
        lambda prompt: {
            "answers": [
                {"medicine_id": "a", "outcome": "taken"},
                {"medicine_id": "zzz", "outcome": "taken"},
                {"medicine_id": "b", "outcome": "bogus"},
                {"medicine_id": "b", "outcome": "remind_later"},
            ],
            "delay_minutes": 20,
        },
    )
    r = understand_medicines("BP one yes", [_dose("a"), _dose("b")], ONLINE_LLM)
    assert [(i.medicine_id, i.outcome) for i in r.items] == [("a", "taken"), ("b", "remind_later")]
    assert r.delay_minutes == 20
    assert r.unclear is False


def test_gemini_invalid_delay_defaults(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(
        understanding, "ask_gemini",
        lambda p: {"answers": [{"medicine_id": "a", "outcome": "remind_later"}], "delay_minutes": 7},
    )
    r = understand_medicines("later", [_dose("a")], ONLINE_LLM)
    assert r.delay_minutes == 15


def test_gemini_no_valid_answers_unclear(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(understanding, "ask_gemini", lambda p: {"answers": []})
    r = understand_medicines("mumble", [_dose("a")], ONLINE_LLM)
    assert r.unclear is True


def test_gemini_error_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "k")

    def boom(prompt):
        raise RuntimeError("down")

    monkeypatch.setattr(understanding, "ask_gemini", boom)
    r = understand_medicines("I took it", [_dose("a")], ONLINE_LLM)
    assert r.items[0].outcome == "taken"


def test_online_without_key_uses_rules(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)

    def boom(prompt):
        raise AssertionError("should not be called")

    monkeypatch.setattr(understanding, "ask_gemini", boom)
    r = understand_medicines("I took it", [_dose("a")], ONLINE_LLM)
    assert r.items[0].outcome == "taken"
