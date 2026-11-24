"""Family dashboard: response shape, medicine stock days left, today's medicines, next appointment, family isolation."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.models.dose import MedicineDose
from app.models.medicine import Medicine
from app.models.prescription_scan import MedicineReminder
from app.models.user import User
from app.services import doses as doses_svc
from app.services import families as families_svc
from app.services.auth import create_auth_session

EXPECTED_KEYS = {
    "parents",
    "selected_care_profile_id",
    "on_date",
    "daily_medicine_count",
    "medicines_today",
    "today_schedule",
    "medicine_stock",
    "next_appointment",
    "emergency",
    "emergencies",
    "recent_activity",
}


def _med(db, profile, name, quantity, times=(), purpose=None, instructions=None):
    medicine = Medicine(
        care_profile_id=profile.id,
        display_name=name,
        quantity_remaining=quantity,
        purpose=purpose,
        instructions_text=instructions,
        active=True,
    )
    db.add(medicine)
    db.commit()
    for t in times:
        db.add(MedicineReminder(medicine_id=medicine.id, time_of_day=t, active=True))
    db.commit()
    return medicine


def _appt(db, family, profile, days_from_today, reason, status="scheduled", start="10:30"):
    today = doses_svc.today_for(profile, datetime.now(timezone.utc))
    appointment = Appointment(
        family_id=family.id,
        care_profile_id=profile.id,
        scheduled_date=today + timedelta(days=days_from_today),
        start_time=start,
        provider="Dr. S. Narayanan",
        reason=reason,
        notes="",
        status=status,
        location="City Care Hospital",
    )
    db.add(appointment)
    db.commit()
    return appointment


@pytest.fixture()
def dashboard_setup(db_session):
    manager = User(email="manager@example.com", display_name="Vikram")
    stranger = User(email="stranger@example.com", display_name="Stranger")
    db_session.add_all([manager, stranger])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Singh family")
    other_family = families_svc.create_family(db_session, stranger, "Other family")

    appa = CareProfile(family_id=family.id, display_name="Appa", greeting_name="Appa", timezone="Asia/Kolkata")
    amma = CareProfile(family_id=family.id, display_name="Amma", greeting_name="Amma", timezone="Asia/Kolkata")
    rival = CareProfile(
        family_id=other_family.id, display_name="Rival", greeting_name="Rival", timezone="Asia/Kolkata"
    )
    db_session.add_all([appa, amma, rival])
    db_session.commit()

    amlodipine = _med(
        db_session, appa, "Amlodipine", quantity=14, times=("08:00", "20:00"),
        purpose="BP Control", instructions="5 mg",
    )
    metformin = _med(db_session, appa, "Metformin", quantity=30, times=("08:00",), purpose="Diabetes")
    vitamin = _med(db_session, appa, "Vitamin D", quantity=None)
    _med(db_session, amma, "Amma pill", quantity=3, times=("09:00",))
    _med(db_session, rival, "Secret drug", quantity=1, times=("09:00",))

    return {
        "manager": manager,
        "stranger": stranger,
        "family": family,
        "other_family": other_family,
        "appa": appa,
        "amma": amma,
        "rival": rival,
        "amlodipine": amlodipine,
        "metformin": metformin,
        "vitamin": vitamin,
    }


def _auth(db, user: User) -> dict:
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _get(client, db, user, family_id, **params):
    return client.get(
        f"/api/families/{family_id}/dashboard",
        params=params,
        headers=_auth(db, user),
    )


def test_response_shape(client, db_session, dashboard_setup):
    s = dashboard_setup
    response = _get(client, db_session, s["manager"], s["family"].id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == EXPECTED_KEYS
    assert [p["display_name"] for p in body["parents"]] == ["Appa", "Amma"]
    parent = body["parents"][0]
    assert set(parent) == {
        "care_profile_id", "display_name", "relationship", "age", "photo_url",
        "known_health_conditions", "primary_caregiver_name", "all_good", "gender", "has_photo",
    }
    assert body["selected_care_profile_id"] == s["appa"].id
    assert body["daily_medicine_count"] == 3
    assert set(body["medicines_today"]) == {"taken", "total"}
    assert set(body["emergency"]) == {"active", "last_check_at"}
    assert body["on_date"] == doses_svc.today_for(s["appa"], datetime.now(timezone.utc)).isoformat()


def test_medicine_stock_days_left_and_low_flag(client, db_session, dashboard_setup):
    s = dashboard_setup
    body = _get(client, db_session, s["manager"], s["family"].id).json()
    stock = {m["display_name"]: m for m in body["medicine_stock"]}
    assert set(stock) == {"Amlodipine", "Metformin", "Vitamin D"}

    amlodipine = stock["Amlodipine"]
    assert amlodipine["days_left"] == 7  # 14 tablets, two doses a day
    assert amlodipine["low"] is True
    assert amlodipine["purpose"] == "BP Control"
    assert amlodipine["instructions_text"] == "5 mg"
    assert amlodipine["quantity_remaining"] == 14

    metformin = stock["Metformin"]
    assert metformin["days_left"] == 30  # 30 tablets, one dose a day
    assert metformin["low"] is False

    vitamin = stock["Vitamin D"]
    assert vitamin["days_left"] is None
    assert vitamin["low"] is False


def test_medicines_today_taken_and_total(client, db_session, dashboard_setup):
    s = dashboard_setup
    now = datetime.now(timezone.utc)
    doses_svc.record_dose(
        db_session, s["appa"], s["amlodipine"].id, "08:00", "taken", s["manager"].id, "manual", now
    )
    body = _get(client, db_session, s["manager"], s["family"].id).json()
    # Amlodipine 08:00 and 20:00, Metformin 08:00, Vitamin D "any" = 4 slots today.
    assert body["medicines_today"] == {"taken": 1, "total": 4}
    taken = [i for i in body["today_schedule"] if i["status"] == "taken"]
    assert [(i["medicine_name"], i["slot"]) for i in taken] == [("Amlodipine", "08:00")]
    # A slot with no answer yet has status null; the dashboard page shows it as "Pending".
    assert {i["status"] for i in body["today_schedule"]} == {"taken", None}


def test_next_appointment_is_earliest_upcoming_scheduled(client, db_session, dashboard_setup):
    s = dashboard_setup
    _appt(db_session, s["family"], s["appa"], -2, "Old visit")
    _appt(db_session, s["family"], s["appa"], 1, "Cancelled visit", status="cancelled")
    soonest = _appt(db_session, s["family"], s["appa"], 5, "Cardiologist Consultation")
    _appt(db_session, s["family"], s["appa"], 9, "Later visit")

    body = _get(client, db_session, s["manager"], s["family"].id).json()
    nxt = body["next_appointment"]
    assert nxt["id"] == soonest.id
    assert nxt["title"] == "Cardiologist Consultation"
    assert nxt["doctor"] == "Dr. S. Narayanan"
    assert nxt["location"] == "City Care Hospital"
    assert nxt["start_time"] == "10:30"
    expected = doses_svc.today_for(s["appa"], datetime.now(timezone.utc)) + timedelta(days=5)
    assert nxt["scheduled_date"] == expected.isoformat()


def test_next_appointment_null_when_none(client, db_session, dashboard_setup):
    s = dashboard_setup
    body = _get(client, db_session, s["manager"], s["family"].id).json()
    assert body["next_appointment"] is None


def test_parent_switcher_uses_care_profile_id(client, db_session, dashboard_setup):
    s = dashboard_setup
    body = _get(
        client, db_session, s["manager"], s["family"].id, care_profile_id=s["amma"].id
    ).json()
    assert body["selected_care_profile_id"] == s["amma"].id
    assert [m["display_name"] for m in body["medicine_stock"]] == ["Amma pill"]
    assert body["medicine_stock"][0]["low"] is True  # 3 tablets, one a day


def test_missed_dose_sets_emergency_active(client, db_session, dashboard_setup):
    s = dashboard_setup
    db_session.add(MedicineDose(
        family_id=s["family"].id, care_profile_id=s["appa"].id, medicine_id=s["metformin"].id,
        dose_date=doses_svc.today_for(s["appa"], datetime.now(timezone.utc)), slot="08:00",
        status="missed", recorded_at=datetime.now(timezone.utc),
        source="system",
    ))
    db_session.commit()
    body = _get(client, db_session, s["manager"], s["family"].id).json()
    assert body["emergency"]["active"] is True
    assert body["parents"][0]["all_good"] is False


def test_family_isolation(client, db_session, dashboard_setup):
    s = dashboard_setup
    body = _get(client, db_session, s["manager"], s["family"].id).json()
    text = str(body)
    assert "Secret drug" not in text
    assert "Rival" not in text
    assert all(p["care_profile_id"] != s["rival"].id for p in body["parents"])


def test_outsider_cannot_read_family_dashboard(client, db_session, dashboard_setup):
    s = dashboard_setup
    response = _get(client, db_session, s["stranger"], s["family"].id)
    assert response.status_code == 403


def test_care_profile_from_other_family_is_not_found(client, db_session, dashboard_setup):
    s = dashboard_setup
    response = _get(client, db_session, s["manager"], s["family"].id, care_profile_id=s["rival"].id)
    assert response.status_code == 404


def test_medicine_without_times_shows_each_part_of_the_day_taken(client, db_session, dashboard_setup):
    s = dashboard_setup
    now = datetime.now(timezone.utc)
    for slot in ("morning", "night"):
        doses_svc.record_dose(db_session, s["appa"], s["vitamin"].id, slot, "taken", s["manager"].id, "chatbot", now)
    body = _get(client, db_session, s["manager"], s["family"].id).json()
    vitamin = [(i["slot"], i["status"]) for i in body["today_schedule"] if i["medicine_name"] == "Vitamin D"]
    assert vitamin == [("morning", "taken"), ("night", "taken")]
    # Amlodipine 08:00 and 20:00, Metformin 08:00, Vitamin D morning and night.
    assert body["medicines_today"] == {"taken": 2, "total": 5}
    assert body["daily_medicine_count"] == 3


def test_parent_card_says_when_an_uploaded_photo_exists(client, db_session, dashboard_setup):
    from app.models.parent_onboarding_profile import ParentOnboardingProfile

    s = dashboard_setup
    before = _get(client, db_session, s["manager"], s["family"].id).json()["parents"]
    assert all(p["has_photo"] is False for p in before)
    db_session.add(ParentOnboardingProfile(
        care_profile_id=s["appa"].id, profile_photo_data=b"img", profile_photo_content_type="image/png",
    ))
    db_session.commit()
    after = {p["care_profile_id"]: p["has_photo"]
             for p in _get(client, db_session, s["manager"], s["family"].id).json()["parents"]}
    assert after[s["appa"].id] is True
