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


# ---------- "ran out" only for explicit phrases; negations are "not taken" ----------

@pytest.mark.parametrize(
    "text",
    [
        "இல்லை", "இன்னும் இல்லை", "எடுக்கவில்லை", "சாப்பிடவில்லை",
        "अभी तक नहीं", "नहीं ली", "नहीं", "अभी नहीं",
        "not yet", "no", "No.", "I haven't taken it", "I didn't take it",
    ],
)
def test_rules_negations_are_not_taken(text):
    r = understand_medicines(text, [_dose("a")], OFFLINE_RULES)
    assert [i.outcome for i in r.items] == ["not_taken"], text


@pytest.mark.parametrize(
    "text",
    [
        "I ran out", "the tablets finished", "medicine finished", "no tablets left", "I am out of medicine",
        "மருந்து தீர்ந்துவிட்டது", "दवा खत्म हो गई", "गोली खत्म हो गया", "दवा खत्म",
    ],
)
def test_rules_explicit_ran_out_is_finished(text):
    r = understand_medicines(text, [_dose("a")], OFFLINE_RULES)
    assert [i.outcome for i in r.items] == ["finished"], text


def test_rules_took_beats_finished_breakfast():
    r = understand_medicines("I finished breakfast and took it", [_dose("a")], OFFLINE_RULES)
    assert [i.outcome for i in r.items] == ["taken"]


def test_rules_no_then_remind_later_still_reminds():
    r = understand_medicines("No, remind me in 10 minutes", [_dose("a")], OFFLINE_RULES)
    assert r.items[0].outcome == "remind_later"
    assert r.delay_minutes == 10


@pytest.mark.parametrize(
    "text", ["thank you for your help", "thanks for the help", "I didn't fall", "I fell asleep early", "no pain today"],
)
def test_urgent_false_for_obvious_negations_and_politeness(text):
    assert is_urgent(text) is False


@pytest.mark.parametrize("text", ["I fell asleep and then I fell down", "help, I fell", "no pain but I feel dizzy"])
def test_urgent_still_true_with_a_real_urgent_word(text):
    assert is_urgent(text) is True


def test_gemini_failure_is_logged_without_the_key(monkeypatch, caplog):
    monkeypatch.setattr(settings, "gemini_api_key", "secret-key-123")

    def boom(prompt):
        raise RuntimeError("Gemini request failed with HTTP status 500")

    monkeypatch.setattr(understanding, "ask_gemini", boom)
    with caplog.at_level("WARNING", logger="app.services.understanding"):
        understand_medicines("I took it", [_dose("a")], ONLINE_LLM)
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, "a failed Gemini call must be logged"
    assert all("secret-key-123" not in r.getMessage() for r in warnings)


# ---------- round 2: negated "ran out", urgent "took a fall" ----------

@pytest.mark.parametrize("text", ["I haven't run out", "it has not run out yet", "the medicine is not finished",
                                  "दवा खत्म नहीं हुई"])
def test_rules_denied_ran_out_alone_is_unclear(text):
    r = understand_medicines(text, [_dose("a")], OFFLINE_RULES)
    assert r.unclear is True and r.items == [], text


@pytest.mark.parametrize("text", ["I ran out of time, didn't take it", "தீர்ந்துவிடவில்லை, இன்னும் எடுக்கவில்லை",
                                  "I haven't run out but I haven't taken it"])
def test_rules_denied_ran_out_with_not_taken_is_not_taken(text):
    r = understand_medicines(text, [_dose("a")], OFFLINE_RULES)
    assert [i.outcome for i in r.items] == ["not_taken"], text


def test_rules_denied_ran_out_tamil_alone_is_not_finished():
    r = understand_medicines("தீர்ந்துவிடவில்லை", [_dose("a")], OFFLINE_RULES)
    assert all(i.outcome != "finished" for i in r.items)


def test_rules_urgent_took_a_fall_is_not_taken_as_a_dose():
    r = understand_medicines("I took a fall", [_dose("a", "Amlodipine")], OFFLINE_RULES)
    assert r.unclear is True and r.items == []


@pytest.mark.parametrize("text", ["I took my tablets but I feel dizzy", "took Amlodipine, then I fell",
                                  "I took my pills, but I feel dizzy"])
def test_rules_urgent_with_a_medicine_reference_is_still_taken(text):
    r = understand_medicines(text, [_dose("a", "Amlodipine")], OFFLINE_RULES)
    assert [i.outcome for i in r.items] == ["taken"], text


# ---------- round 3 ----------

def test_rules_tamil_ran_out_then_separate_negative_word_is_finished():
    r = understand_medicines("தீர்ந்துவிட்டது எடுக்கவில்லை", [_dose("a")], OFFLINE_RULES)
    assert [i.outcome for i in r.items] == ["finished"]


@pytest.mark.parametrize("text", ["தீர்ந்துவிடவில்லை", "தீரவில்லை", "தீர்ந்து இல்லை"])
def test_rules_tamil_not_finished_forms_are_not_finished(text):
    r = understand_medicines(text, [_dose("a")], OFFLINE_RULES)
    assert all(i.outcome != "finished" for i in r.items), text


def test_rules_urgent_both_knees_is_not_taken():
    r = understand_medicines("I took a fall and hurt both knees", [_dose("a"), _dose("b")], OFFLINE_RULES)
    assert r.unclear is True and r.items == []


def test_rules_urgent_took_both_with_two_due_is_taken():
    r = understand_medicines("I took both but I feel dizzy", [_dose("a"), _dose("b")], OFFLINE_RULES)
    assert [i.outcome for i in r.items] == ["taken", "taken"]


def test_rules_took_both_not_urgent_still_taken():
    r = understand_medicines("I took both", [_dose("a"), _dose("b")], OFFLINE_RULES)
    assert [i.outcome for i in r.items] == ["taken", "taken"]


# ---------- medicine schedule questions ----------

from app.services.understanding import is_medicine_question  # noqa: E402


@pytest.mark.parametrize("text", [
    "What medicine do I need to take now or in the night?",
    "which tablets should I take",
    "when is my next medicine",
    "what are my medicines today?",
    "tell me my tablets for tonight",
    "do I have any pills at night?",
    "இன்னைக்கு என்ன மாத்திரை சாப்பிடணும்?",
    "எந்த மருந்து இரவு எடுக்கணும்",
    "मुझे कौन सी दवा लेनी है?",
    "रात को कौनसी गोली खानी है",
    "ఈ రోజు ఏ మందు వేసుకోవాలి?",
    "ഇന്ന് ഏത് മരുന്ന് കഴിക്കണം?",
    "ಇವತ್ತು ಯಾವ ಮಾತ್ರೆ ತೆಗೆದುಕೊಳ್ಳಬೇಕು?",
])
def test_medicine_questions_detected(text):
    assert is_medicine_question(text) is True


@pytest.mark.parametrize("text", [
    "yes I took my medicine",
    "I took both tablets",
    "not yet, I will take the tablets after food",
    "my knee is paining",
    "I ran out of tablets",
    "ஆமா மாத்திரை சாப்பிட்டேன்",
    "हाँ दवा ले ली",
    "",
])
def test_medicine_answers_are_not_questions(text):
    assert is_medicine_question(text) is False


# ---------- how many did you take? ----------

from app.services.understanding import ALL, NONE, count_scope, is_dose_report  # noqa: E402

_DUE = [DueDose("a", "Amlodipine", "08:00", None, None), DueDose("m", "Metformin 500 mg", "08:00", None, None)]


@pytest.mark.parametrize("text,expected", [
    ("I took my medicine", None),
    ("I took my tablets", None),
    ("yes", ALL),
    ("both", ALL),
    ("I took all of them", ALL),
    ("took them", ALL),
    ("none", NONE),
    ("only one", 1),
    ("2", 2),
    ("two", 2),
    ("I took Metformin 500 mg", ["m"]),
    ("amlodipine and metformin 500 mg", ["a", "m"]),
    ("ரெண்டும் சாப்பிட்டேன்", ALL),
    ("दोनों ले ली", ALL),
    ("एक ली", 1),
    ("ಎರಡೂ", ALL),
])
def test_count_scope(text, expected):
    assert count_scope(text, _DUE) == expected


@pytest.mark.parametrize("text,expected", [
    ("I took my evening tablets", True),
    ("took my medicine", True),
    ("which medicine do I take?", False),
    ("I feel tired", False),
    ("I didn't take my medicine", False),
])
def test_is_dose_report(text, expected):
    assert is_dose_report(text) is expected


@pytest.mark.parametrize("text", ["yes", "Yes.", "ஆமா", "ஆம்", "हाँ", "అవును", "അതെ", "ಹೌದು"])
def test_bare_yes_in_every_language_is_taken(text):
    answers = understand_medicines(text, [_dose("a")], OFFLINE_RULES)
    assert [(a.medicine_id, a.outcome) for a in answers.items] == [("a", "taken")]
