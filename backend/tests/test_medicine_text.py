"""Voice mode for Add medicine: a spoken sentence (typed by Wispr Flow) is read into the form fields.

Gemini reads it when GEMINI_API_KEY is set; simple rules read it otherwise, or when Gemini fails.
"""

from decimal import Decimal

import pytest

from app.core.config import settings
from app.models.user import User
from app.services import families as families_svc
from app.services import understanding
from app.services.auth import create_auth_session
from app.services.medicine_text import parse_medicine_text

EXAMPLE = (
    "One tablet at 9 am and one tablet at 8 pm after food, and the total remaining quantity is 10. "
    "Pricing of the tablet is 550 tablets for ₹5"
)


@pytest.fixture(autouse=True)
def no_gemini(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)


# ---- rules ----


def test_rules_read_the_example_sentence():
    out = parse_medicine_text(EXAMPLE)
    assert out["source"] == "rules"
    assert out["reminder_times"] == ["09:00", "20:00"]
    assert out["instructions_text"] == "1 tablet at 9:00 AM and 8:00 PM, after food"
    assert out["quantity_remaining"] == 10
    assert out["total_medicine_count"] == 550
    assert out["unit_price"] == Decimal("0.01")


@pytest.mark.parametrize(
    "text, times, instructions",
    [
        ("2 tablets at 8:30 am before food", ["08:30"], "2 tablets at 8:30 AM, before food"),
        ("half tablet at night 10 pm", ["22:00"], "half tablet at 10:00 PM"),
        (
            "one tablet at 9 am and two tablets at 9 pm",
            ["09:00", "21:00"],
            "1 tablet at 9:00 AM and 2 tablets at 9:00 PM",
        ),
        ("take it at 12 pm and 12 am with food", ["12:00", "00:00"], "1 tablet at 12:00 PM and 12:00 AM, with food"),
        ("one capsule at 7 in the morning", ["07:00"], "1 capsule at 7:00 AM"),
    ],
    ids=["two-tablets-before-food", "half-tablet", "different-doses", "noon-midnight", "in-the-morning"],
)
def test_rules_read_times_and_dose(text, times, instructions):
    out = parse_medicine_text(text)
    assert out["reminder_times"] == times
    assert out["instructions_text"] == instructions


@pytest.mark.parametrize(
    "text, count, unit",
    [
        ("10 tablets for ₹55", 10, Decimal("5.50")),
        ("a strip of 15 tablets costs Rs. 90", 15, Decimal("6.00")),
        ("price is 4 rupees per tablet", None, Decimal("4.00")),
        ("₹2.50 each, total 30 tablets", 30, Decimal("2.50")),
    ],
    ids=["n-for-price", "strip-costs", "per-tablet", "each-and-total"],
)
def test_rules_read_pricing(text, count, unit):
    out = parse_medicine_text(text)
    assert out["total_medicine_count"] == count
    assert out["unit_price"] == unit


@pytest.mark.parametrize(
    "text, qty",
    [
        ("remaining quantity is 10", 10),
        ("we have 24 tablets left", 24),
        ("12 tablets remaining", 12),
        ("stock is twenty", 20),
    ],
)
def test_rules_read_quantity_left(text, qty):
    assert parse_medicine_text(text)["quantity_remaining"] == qty


def test_rules_leave_unknown_fields_empty():
    out = parse_medicine_text("hello there")
    assert out == {
        "instructions_text": None,
        "reminder_times": [],
        "quantity_remaining": None,
        "unit_price": None,
        "total_medicine_count": None,
        "source": "rules",
    }


def test_empty_text_is_rejected():
    with pytest.raises(ValueError):
        parse_medicine_text("   ")


# ---- Gemini ----


def test_gemini_answer_is_used_and_cleaned(monkeypatch):
    seen = {}

    def fake(prompt):
        seen["prompt"] = prompt
        return {
            "instructions_text": " 1 tablet at 9:00 AM and 8:00 PM, after food ",
            "reminder_times": ["9:00", "20:00", "20:00", "25:99", "bad"],
            "quantity_remaining": "10",
            "unit_price": 0.0091,
            "total_medicine_count": 550,
        }

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(understanding, "ask_gemini", fake)
    out = parse_medicine_text(EXAMPLE)
    assert EXAMPLE in seen["prompt"]
    assert out == {
        "instructions_text": "1 tablet at 9:00 AM and 8:00 PM, after food",
        "reminder_times": ["09:00", "20:00"],
        "quantity_remaining": 10,
        "unit_price": Decimal("0.01"),
        "total_medicine_count": 550,
        "source": "gemini",
    }


def test_gemini_bad_values_become_empty(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        understanding,
        "ask_gemini",
        lambda p: {"instructions_text": 5, "reminder_times": "9am", "quantity_remaining": -3, "unit_price": "x"},
    )
    out = parse_medicine_text("one tablet")
    assert out["source"] == "gemini"
    assert out["instructions_text"] is None
    assert out["reminder_times"] == []
    assert out["quantity_remaining"] is None
    assert out["unit_price"] is None
    assert out["total_medicine_count"] is None


def test_gemini_failure_falls_back_to_rules(monkeypatch):
    def boom(prompt):
        raise RuntimeError("Gemini request failed")

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(understanding, "ask_gemini", boom)
    out = parse_medicine_text(EXAMPLE)
    assert out["source"] == "rules"
    assert out["reminder_times"] == ["09:00", "20:00"]


# ---- API ----


@pytest.fixture()
def family(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    outsider = User(email="outsider@example.com", display_name="Outsider")
    db_session.add_all([manager, outsider])
    db_session.commit()
    fam = families_svc.create_family(db_session, manager, "Doe family")
    return {"id": fam.id, "manager": manager, "outsider": outsider}


def _auth(db, user):
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def test_parse_text_endpoint(client, db_session, family):
    r = client.post(
        f"/api/families/{family['id']}/medicines/parse-text",
        json={"text": EXAMPLE},
        headers=_auth(db_session, family["manager"]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reminder_times"] == ["09:00", "20:00"]
    assert body["quantity_remaining"] == 10
    assert body["total_medicine_count"] == 550
    assert Decimal(str(body["unit_price"])) == Decimal("0.01")
    assert body["source"] == "rules"


def test_parse_text_endpoint_rejects_empty_and_outsiders(client, db_session, family):
    url = f"/api/families/{family['id']}/medicines/parse-text"
    assert client.post(url, json={"text": " "}, headers=_auth(db_session, family["manager"])).status_code in (400, 422)
    assert client.post(url, json={"text": EXAMPLE}, headers=_auth(db_session, family["outsider"])).status_code == 403
