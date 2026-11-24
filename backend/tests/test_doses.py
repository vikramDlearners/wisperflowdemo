"""Dose log and due-today service."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.care_profile import CareProfile
from app.models.dose import MedicineDose
from app.models.medicine import Medicine
from app.models.prescription_scan import MedicineReminder
from app.models.user import User
from app.services import doses as svc
from app.services import families as families_svc
from app.services.auth import create_auth_session


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Manager")
    db_session.add(manager)
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    profile = CareProfile(
        family_id=family.id, display_name="Amma", greeting_name="Amma", timezone="Asia/Kolkata"
    )
    db_session.add(profile)
    db_session.commit()
    return {"manager": manager, "family": family, "profile": profile}


def _med(db, profile, name="Amlodipine", times=(), active=True):
    m = Medicine(care_profile_id=profile.id, display_name=name, active=active)
    db.add(m)
    db.commit()
    for t in times:
        db.add(MedicineReminder(medicine_id=m.id, time_of_day=t, active=True))
    db.commit()
    return m


# 09:00 IST on 2026-11-22 == 03:30 UTC
NOW = datetime(2026, 11, 22, 3, 30, tzinfo=timezone.utc)


def test_due_untaken_only_past_slots(db_session, setup):
    m = _med(db_session, setup["profile"], times=("08:00", "20:00"))
    due = svc.due_untaken(db_session, setup["profile"], NOW)
    assert [(d.medicine_id, d.slot) for d in due] == [(m.id, "08:00")]
    assert len(svc.doses_today(db_session, setup["profile"], NOW)) == 2


def test_no_reminders_uses_the_day_part_and_taken(db_session, setup):
    m = _med(db_session, setup["profile"])
    assert [d.slot for d in svc.due_untaken(db_session, setup["profile"], NOW)] == ["any"]
    svc.record_dose(db_session, setup["profile"], m.id, "morning", "taken", setup["manager"].id, "chatbot", NOW)
    assert svc.due_untaken(db_session, setup["profile"], NOW) == []


# 19:30 IST == 14:00 UTC; 13:00 IST == 07:30 UTC
EVENING = datetime(2026, 11, 22, 14, 0, tzinfo=timezone.utc)
AFTERNOON = datetime(2026, 11, 22, 7, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("when,part", [(NOW, "morning"), (AFTERNOON, "noon"), (EVENING, "night")])
def test_day_part_by_local_hour(setup, when, part):
    assert svc.day_part(svc.local_now(setup["profile"], when)) == part


def test_evening_answer_marks_only_the_night_dose(db_session, setup):
    m = _med(db_session, setup["profile"])
    [dose] = svc.current_doses(db_session, setup["profile"], EVENING, volunteered=True)
    assert dose.slot == "night"
    svc.record_dose(db_session, setup["profile"], m.id, dose.slot, "taken", setup["manager"].id, "chatbot", EVENING)
    shown = svc.doses_today(db_session, setup["profile"], EVENING)
    assert [(d.slot, d.status) for d in shown] == [("night", "taken")]


def test_morning_and_night_doses_are_separate(db_session, setup):
    m = _med(db_session, setup["profile"])
    svc.record_dose(db_session, setup["profile"], m.id, "morning", "taken", setup["manager"].id, "chatbot", NOW)
    # Not asked again by the bot after a dose today, but the parent can still report the night one.
    assert svc.current_doses(db_session, setup["profile"], EVENING) == []
    [dose] = svc.current_doses(db_session, setup["profile"], EVENING, volunteered=True)
    assert dose.slot == "night"
    svc.record_dose(db_session, setup["profile"], m.id, "night", "taken", setup["manager"].id, "chatbot", EVENING)
    shown = svc.doses_today(db_session, setup["profile"], EVENING)
    assert [(d.slot, d.status) for d in shown] == [("morning", "taken"), ("night", "taken")]


def test_timed_current_dose_is_the_latest_due_only(db_session, setup):
    _med(db_session, setup["profile"], times=("08:00", "20:00"))
    # 19:30: the 20:00 dose is within the early window; the unanswered 08:00 dose is not offered.
    assert [d.slot for d in svc.current_doses(db_session, setup["profile"], EVENING)] == ["20:00"]
    # 09:00: only the 08:00 dose.
    assert [d.slot for d in svc.current_doses(db_session, setup["profile"], NOW)] == ["08:00"]


def test_timed_taken_current_dose_is_not_offered_again(db_session, setup):
    m = _med(db_session, setup["profile"], times=("08:00", "20:00"))
    svc.record_dose(db_session, setup["profile"], m.id, "20:00", "taken", setup["manager"].id, "chatbot", EVENING)
    assert svc.current_doses(db_session, setup["profile"], EVENING, volunteered=True) == []


def test_day_part_slots_are_valid(db_session, setup):
    m = _med(db_session, setup["profile"])
    for slot in ("morning", "noon", "night", "any"):
        svc.record_dose(db_session, setup["profile"], m.id, slot, "taken", setup["manager"].id, "chatbot", NOW)
    with pytest.raises(ValueError):
        svc.record_dose(db_session, setup["profile"], m.id, "evening", "taken", setup["manager"].id, "chatbot", NOW)


def test_inactive_medicine_not_due(db_session, setup):
    _med(db_session, setup["profile"], active=False)
    assert svc.doses_today(db_session, setup["profile"], NOW) == []


def test_record_twice_updates(db_session, setup):
    m = _med(db_session, setup["profile"])
    args = (db_session, setup["profile"], m.id, "any")
    svc.record_dose(*args, "not_taken", setup["manager"].id, "chatbot", NOW)
    svc.record_dose(*args, "taken", setup["manager"].id, "manual", NOW)
    rows = db_session.execute(select(MedicineDose)).scalars().all()
    assert len(rows) == 1 and rows[0].status == "taken" and rows[0].source == "manual"


def test_dose_date_2350_ist_same_day(db_session, setup):
    m = _med(db_session, setup["profile"])
    now = datetime(2026, 11, 22, 18, 20, tzinfo=timezone.utc)
    d = svc.record_dose(db_session, setup["profile"], m.id, "any", "taken", setup["manager"].id, "chatbot", now)
    assert d.dose_date == date(2026, 11, 22)
    assert svc.local_now(setup["profile"], now).hour == 23


def test_remind_later_invalid(db_session, setup):
    m = _med(db_session, setup["profile"])
    with pytest.raises(ValueError):
        svc.set_remind_later(db_session, setup["profile"], m.id, "any", 7, NOW)


def test_remind_later_hides_until_due(db_session, setup):
    m = _med(db_session, setup["profile"])
    svc.set_remind_later(db_session, setup["profile"], m.id, "any", 15, NOW)
    assert svc.due_untaken(db_session, setup["profile"], NOW + timedelta(minutes=10)) == []
    assert len(svc.due_untaken(db_session, setup["profile"], NOW + timedelta(minutes=16))) == 1


def test_today_route(client, db_session, setup):
    m = _med(db_session, setup["profile"])
    svc.record_dose(db_session, setup["profile"], m.id, "any", "taken", setup["manager"].id, "chatbot",
                    datetime.now(timezone.utc))
    h = {"Authorization": f"Bearer {create_auth_session(db_session, setup['manager'].id)}"}
    r = client.get(
        f"/api/families/{setup['family'].id}/medicines/doses/today",
        params={"care_profile_id": setup["profile"].id}, headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body[0]["medicine_id"] == m.id and body[0]["status"] == "taken" and body[0]["slot"] == "any"
    assert client.get(
        f"/api/families/{setup['family'].id}/medicines/doses/today",
        params={"care_profile_id": setup["profile"].id},
    ).status_code in (401, 403)


def _rec(db, setup, m, slot="any", status="taken", source="chatbot", now=NOW):
    return svc.record_dose(db, setup["profile"], m.id, slot, status, setup["manager"].id, source, now)


def test_dose_date_ahead_of_utc(db_session, setup):
    m = _med(db_session, setup["profile"])
    d = _rec(db_session, setup, m, now=datetime(2026, 11, 22, 19, 0, tzinfo=timezone.utc))
    assert d.dose_date == date(2026, 11, 23)  # 00:30 IST next day


def test_dose_date_behind_utc(db_session, setup):
    setup["profile"].timezone = "America/New_York"
    db_session.commit()
    m = _med(db_session, setup["profile"])
    d = _rec(db_session, setup, m, now=datetime(2026, 11, 23, 2, 0, tzinfo=timezone.utc))
    assert d.dose_date == date(2026, 11, 22)  # 21:00 local previous day


def test_medicine_must_belong_to_profile_and_be_active(db_session, setup):
    other = CareProfile(family_id=setup["family"].id, display_name="Appa", greeting_name="Appa")
    db_session.add(other)
    db_session.commit()
    foreign = _med(db_session, other, name="Other")
    inactive = _med(db_session, setup["profile"], name="Old", active=False)
    for bad in (foreign.id, inactive.id, "missing-id"):
        with pytest.raises(ValueError):
            svc.record_dose(db_session, setup["profile"], bad, "any", "taken", None, "chatbot", NOW)
        with pytest.raises(ValueError):
            svc.set_remind_later(db_session, setup["profile"], bad, "any", 15, NOW)
    assert db_session.execute(select(MedicineDose)).scalars().all() == []


@pytest.mark.parametrize("status,source,slot", [
    ("takne", "chatbot", "any"),
    ("taken", "robot", "any"),
    ("taken", "chatbot", "9am"),
    ("taken", "chatbot", "24:00"),
    ("taken", "chatbot", "08:60"),
    ("taken", "chatbot", "8:00"),
])
def test_record_dose_validates_inputs(db_session, setup, status, source, slot):
    m = _med(db_session, setup["profile"])
    with pytest.raises(ValueError):
        svc.record_dose(db_session, setup["profile"], m.id, slot, status, None, source, NOW)


def test_remind_later_validates_slot(db_session, setup):
    m = _med(db_session, setup["profile"])
    with pytest.raises(ValueError):
        svc.set_remind_later(db_session, setup["profile"], m.id, "9am", 15, NOW)


def test_record_dose_racing_insert_updates_the_other_row(db_session, setup, monkeypatch):
    m = _med(db_session, setup["profile"], times=("08:00",))
    now = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)
    # Another request recorded the same slot first; this one did not see it when it looked.
    svc.record_dose(db_session, setup["profile"], m.id, "08:00", "not_taken", None, "chatbot", now)
    real = svc._existing
    calls = []

    def stale_first(db, medicine_id, day, slot):
        calls.append(1)
        return None if len(calls) == 1 else real(db, medicine_id, day, slot)

    monkeypatch.setattr(svc, "_existing", stale_first)
    row = svc.record_dose(db_session, setup["profile"], m.id, "08:00", "taken", setup["manager"].id, "manual",
                          now + timedelta(minutes=5))
    assert row.status == "taken" and row.source == "manual"
    rows = db_session.execute(select(MedicineDose)).scalars().all()
    assert len(rows) == 1 and rows[0].status == "taken"


def _post_dose(client, setup, headers, **body):
    return client.post(
        f"/api/families/{setup['family'].id}/medicines/doses",
        json={"care_profile_id": setup["profile"].id, "slot": "any", "status": "taken", **body},
        headers=headers,
    )


def test_caregiver_records_and_corrects_a_dose(client, db_session, setup):
    m = _med(db_session, setup["profile"], times=("00:00",))
    h = {"Authorization": f"Bearer {create_auth_session(db_session, setup['manager'].id)}"}
    assert _post_dose(client, setup, h, medicine_id=m.id, slot="00:00", status="skipped").status_code == 201
    r = _post_dose(client, setup, h, medicine_id=m.id, slot="00:00")
    assert r.status_code == 201, r.text
    db_session.expire_all()
    [row] = db_session.execute(select(MedicineDose)).scalars().all()
    assert (row.status, row.source, row.recorded_by_user_id) == ("taken", "manual", setup["manager"].id)


def test_caregiver_answer_replaces_missed(db_session, setup):
    m = _med(db_session, setup["profile"], times=("08:00",))
    db_session.add(MedicineDose(
        family_id=setup["family"].id, care_profile_id=setup["profile"].id, medicine_id=m.id,
        dose_date=date(2026, 11, 22), slot="08:00", status="missed", recorded_at=NOW, source="system",
    ))
    db_session.commit()
    row = svc.record_family_dose(
        db_session, setup["profile"], m.id, "08:00", "taken", setup["manager"].id, NOW
    )
    assert (row.status, row.source) == ("taken", "manual")


def test_caregiver_dose_without_times_uses_the_day_part(db_session, setup):
    m = _med(db_session, setup["profile"])
    row = svc.record_family_dose(db_session, setup["profile"], m.id, "any", "taken", setup["manager"].id, EVENING)
    assert row.slot == "night"


def test_caregiver_cannot_record_a_later_or_unknown_dose(db_session, setup):
    m = _med(db_session, setup["profile"], times=("20:00",))
    for slot in ("20:00", "08:00"):
        with pytest.raises(ValueError):
            svc.record_family_dose(
                db_session, setup["profile"], m.id, slot, "taken", setup["manager"].id, NOW
            )


def test_recording_a_dose_needs_permission_and_a_valid_status(client, db_session, setup):
    m = _med(db_session, setup["profile"])
    stranger = User(email="stranger@example.com", display_name="Stranger")
    db_session.add(stranger)
    db_session.commit()
    h = {"Authorization": f"Bearer {create_auth_session(db_session, stranger.id)}"}
    assert _post_dose(client, setup, h, medicine_id=m.id).status_code in (403, 404)
    h = {"Authorization": f"Bearer {create_auth_session(db_session, setup['manager'].id)}"}
    assert _post_dose(client, setup, h, medicine_id=m.id, status="missed").status_code == 422
    assert db_session.execute(select(MedicineDose)).scalars().all() == []
