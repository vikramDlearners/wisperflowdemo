"""Family chat is saved in the database: each member's conversations, every question and answer."""

import pytest

from app.models.family_chat import FamilyChatConversation, FamilyChatMessage
from app.models.membership import FamilyMember
from app.models.role import Role
from app.models.user import User
from app.services import families as families_svc
from app.services import family_chat
from app.services.auth import create_auth_session


@pytest.fixture()
def setup(db_session, monkeypatch):
    # Answers come from the rules, so the tests need no Gemini.
    monkeypatch.setattr(family_chat, "_gemini_reply", lambda *a, **k: None)
    manager = User(email="manager@example.com", display_name="Priya")
    carer = User(email="carer@example.com", display_name="Deepak")
    outsider = User(email="o@example.com", display_name="Outsider")
    db_session.add_all([manager, carer, outsider])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    caregiver = db_session.query(Role).filter_by(family_id=family.id, name="Caregiver").one()
    db_session.add(FamilyMember(family_id=family.id, user_id=carer.id, role_id=caregiver.id, status="active"))
    db_session.commit()

    def h(u):
        return {"Authorization": f"Bearer {create_auth_session(db_session, u.id)}"}

    return {"base": f"/api/families/{family.id}/chat", "manager": manager, "carer": carer, "outsider": outsider,
            "h": h}


def _ask(client, s, text, user=None, conversation_id=None):
    body = {"text": text}
    if conversation_id:
        body["conversation_id"] = conversation_id
    r = client.post(s["base"], json=body, headers=s["h"](user or s["manager"]))
    assert r.status_code == 200, r.text
    return r.json()


def test_question_and_answer_are_saved(client, db_session, setup):
    out = _ask(client, setup, "Show my open tasks")
    assert out["reply"]
    cid = out["conversation_id"]
    convo = db_session.get(FamilyChatConversation, cid)
    assert convo.title == "Show my open tasks"
    rows = db_session.query(FamilyChatMessage).filter_by(conversation_id=cid).order_by(FamilyChatMessage.seq).all()
    assert [(m.role, m.text) for m in rows] == [("user", "Show my open tasks"), ("assistant", out["reply"])]


def test_follow_up_goes_into_the_same_conversation(client, setup):
    cid = _ask(client, setup, "How are things today?")["conversation_id"]
    again = _ask(client, setup, "What are the upcoming appointments?", conversation_id=cid)
    assert again["conversation_id"] == cid
    r = client.get(f"{setup['base']}/conversations/{cid}", headers=setup["h"](setup["manager"]))
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "How are things today?"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user", "assistant"]
    assert body["messages"][2]["text"] == "What are the upcoming appointments?"


def test_list_is_newest_first_and_private_to_the_member(client, setup):
    first = _ask(client, setup, "How are things today?")["conversation_id"]
    second = _ask(client, setup, "Show my open tasks")["conversation_id"]
    _ask(client, setup, "Which medicines need a refill?", user=setup["carer"])
    mine = client.get(f"{setup['base']}/conversations", headers=setup["h"](setup["manager"])).json()
    assert [c["id"] for c in mine] == [second, first]
    theirs = client.get(f"{setup['base']}/conversations", headers=setup["h"](setup["carer"])).json()
    assert [c["title"] for c in theirs] == ["Which medicines need a refill?"]
    # Another member cannot open or add to someone else's chat.
    assert client.get(f"{setup['base']}/conversations/{first}", headers=setup["h"](setup["carer"])).status_code == 404
    r = client.post(setup["base"], json={"text": "hi", "conversation_id": first}, headers=setup["h"](setup["carer"]))
    assert r.status_code == 404


def test_delete_removes_the_conversation_and_its_messages(client, db_session, setup):
    cid = _ask(client, setup, "How are things today?")["conversation_id"]
    url = f"{setup['base']}/conversations/{cid}"
    assert client.delete(url, headers=setup["h"](setup["carer"])).status_code == 404
    assert client.delete(url, headers=setup["h"](setup["manager"])).status_code == 204
    assert db_session.query(FamilyChatMessage).filter_by(conversation_id=cid).count() == 0
    assert client.get(url, headers=setup["h"](setup["manager"])).status_code == 404


def test_a_page_link_reply_is_saved(client, setup):
    r = client.post(f"{setup['base']}/log", headers=setup["h"](setup["manager"]),
                    json={"text": "Add a task", "reply": "You can do that here:", "destination": "task.add"})
    assert r.status_code == 200, r.text
    cid = r.json()["conversation_id"]
    msgs = client.get(f"{setup['base']}/conversations/{cid}", headers=setup["h"](setup["manager"])).json()["messages"]
    assert msgs[-1] == {**msgs[-1], "role": "assistant", "destination": "task.add"}


def test_import_from_this_browser(client, setup):
    r = client.post(f"{setup['base']}/conversations/import", headers=setup["h"](setup["manager"]), json={
        "conversations": [
            {"title": "Old chat", "messages": [
                {"role": "user", "text": "How are things?"},
                {"role": "assistant", "text": "All good.", "destination": None},
            ]},
            {"title": "Empty", "messages": []},
        ],
    })
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1
    listed = client.get(f"{setup['base']}/conversations", headers=setup["h"](setup["manager"])).json()
    assert [c["title"] for c in listed] == ["Old chat"]


def test_outsider_is_refused(client, setup):
    r = client.post(setup["base"], json={"text": "hi"}, headers=setup["h"](setup["outsider"]))
    assert r.status_code == 403
    assert client.get(f"{setup['base']}/conversations", headers=setup["h"](setup["outsider"])).status_code == 403
