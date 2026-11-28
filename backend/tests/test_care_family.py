"""Medical file and doctor links, siblings' money and visits, paperwork, the carer's day and video check-ins."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.appointment import Appointment
from app.models.meal import MealLog
from app.models.dose import MedicineDose
from app.models.notification import Notification
from app.models.user import User
from app.services import care_circle
from app.services import care_family as fam
from app.services import medical_file as mf
from app.services import video_calls as calls
from app.services.errors import LinkGone, NotFound
from app.services.permissions import PermissionDenied
from tests.test_checkin_engine import NOW, world  # noqa: F401
from tests.test_parent_invites import _auth, family_setup  # noqa: F401

PDF = b"%PDF-1.4\n" + b"0" * 100
SDP = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\n"


def _user(db, email):
    return db.execute(select(User).where(User.email == email)).scalar_one()


def _doc(db, w, title, text, day, kind="lab"):
    return mf.add_document(db, w["manager"].id, w["family_id"], w["profile"].id, kind=kind, title=title,
                           doc_date=day, text=text, data=None, mime=None, file_name=None, now=NOW)


# ---------- medical file ----------

def test_search_finds_the_latest_hba1c_first(db_session, world):
    _doc(db_session, world, "Lipid profile", "LDL 130 mg/dL", date(2026, 10, 1))
    _doc(db_session, world, "Diabetes panel", "HbA1c 7.9 %\nFasting sugar 140", date(2026, 3, 2))
    _doc(db_session, world, "Diabetes panel", "HbA1c 7.1 %\nFasting sugar 120", date(2026, 9, 5))
    rows = mf.search(db_session, world["manager"].id, world["family_id"], world["profile"].id,
                     "When was the last HbA1c?")
    assert [(r["doc"].doc_date, r["match"]) for r in rows] == [
        (date(2026, 9, 5), "HbA1c 7.1 %"), (date(2026, 3, 2), "HbA1c 7.9 %")]
    everything = mf.search(db_session, world["manager"].id, world["family_id"], world["profile"].id, None)
    assert len(everything) == 3


def test_upload_is_read_by_ai_when_set_up(db_session, world, monkeypatch):
    monkeypatch.setattr(mf.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(mf, "ask_gemini_image", lambda prompt, data, mime: {
        "kind": "discharge", "title": "Discharge summary, City Hospital", "doc_date": "2026-08-14",
        "text": "Diagnosis: pneumonia\nAmoxicillin 500 mg"})
    doc = mf.add_document(db_session, world["manager"].id, world["family_id"], world["profile"].id, kind=None,
                          title=None, doc_date=None, text=None, data=PDF, mime="application/pdf",
                          file_name="discharge.pdf", now=NOW)
    assert (doc.kind, doc.title, doc.doc_date) == ("discharge", "Discharge summary, City Hospital", date(2026, 8, 14))
    assert "Amoxicillin" in doc.text


def test_upload_without_ai_keeps_the_file_name_as_title(db_session, world, monkeypatch):
    monkeypatch.setattr(mf.settings, "gemini_api_key", "")
    doc = mf.add_document(db_session, world["manager"].id, world["family_id"], world["profile"].id, kind=None,
                          title=None, doc_date=None, text=None, data=PDF, mime="application/pdf",
                          file_name="scan.pdf", now=NOW)
    assert (doc.kind, doc.title) == ("other", "scan.pdf")


def test_a_fake_pdf_and_an_empty_document_are_refused(db_session, world):
    with pytest.raises(ValueError):
        mf.add_document(db_session, world["manager"].id, world["family_id"], world["profile"].id, kind=None,
                        title=None, doc_date=None, text=None, data=b"<html>", mime="application/pdf",
                        file_name="x.pdf", now=NOW)
    with pytest.raises(ValueError):
        _doc(db_session, world, "Empty", "  ", None)


def test_viewer_can_read_but_not_add(db_session, world):
    viewer = _user(db_session, "viewer@example.com")
    mf.search(db_session, viewer.id, world["family_id"], world["profile"].id, None)
    with pytest.raises(PermissionDenied):
        mf.add_document(db_session, viewer.id, world["family_id"], world["profile"].id, kind="lab", title="x",
                        doc_date=None, text="x", data=None, mime=None, file_name=None, now=NOW)


def test_doctor_link_shows_the_file_until_it_expires_or_is_turned_off(db_session, world):
    _doc(db_session, world, "Diabetes panel", "HbA1c 7.1 %", date(2026, 9, 5))
    link = mf.share(db_session, world["manager"].id, world["family_id"], world["profile"].id, 7, NOW)
    token = mf.token_for(link)
    _, card, docs = mf.shared_file(db_session, token, NOW)
    assert card["name"] == "Amma" and [d.title for d in docs] == ["Diabetes panel"]
    with pytest.raises(NotFound):
        mf.resolve(db_session, link.id + ".forged", NOW)
    with pytest.raises(LinkGone):
        mf.resolve(db_session, token, NOW + timedelta(days=8))
    mf.revoke(db_session, world["manager"].id, world["family_id"], link.id, NOW)
    with pytest.raises(LinkGone):
        mf.resolve(db_session, token, NOW)


def test_doctor_link_over_http(client, db_session, world):
    _doc(db_session, world, "Diabetes panel", "HbA1c 7.1 %", date(2026, 9, 5))
    headers = _auth(db_session, world["manager"])
    base = f"/api/families/{world['family_id']}/care-profiles/{world['profile'].id}/medical-file"
    made = client.post(f"{base}/links", json={"days": 1}, headers=headers)
    assert made.status_code == 201
    shared = client.get(f"/api/medical-file/{made.json()['token']}")
    assert shared.status_code == 200 and shared.json()["documents"][0]["title"] == "Diabetes panel"
    assert client.get(f"{base}?q=hba1c", headers=headers).json()[0]["match"] == "HbA1c 7.1 %"
    assert client.post(f"{base}/links", json={"days": 99}, headers=headers).status_code == 422


# ---------- siblings ----------

def test_expenses_are_split_between_the_siblings(db_session, world):
    viewer = _user(db_session, "viewer@example.com")
    m = world["manager"]
    fam.add_expense(db_session, m.id, world["family_id"], world["profile"].id, Decimal("3000"), "Physio", NOW.date(), None)
    fam.add_expense(db_session, m.id, world["family_id"], world["profile"].id, Decimal("1000"), "Groceries",
                    NOW.date(), viewer.id)
    out = fam.sharing(db_session, m.id, world["family_id"], world["profile"].id, NOW.date())
    assert (out["total"], out["share"]) == (4000.0, 2000.0)
    by = {b["name"]: b["balance"] for b in out["balances"]}
    assert by == {"Manager": 1000.0, "Viewer Doe": -1000.0}


def test_visits_and_who_went_to_the_last_appointment(db_session, world):
    m = world["manager"]
    appt = Appointment(family_id=world["family_id"], care_profile_id=world["profile"].id,
                       scheduled_date=NOW.date() - timedelta(days=3), start_time="10:00", provider="Dr Rao", reason="BP review",
                       status="completed")
    db_session.add(appt)
    db_session.commit()
    out = fam.sharing(db_session, m.id, world["family_id"], world["profile"].id, NOW.date())
    assert out["last_appointment"]["went"] is None
    fam.add_visit(db_session, m.id, world["family_id"], world["profile"].id, appt.scheduled_date, appt.id, None)
    fam.add_visit(db_session, m.id, world["family_id"], world["profile"].id, NOW.date(), None, "Sunday lunch")
    out = fam.sharing(db_session, m.id, world["family_id"], world["profile"].id, NOW.date())
    assert out["last_appointment"]["went"] == "Manager"
    assert {v["name"]: v["count"] for v in out["visits_this_month"]}["Manager"] == 2


# ---------- paperwork ----------

def test_usual_paperwork_and_a_yearly_chore_comes_back(db_session, world):
    m, fid, pid = world["manager"].id, world["family_id"], world["profile"].id
    assert len(fam.add_usual(db_session, m, fid, pid, NOW.date())) == 3
    assert fam.add_usual(db_session, m, fid, pid, NOW.date()) == []
    rows = fam.paperwork(db_session, m, fid, pid, NOW.date())
    life = next(r for r in rows if r["kind"] == "life_certificate")
    assert life["due_date"] == date(2026, 11, 30) and life["days_left"] == 8
    nxt = fam.done_paperwork(db_session, m, fid, life["id"], NOW.date())
    assert nxt.due_date == date(2027, 11, 30)


# ---------- carer ----------

def test_carer_ticks_meals_and_medicines_and_flags_a_concern(db_session, world):
    carer = _user(db_session, "carer@example.com")
    fid, pid = world["family_id"], world["profile"].id
    fam.carer_meal(db_session, carer.id, fid, pid, "breakfast", None, NOW)
    med = world["meds"][0]
    fam.carer_dose(db_session, carer.id, fid, pid, med.id, "08:00", "taken", NOW)
    day = fam.carer_day(db_session, carer.id, fid, pid, NOW)
    assert {m["meal"]: m["done"] for m in day["meals"]}["breakfast"] is True
    assert next(d for d in day["doses"] if d["medicine_id"] == med.id)["status"] == "taken"
    assert db_session.query(MealLog).one().recorded_by_user_id == carer.id
    assert db_session.query(MedicineDose).one().recorded_by_user_id == carer.id
    fam.carer_report(db_session, carer.id, fid, pid, "concern", "Amma felt dizzy after lunch", NOW)
    told = db_session.execute(select(Notification).where(Notification.type == "carer_concern")).scalars().all()
    assert {n.recipient_user_id for n in told} == world["member_ids"] - {carer.id}


def test_viewer_cannot_use_the_carer_day(db_session, world):
    viewer = _user(db_session, "viewer@example.com")
    with pytest.raises(PermissionDenied):
        fam.carer_day(db_session, viewer.id, world["family_id"], world["profile"].id, NOW)


# ---------- video ----------

def test_video_call_rings_is_answered_and_ends(db_session, world):
    call = calls.start(db_session, world["manager"].id, world["family_id"], world["profile"].id, SDP, NOW)
    ring = calls.incoming(db_session, world["ctx"], NOW + timedelta(seconds=5))
    assert ring["id"] == call.id and ring["caller"] == "Manager" and ring["auto_answer"] is False
    calls.answer(db_session, world["ctx"], call.id, SDP, NOW + timedelta(seconds=6))
    assert calls.family_call(db_session, world["manager"].id, world["family_id"], call.id, NOW).status == "live"
    assert calls.incoming(db_session, world["ctx"], NOW) is None
    calls.hang_up(call, db_session, NOW)
    assert call.status == "ended"


def test_auto_answer_follows_the_parents_choice_and_ringing_stops(db_session, world):
    care_circle.set_privacy(db_session, world["ctx"], {"video_auto_answer": True}, NOW)
    calls.start(db_session, world["manager"].id, world["family_id"], world["profile"].id, SDP, NOW)
    assert calls.incoming(db_session, world["ctx"], NOW)["auto_answer"] is True
    assert calls.incoming(db_session, world["ctx"], NOW + timedelta(seconds=61)) is None
    with pytest.raises(ValueError):
        calls.start(db_session, world["manager"].id, world["family_id"], world["profile"].id, "hello", NOW)
