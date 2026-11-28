"""The parent's plan for today, refills from one yes, and what to tell the doctor before a visit."""

from datetime import date, timedelta

from sqlalchemy import select

from app.models.appointment import Appointment
from app.models.dose import MedicineDose
from app.models.health_note import HealthNote
from app.models.notification import Notification
from app.models.refill_request import RefillRequest
from app.models.task import Task
from app.services import today_plan as tp
from app.services.auth import create_auth_session

from tests.test_checkin_engine import NOW, SETUP_AT, world  # noqa: F401
from tests.test_parent_invites import email, family_setup  # noqa: F401

TODAY = date(2026, 11, 22)


def _stock(db, med, count):
    med.quantity_remaining = count
    med.updated_at = SETUP_AT
    db.commit()


def _taken(db, world, med, day):
    db.add(MedicineDose(family_id=world["family_id"], care_profile_id=world["profile"].id, medicine_id=med.id,
                        dose_date=day, slot="08:00", status="taken", source="chatbot", recorded_at=NOW))
    db.commit()


def _visit(db, world, day):
    a = Appointment(family_id=world["family_id"], care_profile_id=world["profile"].id, scheduled_date=day,
                    start_time="10:30", provider="Dr Rao", reason="BP review", status="scheduled")
    db.add(a)
    db.commit()
    return a


def test_today_lists_tablets_and_a_close_visit(db_session, world):
    _visit(db_session, world, TODAY + timedelta(days=1))
    _visit(db_session, world, TODAY + timedelta(days=9))
    plan = tp.today(db_session, world["ctx"], NOW)
    assert [(d.name, d.time) for d in plan.doses] == [("Amlodipine", "08:00"), ("Metformin", "08:00")]
    assert [v.provider for v in plan.visits] == ["Dr Rao"]


def test_stock_counts_down_with_doses_taken(db_session, world):
    med = world["meds"][0]
    _stock(db_session, med, 9)
    assert tp.refills(db_session, world["profile"], NOW, world["parent"].id) == []
    for d in (19, 20, 21):
        _taken(db_session, world, med, date(2026, 11, d))
    low = tp.refills(db_session, world["profile"], NOW, world["parent"].id)
    assert [(r.name, r.left, r.asked) for r in low] == [("Amlodipine", 6, False)]
    assert low[0].ask_name


def test_one_yes_makes_one_task_and_tells_the_family(db_session, world):
    med = world["meds"][0]
    _stock(db_session, med, 5)
    tp.ask_refill(db_session, world["ctx"], med.id, NOW)
    tp.ask_refill(db_session, world["ctx"], med.id, NOW)
    tasks = db_session.execute(select(Task).where(Task.title.like("Order Amlodipine%"))).scalars().all()
    assert len(tasks) == 1 and tasks[0].assigned_to_user_id
    assert len(db_session.execute(select(RefillRequest)).scalars().all()) == 1
    told = db_session.execute(select(Notification).where(Notification.type == "refill.requested")).scalars().all()
    assert {n.recipient_user_id for n in told} == world["member_ids"]
    assert tp.refills(db_session, world["profile"], NOW, world["parent"].id)[0].asked


def test_new_count_from_the_family_clears_the_request(db_session, world):
    med = world["meds"][0]
    _stock(db_session, med, 5)
    tp.ask_refill(db_session, world["ctx"], med.id, NOW)
    med.quantity_remaining = 60
    med.updated_at = NOW + timedelta(hours=1)
    db_session.commit()
    assert tp.refills(db_session, world["profile"], NOW, world["parent"].id) == []


def test_visit_points_from_the_last_two_weeks(db_session, world):
    for i, top in enumerate((150, 145, 120)):
        db_session.add(HealthNote(family_id=world["family_id"], care_profile_id=world["profile"].id,
                                  kind="reading", label="bp", value=f"{top}/90", value_num=top, source="chat",
                                  active=True, recorded_at=NOW - timedelta(days=3 - i)))
    db_session.add(HealthNote(family_id=world["family_id"], care_profile_id=world["profile"].id, kind="allergy",
                              label="penicillin", source="chat", active=True, recorded_at=NOW))
    db_session.add(MedicineDose(family_id=world["family_id"], care_profile_id=world["profile"].id,
                                medicine_id=world["meds"][1].id, dose_date=TODAY - timedelta(days=2), slot="08:00",
                                status="missed", source="system", recorded_at=NOW))
    db_session.commit()
    points = {p.kind: p for p in tp.visit_points(db_session, world["profile"], NOW)}
    assert points["bp_high"].count == 2
    assert (points["missed"].value, points["missed"].count) == ("Metformin", 1)
    assert points["allergy"].value == "penicillin"


def test_parent_api(client, db_session, world):
    _stock(db_session, world["meds"][0], 3)
    h = {"Authorization": f"Bearer {create_auth_session(db_session, world['parent'].id)}"}
    plan = client.get("/api/parent/today", headers=h).json()
    assert plan["refills"][0]["name"] == "Amlodipine"
    r = client.post(f"/api/parent/refills/{world['meds'][0].id}", headers=h)
    assert r.status_code == 200 and r.json()["asked"] is True
    assert client.post("/api/parent/refills/nope", headers=h).status_code == 404
    fam = f"/api/families/{world['family_id']}/care-profiles/{world['profile'].id}/weekly-summary/visit-prep"
    mh = {"Authorization": f"Bearer {create_auth_session(db_session, world['manager'].id)}"}
    body = client.get(fam, headers=mh).json()
    assert body["refills"][0]["asked"] is True
