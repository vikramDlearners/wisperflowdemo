"""Voice mode for Add appointment: one spoken sentence fills the parent, reason, doctor, place, date, time and notes."""

from datetime import date

import pytest

from app.core.config import settings
from app.models.care_profile import CareProfile
from app.models.user import User
from app.services import families as families_svc
from app.services import understanding
from app.services.appointment_text import parse_appointment_text
from app.services.auth import create_auth_session

TODAY = date(2026, 11, 24)  # a Tuesday
PROFILES = [("p-amma", "Amma", "Amma"), ("p-dad", "Ramesh Iyer", "Appa")]

EXAMPLE = "Amma's eye check-up with Dr. Rao at Apollo Hospital next Tuesday at 10:30 am. Bring the old reports and her glasses."


@pytest.fixture(autouse=True)
def no_gemini(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)


def parse(text, profiles=PROFILES):
    return parse_appointment_text(text, TODAY, profiles)


def test_rules_read_the_example():
    out = parse(EXAMPLE)
    assert out["source"] == "rules"
    assert out["care_recipient_id"] == "p-amma"
    assert out["reason"] == "Eye check-up"
    assert out["provider"] == "Dr. Rao"
    assert out["location"] == "Apollo Hospital"
    assert out["scheduled_date"] == "2026-12-01"
    assert out["start_time"] == "10:30"
    assert out["notes"] == "Bring the old reports and her glasses."


@pytest.mark.parametrize(
    "text, when, time",
    [
        ("blood test tomorrow at 8 am", "2026-11-25", "08:00"),
        ("dentist on friday 4 pm", "2026-11-27", "16:00"),
        ("physiotherapy on 3 december at 5:15 pm", "2026-12-03", "17:15"),
        ("ECG today at noon", "2026-11-24", "12:00"),
        ("follow-up at 6 in the evening day after tomorrow", "2026-11-26", "18:00"),
        ("scan next week", "2026-12-01", None),
    ],
)
def test_rules_read_date_and_time(text, when, time):
    out = parse(text)
    assert out["scheduled_date"] == when
    assert out["start_time"] == time


@pytest.mark.parametrize(
    "text, reason, provider",
    [
        ("blood test tomorrow at 8 am", "Blood test", None),
        ("Cardiology follow-up with Doctor Meena Sharma on friday", "Cardiology follow-up", "Dr. Meena Sharma"),
        ("dentist on friday 4 pm", "Dentist visit", None),
        ("See dr kumar tomorrow at 11 am", "Doctor visit", "Dr. Kumar"),
        ("Diabetes review at City Clinic tomorrow", "Diabetes review", None),
    ],
)
def test_rules_read_reason_and_doctor(text, reason, provider):
    out = parse(text)
    assert out["reason"] == reason
    assert out["provider"] == provider


def test_place_is_read_without_the_time():
    out = parse("Diabetes review at City Clinic, Jayanagar tomorrow at 9 am")
    assert out["location"] == "City Clinic, Jayanagar"
    assert out["start_time"] == "09:00"


@pytest.mark.parametrize(
    "text, who",
    [("dad's blood test tomorrow", "p-dad"), ("take Ramesh to the dentist", "p-dad"), ("blood test tomorrow", None)],
)
def test_rules_find_the_parent(text, who):
    assert parse(text)["care_recipient_id"] == who


def test_single_parent_is_picked_without_being_named():
    assert parse("blood test tomorrow", [("p-amma", "Amma", "Amma")])["care_recipient_id"] == "p-amma"


def test_empty_text_is_rejected():
    with pytest.raises(ValueError):
        parse(" ")


def test_gemini_answer_is_checked(monkeypatch):
    seen = {}

    def fake(prompt):
        seen["prompt"] = prompt
        return {
            "for_whom": "amma",
            "reason": "Eye check-up",
            "provider": "Dr. Rao",
            "location": "Apollo Hospital",
            "date": "2026-12-01",
            "time": "10:30",
            "notes": "Bring the old reports.",
        }

    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(understanding, "ask_gemini", fake)
    out = parse(EXAMPLE)
    assert "Ramesh Iyer" in seen["prompt"] and "2026-11-24" in seen["prompt"]
    assert out == {
        "care_recipient_id": "p-amma",
        "care_recipient_name": "Amma",
        "reason": "Eye check-up",
        "provider": "Dr. Rao",
        "location": "Apollo Hospital",
        "scheduled_date": "2026-12-01",
        "start_time": "10:30",
        "notes": "Bring the old reports.",
        "source": "gemini",
    }


def test_gemini_bad_values_are_dropped(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(
        understanding, "ask_gemini",
        lambda p: {"reason": "Scan", "date": "soon", "time": "25:00", "for_whom": "Uncle", "provider": 3},
    )
    out = parse("scan")
    assert out["source"] == "gemini"
    assert (out["scheduled_date"], out["start_time"], out["care_recipient_id"], out["provider"]) == (
        None, None, None, None)


def test_gemini_failure_falls_back_to_rules(monkeypatch):
    def boom(prompt):
        raise RuntimeError("down")

    monkeypatch.setattr(settings, "gemini_api_key", "k")
    monkeypatch.setattr(understanding, "ask_gemini", boom)
    assert parse("blood test tomorrow at 8 am")["source"] == "rules"


def test_parse_text_endpoint(client, db_session):
    manager = User(email="m@example.com", display_name="Manager")
    outsider = User(email="o@example.com", display_name="Outsider")
    db_session.add_all([manager, outsider])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    profile = CareProfile(family_id=family.id, display_name="Amma", greeting_name="Amma")
    db_session.add(profile)
    db_session.commit()

    def post(user, text):
        return client.post(
            "/api/appointments/parse-text",
            json={"family_id": family.id, "text": text, "today": "2026-11-24"},
            headers={"Authorization": f"Bearer {create_auth_session(db_session, user.id)}"},
        )

    r = post(manager, EXAMPLE)
    assert r.status_code == 200, r.text
    assert r.json()["care_recipient_id"] == profile.id
    assert r.json()["start_time"] == "10:30"
    assert post(outsider, EXAMPLE).status_code == 403
