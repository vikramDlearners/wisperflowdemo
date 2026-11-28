"""Parent notes: save a note, remind yourself, or hand it to a family member as a task (+ optional reminder)."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.care_profile import CareProfile
from app.models.notification import Notification
from app.models.parent_note import ParentNote
from app.models.role import Role
from app.models.task import Task
from app.models.user import User
from app.services import families as families_svc
from app.services import parent_notes as svc
from app.services.adapters import messaging
from app.services.auth import create_auth_session

URL = "/api/parent/notes"


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Priya", phone="+91 90000 11111")
    outsider = User(email="o@example.com", display_name="Outsider")
    db_session.add_all([manager, outsider])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Rao family")
    parent_role = db_session.execute(
        select(Role).where(Role.family_id == family.id, Role.name == "Parent")
    ).scalar_one()
    viewer_role = db_session.execute(
        select(Role).where(Role.family_id == family.id, Role.name == "Viewer")
    ).scalar_one()
    parent_m = families_svc.add_member(db_session, manager.id, family.id, "appa@example.com", parent_role.id, "Appa")
    viewer_m = families_svc.add_member(db_session, manager.id, family.id, "rahul@example.com", viewer_role.id, "Rahul")
    parent = db_session.get(User, parent_m.user_id)
    parent.phone = "+91 98765 43210"
    profile = CareProfile(family_id=family.id, display_name="Arjun Rao", greeting_name="Appa",
                          linked_user_id=parent.id)
    db_session.add(profile)
    db_session.commit()
    for provider in (messaging._whatsapp_provider, messaging._sms_provider):
        provider.outbox.clear()
    return {"family": family, "parent": parent, "manager": manager, "viewer": db_session.get(User, viewer_m.user_id),
            "outsider": outsider, "profile": profile}


def _h(db, user):
    return {"Authorization": f"Bearer {create_auth_session(db, user.id)}"}


def _later(minutes=60):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _notes_for(db, user):
    return db.execute(select(Notification).where(Notification.recipient_user_id == user.id)).scalars().all()


# ---------- notes for myself ----------

def test_plain_note_has_no_reminder_or_task(client, db_session, setup):
    r = client.post(URL, json={"text": "  I have kept my medicines in the drawer.  "},
                    headers=_h(db_session, setup["parent"]))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["text"] == "I have kept my medicines in the drawer."
    assert body["remind_at"] is None and body["remind_user_id"] is None and body["task_id"] is None
    assert body["reminded"] is True  # nothing left to send
    assert db_session.execute(select(Task)).first() is None

    listed = client.get(URL, headers=_h(db_session, setup["parent"])).json()
    assert [n["text"] for n in listed] == ["I have kept my medicines in the drawer."]


def test_reminder_for_myself_is_sent_once_at_the_time(client, db_session, setup):
    remind_at = datetime.now(timezone.utc) + timedelta(hours=2)
    r = client.post(URL, json={"text": "Take my medicines at 6 pm", "remind_at": remind_at.isoformat()},
                    headers=_h(db_session, setup["parent"]))
    assert r.status_code == 201, r.text
    assert r.json()["reminded"] is False

    assert svc.deliver_due_reminders(db_session, remind_at - timedelta(minutes=1)) == 0
    assert svc.deliver_due_reminders(db_session, remind_at) == 1
    assert svc.deliver_due_reminders(db_session, remind_at + timedelta(minutes=5)) == 0  # only once

    sent = [m for m in messaging._whatsapp_provider.outbox]
    assert [m.to for m in sent] == ["+91 98765 43210"]
    assert "Take my medicines at 6 pm" in sent[0].body and "Appa" in sent[0].body
    assert [m.to for m in messaging._sms_provider.outbox] == ["+91 98765 43210"]
    (note,) = _notes_for(db_session, setup["parent"])
    assert note.type == "note.reminder"
    assert client.get(URL, headers=_h(db_session, setup["parent"])).json()[0]["reminded"] is True


def test_picking_my_own_name_means_myself(client, db_session, setup):
    r = client.post(URL, json={"text": "Calcium after lunch", "remind_at": _later(),
                               "remind_user_id": setup["parent"].id, "send_reminder": True},
                    headers=_h(db_session, setup["parent"]))
    assert r.status_code == 201, r.text
    assert r.json()["remind_user_id"] is None and r.json()["task_id"] is None


# ---------- notes for someone else ----------

def test_note_for_someone_else_becomes_their_task(client, db_session, setup):
    remind_at = _later(90)
    r = client.post(URL, json={"text": "Buy calcium supplements", "remind_at": remind_at,
                               "remind_user_id": setup["manager"].id},
                    headers=_h(db_session, setup["parent"]))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["remind_user_name"] == "Priya" and body["send_reminder"] is False
    task = db_session.get(Task, body["task_id"])
    assert task.assigned_to_user_id == setup["manager"].id
    assert task.title == "Buy calcium supplements"
    assert task.description == "Note from Arjun Rao: Buy calcium supplements"
    assert task.status == "OPEN" and task.care_profile_id == setup["profile"].id
    assert task.due_at is not None
    assert [n.type for n in _notes_for(db_session, setup["manager"])] == ["task.assigned"]
    # No extra reminder was asked for: nothing more goes out later.
    assert body["reminded"] is True
    assert svc.deliver_due_reminders(db_session, datetime.now(timezone.utc) + timedelta(days=1)) == 0
    assert messaging._whatsapp_provider.outbox == []


def test_someone_else_can_also_get_a_reminder_at_the_time(client, db_session, setup):
    remind_at = datetime.now(timezone.utc) + timedelta(hours=3)
    r = client.post(URL, json={"text": "Pick up my prescription", "remind_at": remind_at.isoformat(),
                               "remind_user_id": setup["manager"].id, "send_reminder": True},
                    headers=_h(db_session, setup["parent"]))
    assert r.status_code == 201, r.text
    assert r.json()["reminded"] is False

    assert svc.deliver_due_reminders(db_session, remind_at) == 1
    assert [m.to for m in messaging._whatsapp_provider.outbox] == ["+91 90000 11111"]
    assert messaging._whatsapp_provider.outbox[0].body == "Reminder from Arjun Rao: Pick up my prescription"
    assert sorted(n.type for n in _notes_for(db_session, setup["manager"])) == ["note.reminder_for_you",
                                                                               "task.assigned"]
    assert _notes_for(db_session, setup["parent"]) == []


def test_reminder_without_a_time_is_sent_right_away(client, db_session, setup):
    r = client.post(URL, json={"text": "Please call me today", "remind_user_id": setup["viewer"].id,
                               "send_reminder": True},
                    headers=_h(db_session, setup["parent"]))
    assert r.status_code == 201, r.text
    assert r.json()["reminded"] is True
    types = sorted(n.type for n in _notes_for(db_session, setup["viewer"]))
    assert types == ["note.reminder_for_you", "task.assigned"]


def test_people_lists_family_but_not_the_parent(client, db_session, setup):
    r = client.get(f"{URL}/people", headers=_h(db_session, setup["parent"]))
    assert r.status_code == 200, r.text
    assert [p["display_name"] for p in r.json()] == ["Priya", "Rahul"]
    assert set(r.json()[0]) == {"user_id", "display_name", "relationship"}  # no emails or phones


# ---------- validation and access ----------

@pytest.mark.parametrize("payload,status,detail", [
    ({"text": ""}, 422, None),
    ({"text": "   "}, 400, "Please write your note first."),
    ({"text": "x" * 1001}, 422, None),
    ({"text": "Old", "remind_at": "2020-01-01T10:00:00+00:00"}, 400, "Please choose a reminder time in the future."),
])
def test_invalid_notes_are_rejected(client, db_session, setup, payload, status, detail):
    r = client.post(URL, json=payload, headers=_h(db_session, setup["parent"]))
    assert r.status_code == status, r.text
    if detail:
        assert r.json()["detail"] == detail
    assert db_session.execute(select(ParentNote)).first() is None


def test_cannot_send_a_note_outside_the_family(client, db_session, setup):
    r = client.post(URL, json={"text": "Hi", "remind_user_id": setup["outsider"].id},
                    headers=_h(db_session, setup["parent"]))
    assert r.status_code == 400
    assert r.json()["detail"] == "That person isn't an active member of your family."
    assert db_session.execute(select(Task)).first() is None


def test_delete_keeps_the_task_and_only_deletes_own_notes(client, db_session, setup):
    created = client.post(URL, json={"text": "Buy fruit", "remind_user_id": setup["manager"].id},
                          headers=_h(db_session, setup["parent"])).json()
    r = client.delete(f"{URL}/{created['id']}", headers=_h(db_session, setup["parent"]))
    assert r.status_code == 204
    assert client.get(URL, headers=_h(db_session, setup["parent"])).json() == []
    assert db_session.get(Task, created["task_id"]) is not None
    assert client.delete(f"{URL}/{created['id']}", headers=_h(db_session, setup["parent"])).status_code == 404


def test_not_a_parent_cannot_use_notes(client, db_session, setup):
    assert client.get(URL, headers=_h(db_session, setup["outsider"])).status_code == 409
    assert client.get(URL).status_code == 401
