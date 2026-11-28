"""The parent's circle: errands the family approves, posts, contacts and birthdays, the card, and privacy."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.conversation_summary import ConversationSummary
from app.models.notification import Notification
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.models.task import Task
from app.models.user import User
from app.services import care_circle as svc
from app.services import checkin as engine
from app.services import family_alerts, today_plan
from app.services.permissions import PermissionDenied
from tests.test_checkin_engine import NOW, no_meal_questions, offline, world  # noqa: F401
from tests.test_parent_invites import email, family_setup  # noqa: F401


def _carer(db):
    return db.execute(select(User).where(User.email == "carer@example.com")).scalar_one()


def _types(db, type_):
    return db.execute(select(Notification).where(Notification.type == type_)).scalars().all()


# ---------- help ----------

def test_asking_for_help_makes_one_task_and_tells_the_family(db_session, world):
    req = svc.ask_help(db_session, world["ctx"], "groceries", "Rice and dal", NOW)
    task = db_session.get(Task, req.task_id)
    assert task.title == "Order groceries for Amma" and task.description == "Rice and dal"
    assert {n.recipient_user_id for n in _types(db_session, "help.requested")} == world["member_ids"]
    again = svc.ask_help(db_session, world["ctx"], "groceries", None, NOW)
    assert again.id == req.id
    assert db_session.query(Task).count() == 1


def test_family_approves_help_and_the_task_becomes_theirs(db_session, world):
    req = svc.ask_help(db_session, world["ctx"], "cab", None, NOW)
    manager = world["manager"]
    svc.decide_help(db_session, manager.id, world["family_id"], req.id, "approved", 450, NOW)
    assert db_session.get(Task, req.task_id).assigned_to_user_id == manager.id
    assert float(req.amount) == 450
    told = _types(db_session, "help.decided")
    assert [n.recipient_user_id for n in told] == [world["parent"].id]


def test_declined_help_closes_the_task(db_session, world):
    req = svc.ask_help(db_session, world["ctx"], "nurse", None, NOW)
    svc.decide_help(db_session, world["manager"].id, world["family_id"], req.id, "declined", None, NOW)
    assert db_session.get(Task, req.task_id).status == "DONE"


def test_unknown_help_kind_is_refused(db_session, world):
    with pytest.raises(ValueError):
        svc.ask_help(db_session, world["ctx"], "spaceship", None, NOW)


# ---------- posts ----------

def test_family_post_reaches_the_parent_and_is_marked_seen(db_session, world):
    svc.add_post(db_session, world["manager"].id, world["family_id"], world["profile"].id, "text",
                 "Miss you, Amma!", None, None, NOW)
    posts = svc.parent_posts(db_session, world["ctx"], NOW)
    assert [p.text for p in posts] == ["Miss you, Amma!"]
    assert posts[0].seen_at is not None


def test_photo_post_needs_an_image(db_session, world):
    with pytest.raises(ValueError):
        svc.add_post(db_session, world["manager"].id, world["family_id"], world["profile"].id, "photo",
                     None, b"x", "text/plain", NOW)
    post = svc.add_post(db_session, world["manager"].id, world["family_id"], world["profile"].id, "photo",
                        None, b"\x89PNG", "image/png", NOW)
    assert svc.post_for_parent(db_session, world["ctx"], post.id).data == b"\x89PNG"


# ---------- contacts and birthdays ----------

def _friend(db, w, month, day, name="Kamala"):
    return svc.add_contact(db, w["manager"].id, w["family_id"], w["profile"].id,
                           {"name": name, "role": "friend", "phone": "+91 90000 22222",
                            "birthday_month": month, "birthday_day": day})


def test_birthday_today_and_tomorrow_show_in_the_today_plan(db_session, world):
    _friend(db_session, world, 11, 22)
    _friend(db_session, world, 11, 23, name="Lakshmi")
    _friend(db_session, world, 12, 25, name="Later")
    plan = today_plan.today(db_session, world["ctx"], NOW)
    assert [(b.name, b.today) for b in plan.birthdays] == [("Kamala", True), ("Lakshmi", False)]


def test_leap_day_birthday_falls_on_28_feb(db_session, world):
    c = _friend(db_session, world, 2, 29)
    assert svc.birthdays(db_session, world["profile"].id, date(2027, 2, 28), ahead=0)[0][0].id == c.id


def test_bad_birthday_is_refused(db_session, world):
    with pytest.raises(ValueError):
        _friend(db_session, world, 2, 30)


def test_caregiver_cannot_edit_contacts(db_session, world):
    with pytest.raises(PermissionDenied):
        svc.add_contact(db_session, _carer(db_session).id, world["family_id"], world["profile"].id,
                        {"name": "X", "role": "friend"})


def test_call_circle_lists_family_with_numbers_then_contacts(db_session, world):
    _friend(db_session, world, None, None)
    people = svc.call_circle(db_session, world["family_id"], world["profile"].id, world["parent"].id)
    assert ("Manager", "family") in [(p.name.split()[0], p.role) for p in people]
    assert people[-1].name == "Kamala"


def test_nudge_names_the_birthday_friend_first(db_session, world):
    _friend(db_session, world, 11, 22)
    assert svc.nudge(db_session, world["ctx"], NOW)["name"] == "Kamala"


def test_nudge_asks_to_call_family_after_quiet_days_else_walk(db_session, world):
    assert svc.nudge(db_session, world["ctx"], NOW)["kind"] == "call"
    svc.add_post(db_session, world["manager"].id, world["family_id"], world["profile"].id, "text", "Hi",
                 None, None, NOW - timedelta(hours=1))
    assert svc.nudge(db_session, world["ctx"], NOW)["kind"] == "walk"


# ---------- medical card ----------

def test_card_gathers_allergies_medicines_and_the_emergency_number(db_session, world):
    db_session.add(ParentOnboardingProfile(user_id=world["parent"].id, allergies="Penicillin",
                                           primary_doctor_name="Dr. Rao"))
    db_session.commit()
    card = svc.save_card(db_session, world["manager"].id, world["family_id"], world["profile"].id,
                         {"blood_group": "B+", "emergency_name": "Ravi", "emergency_phone": "+91 91111 00000"}, NOW)
    assert card["allergies"] == "Penicillin" and card["doctor"] == "Dr. Rao"
    assert card["medicines"] == ["Amlodipine", "Metformin"]
    assert card["emergency_contact"] == {"name": "Ravi", "phone": "+91 91111 00000"}
    assert card["blood_group"] == "B+"


# ---------- privacy ----------

def _checkin_with_words(db, w, words):
    engine.start_or_resume(db, w["ctx"], NOW)
    turn = engine.handle_parent_text(db, w["ctx"], words, NOW)
    return turn.checkin


def test_private_words_stay_out_of_family_updates(db_session, world, offline, no_meal_questions):
    svc.set_privacy(db_session, world["ctx"], {"share_words": False}, NOW)
    checkin = _checkin_with_words(db_session, world, "My knee hurts a little")
    family_alerts.notify_family_update(db_session, world["ctx"], checkin)
    updates = _types(db_session, "checkin.update")
    assert updates and all(n.payload["text"] is None for n in updates)
    body = family_alerts._summary_body(db_session, checkin, world["profile"])
    assert "knee" not in body and "private" in body


def test_shared_words_still_reach_the_family(db_session, world, offline, no_meal_questions):
    checkin = _checkin_with_words(db_session, world, "My knee hurts a little")
    family_alerts.notify_family_update(db_session, world["ctx"], checkin)
    assert any(n.payload["text"] for n in _types(db_session, "checkin.update"))


def test_private_chats_hide_summaries_unless_the_checkin_was_urgent(client, db_session, world):
    from tests.test_parent_invites import _auth  # noqa: PLC0415

    checkin = engine.start_or_resume(db_session, world["ctx"], NOW).checkin
    db_session.add(ConversationSummary(family_id=world["family_id"], care_profile_id=world["profile"].id,
                                       checkin_id=checkin.id, from_seq=1, to_seq=2, summary="talked",
                                       source="rule"))
    db_session.commit()
    url = f"/api/families/{world['family_id']}/conversation-summaries"
    headers = _auth(db_session, world["manager"])
    assert len(client.get(url, headers=headers).json()) == 1
    svc.set_privacy(db_session, world["ctx"], {"share_chats": False}, NOW)
    assert client.get(url, headers=headers).json() == []
    checkin.urgent = True
    db_session.commit()
    assert len(client.get(url, headers=headers).json()) == 1
