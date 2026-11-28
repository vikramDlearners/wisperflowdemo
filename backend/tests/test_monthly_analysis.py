"""The month's analysis in the family Chat: which month is asked for, what is counted, who sees what, and saving."""

from datetime import date, datetime, timezone

import pytest

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.models.checkin import ChatMessage, HealthCheckin
from app.models.conversation_summary import ConversationSummary
from app.models.dose import MedicineDose
from app.models.emergency import Emergency
from app.models.insurance import InsurancePolicy
from app.models.meal import MealLog
from app.models.medicine import Medicine
from app.models.membership import FamilyMember
from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
from app.services import monthly_analysis
from app.services.auth import create_auth_session

TODAY = date(2026, 11, 28)


@pytest.mark.parametrize(
    ("text", "period"),
    [
        ("Give me last month's analysis", (date(2026, 10, 1), date(2026, 10, 31))),
        ("monthly report please", (date(2026, 10, 1), date(2026, 10, 31))),
        ("analysis", (date(2026, 10, 1), date(2026, 10, 31))),
        ("Summary of this month", (date(2026, 11, 1), date(2026, 11, 30))),
        ("Analyse September", (date(2026, 9, 1), date(2026, 9, 30))),
        ("analysis for Dec", (date(2025, 12, 1), date(2025, 12, 31))),  # December not here yet: last year's
        ("February 2024 recap", (date(2024, 2, 1), date(2024, 2, 29))),
        ("Previous month summary", (date(2026, 10, 1), date(2026, 10, 31))),
        ("analysis for May", (date(2026, 5, 1), date(2026, 5, 31))),
        ("Analyse how she may be doing", (date(2026, 10, 1), date(2026, 10, 31))),
    ],
)
def test_which_month_is_asked_for(text, period):
    assert monthly_analysis.asked_period(text, TODAY) == period


@pytest.mark.parametrize("text", ["How is Amma doing?", "Show my tasks", "Which medicines need a refill?",
                                  "What did she eat last month"])
def test_other_questions_are_not_an_analysis(text):
    assert monthly_analysis.asked_period(text, TODAY) is None


def test_last_month_in_january_is_december():
    assert monthly_analysis.asked_period("last month's analysis", date(2027, 1, 5)) == (
        date(2026, 12, 1), date(2026, 12, 31))


def _at(day: int, hour: int = 6, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=timezone.utc)


@pytest.fixture
def home(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    db = db_session
    manager = User(email="m@example.com", display_name="Manager")
    viewer = User(email="v@example.com", display_name="Viewer")
    parent = User(email="p@example.com", display_name="Lakshmi")
    db.add_all([manager, viewer, parent])
    db.commit()
    family = families_svc.create_family(db, manager, "Doe family")
    role = db.query(Role).filter_by(family_id=family.id, name="Viewer").one()
    db.add(FamilyMember(family_id=family.id, user_id=viewer.id, role_id=role.id, status="active"))
    mother = CareProfile(family_id=family.id, display_name="Lakshmi Doe", greeting_name="Amma",
                         timezone="Asia/Kolkata")
    db.add(mother)
    db.commit()

    metformin = Medicine(care_profile_id=mother.id, display_name="Metformin", total_price=450, created_at=_at(3))
    vitamin = Medicine(care_profile_id=mother.id, display_name="Vitamin D", unit_price=10, total_medicine_count=30,
                       created_at=_at(20))
    old = Medicine(care_profile_id=mother.id, display_name="Old", total_price=999, created_at=_at(20, month=9))
    db.add_all([metformin, vitamin, old])
    db.commit()
    for day, status in ((1, "taken"), (2, "taken"), (3, "missed"), (4, "skipped"), (5, "taken")):
        db.add(MedicineDose(family_id=family.id, care_profile_id=mother.id, medicine_id=metformin.id,
                            dose_date=date(2026, 10, day), slot="morning", status=status, source="chatbot"))
    db.add(MedicineDose(family_id=family.id, care_profile_id=mother.id, medicine_id=vitamin.id,
                        dose_date=date(2026, 10, 6), slot="night", status="taken", source="manual"))
    db.add(MedicineDose(family_id=family.id, care_profile_id=mother.id, medicine_id=vitamin.id,
                        dose_date=date(2026, 11, 1), slot="night", status="taken", source="manual"))  # next month

    db.add(Appointment(family_id=family.id, care_profile_id=mother.id, provider="Dr Rao", reason="Review",
                       scheduled_date=date(2026, 10, 12), start_time="10:00", status="completed", fee=800,
                       doctor_notes="Sugar is under control. Walk 20 minutes daily."))
    db.add(Appointment(family_id=family.id, care_profile_id=mother.id, provider="Dr Gone", reason="Review",
                       scheduled_date=date(2026, 10, 14), start_time="10:00", status="cancelled", fee=500))
    db.add(InsurancePolicy(family_id=family.id, care_profile_id=mother.id, policy_type="health", insurer="Star",
                           premium=12000, renewal_date=date(2027, 10, 15), last_renewed_on=date(2026, 10, 15)))

    talked = HealthCheckin(family_id=family.id, care_profile_id=mother.id, parent_user_id=parent.id,
                           checkin_date=date(2026, 10, 2))
    urgent = HealthCheckin(family_id=family.id, care_profile_id=mother.id, parent_user_id=parent.id,
                           checkin_date=date(2026, 10, 9), urgent=True, health_text="Dizzy and fell in the bathroom")
    silent = HealthCheckin(family_id=family.id, care_profile_id=mother.id, parent_user_id=parent.id,
                           checkin_date=date(2026, 10, 10))
    db.add_all([talked, urgent, silent])
    db.commit()
    for c, texts in ((talked, ["I am fine", "Took my tablet"]), (urgent, ["I feel dizzy"])):
        for i, t in enumerate(texts):
            db.add(ChatMessage(checkin_id=c.id, sender="parent", text=t, language="en", seq=i * 2 + 1))
            db.add(ChatMessage(checkin_id=c.id, sender="bot", text="ok", language="en", seq=i * 2 + 2))
    db.add(ChatMessage(checkin_id=silent.id, sender="bot", text="Good morning", language="en", seq=1))
    db.add(Emergency(family_id=family.id, care_profile_id=mother.id, text="Chest pain", source="button",
                     created_at=_at(20), status="completed"))
    db.add(ConversationSummary(family_id=family.id, care_profile_id=mother.id, checkin_id=talked.id, from_seq=1,
                               to_seq=4, summary="Amma said she slept well and had idli.", source="rules",
                               created_at=_at(2), important=[{"title": "Knee pain again", "priority": "high"}]))
    db.add(MealLog(family_id=family.id, care_profile_id=mother.id, log_date=date(2026, 10, 2),
                   meals="breakfast,lunch", text="Idli and rice with sambar"))
    db.add(MealLog(family_id=family.id, care_profile_id=mother.id, log_date=date(2026, 10, 3),
                   meals="dinner", text="Skipped dinner, not hungry"))
    db.commit()

    def ask(text, user=manager, conversation_id=None):
        headers = {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}
        return client.post(f"/api/families/{family.id}/chat",
                           json={"text": text, "conversation_id": conversation_id}, headers=headers)

    return {"ask": ask, "db": db, "family": family, "manager": manager, "viewer": viewer, "client": client}


def test_the_analysis_card(home):
    r = home["ask"]("Give me the analysis for October 2026")
    assert r.status_code == 200, r.text
    body = r.json()
    card = body["card"]
    assert card["kind"] == "monthly_analysis"
    assert card["period"] == {"start": "2026-10-01", "end": "2026-10-31", "label": "October 2026"}
    assert card["parent"]["name"] == "Lakshmi Doe"

    med = card["medicines"]
    assert (med["taken"], med["missed"], med["skipped"], med["recorded"], med["taken_percent"]) == (4, 1, 1, 6, 67)
    assert med["by_medicine"][0] == {"name": "Metformin", "taken": 3, "missed": 1, "skipped": 1}

    spend = card["spending"]
    assert spend["medicines"] == 750  # 450 + 10 × 30; September's medicine is not counted
    assert spend["appointments"] == 800  # the cancelled visit is not counted
    assert spend["insurance"] == 12000
    assert spend["total"] == 13550
    assert spend["items"][0]["label"] == "Insurance: Star"

    assert card["conversations"] == {"conversations": 2, "days_talked": 2, "days_in_month": 31, "parent_messages": 3}
    kinds = [(i["kind"], i["text"]) for i in card["incidents"]]
    assert ("urgent", "Dizzy and fell in the bathroom") in kinds
    assert ("emergency", "Chest pain") in kinds
    assert ("important", "Knee pain again") in kinds

    diet = card["diet"]
    assert diet["days_reported"] == 2
    assert diet["meals"] == {"breakfast": 1, "lunch": 1, "dinner": 0}
    assert diet["skipped"] == 1
    assert "skipped" in diet["summary"]
    sources = {n["source"] for n in card["notes"]}
    assert sources == {"Doctor (Dr Rao)", "Chat summary"}

    assert body["source"] == "rules"
    assert body["reply"] == card["overview"]
    assert "took 4 of 6 recorded doses (67%)" in body["reply"]
    assert "₹13,550" in body["reply"]


def test_the_card_is_saved_with_the_chat(home):
    out = home["ask"]("October 2026 analysis").json()
    h = {"Authorization": f"Bearer {create_auth_session(home['db'], home['manager'].id)}"}
    saved = home["client"].get(
        f"/api/families/{home['family'].id}/chat/conversations/{out['conversation_id']}", headers=h
    ).json()
    assert saved["messages"][0]["card"] is None
    assert saved["messages"][1]["card"]["spending"]["total"] == 13550


def test_a_viewer_sees_the_analysis_too(home):
    card = home["ask"]("October 2026 analysis", user=home["viewer"]).json()["card"]
    assert card["spending"]["insurance"] == 12000  # Viewers may view reports
    assert card["medicines"]["taken"] == 4


def test_sections_follow_permissions(home):
    db = home["db"]
    role = db.query(Role).filter_by(family_id=home["family"].id, name="Viewer").one()
    from app.models.role import RolePermission  # noqa: PLC0415

    db.query(RolePermission).filter(RolePermission.role_id == role.id,
                                    RolePermission.permission.in_(
                                        ["medicines.view", "appointments.view", "reports.view"])).delete()
    db.commit()
    card = home["ask"]("October 2026 analysis", user=home["viewer"]).json()["card"]
    assert card["medicines"] is None
    assert card["spending"] is None
    assert all(not n["source"].startswith("Doctor") for n in card["notes"])


def test_gemini_writes_the_overview(home, monkeypatch):
    from app.services import understanding  # noqa: PLC0415

    monkeypatch.setattr(settings, "gemini_api_key", "k")
    seen = {}

    def fake(prompt):
        seen["prompt"] = prompt
        return {"overview": "A steady month for Amma.", "diet": "Mostly idli and rice."}

    monkeypatch.setattr(understanding, "ask_gemini", fake)
    body = home["ask"]("October 2026 analysis").json()
    assert body["reply"] == "A steady month for Amma."
    assert body["source"] == "ai"
    assert body["card"]["diet"]["summary"] == "Mostly idli and rice."
    assert "Metformin" in seen["prompt"]


def test_an_empty_month(home):
    card = home["ask"]("analysis for March 2026").json()["card"]
    assert card["medicines"]["recorded"] == 0
    assert card["spending"]["total"] == 0
    assert card["incidents"] == []
    assert card["diet"]["summary"] is None
    assert "No medicine doses were recorded" in card["overview"]
    assert "no major incidents" in card["overview"]
