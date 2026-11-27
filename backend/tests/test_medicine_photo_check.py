"""A parent photographs a medicine they are unsure about: which one it is, when to take it, and whether it was prescribed."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.api import parent as parent_api
from app.models.checkin import ChatMessage
from app.services import checkin as engine

from tests.test_checkin_engine import offline, world, no_meal_questions  # noqa: F401
from tests.test_parent_api import FakeTTS
from tests.test_parent_invites import _auth, email, family_setup  # noqa: F401

# 08:30 IST on 2026-11-22: the 08:00 doses are due now.
NOW = datetime(2026, 11, 22, 3, 0, tzinfo=timezone.utc)
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 32
URL = "/api/parent/checkin/medicine-photo?speak=false"


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch):
    monkeypatch.setattr(parent_api, "_now", lambda: NOW)
    monkeypatch.setattr(parent_api, "get_text_to_speech", lambda: FakeTTS(fail=True))


@pytest.fixture()
def gemini(monkeypatch):
    calls = []

    def answer(result):
        def fake(prompt, image, mime_type):
            calls.append((prompt, image, mime_type))
            if isinstance(result, Exception):
                raise result
            return result
        monkeypatch.setattr(engine, "ask_gemini_image", fake)
        return calls
    return answer


def _send(client, db_session, world, content_type="image/jpeg", data=JPEG):
    return client.post(URL, files={"file": ("pill.jpg", data, content_type)}, headers=_auth(db_session, world["parent"]))


def _texts(r):
    assert r.status_code == 200, r.text
    return [(m["text"], m["photos"]) for m in r.json()["messages"]]


def test_match_says_when_to_take_and_that_the_doctor_prescribed_it(client, db_session, world, gemini):
    med = world["meds"][0]
    med.prescription_image_data = JPEG
    med.image_data, med.image_content_type = JPEG, "image/jpeg"
    db_session.commit()
    calls = gemini({"name_seen": "Amlodipine 5 mg", "medicine_id": med.id})

    texts = _texts(_send(client, db_session, world))

    answer, schedule_line = texts[0][0].split("\n")[0], texts[0][0].split("\n")[1]
    assert answer == "This looks like Amlodipine."
    assert "Amlodipine" in schedule_line and "8:00" not in schedule_line  # due now, not "later at 8:00"
    assert texts[0][0].endswith("Your doctor prescribed it.")
    assert texts[1] == ("Here is the photo of Amlodipine.", True)
    # Gemini sees the parent's own list and the photo.
    prompt, image, mime_type = calls[0]
    assert med.id in prompt and "Metformin" in prompt
    assert (image, mime_type) == (JPEG, "image/jpeg")


def test_match_without_prescription_or_photo(client, db_session, world, gemini):
    gemini({"name_seen": "Metformin 500", "medicine_id": world["meds"][1].id})
    texts = _texts(_send(client, db_session, world))
    assert len(texts) == 1
    assert texts[0][0].startswith("This looks like Metformin.\n")
    assert texts[0][0].endswith("It is on your medicine list, but I don't have the doctor's prescription for it.")


def test_medicine_without_reminder_times_is_for_any_time_today(client, db_session, world, gemini):
    from app.models.prescription_scan import MedicineReminder
    for r in db_session.execute(select(MedicineReminder).where(
        MedicineReminder.medicine_id == world["meds"][1].id
    )).scalars():
        r.active = False
    db_session.commit()
    gemini({"name_seen": "Metformin", "medicine_id": world["meds"][1].id})
    assert _texts(_send(client, db_session, world)) == [(
        "This looks like Metformin.\nAny time today: Metformin.\n"
        "It is on your medicine list, but I don't have the doctor's prescription for it.",
        False,
    )]


def test_unknown_medicine_warns_not_to_take_it(client, db_session, world, gemini):
    gemini({"name_seen": "Dolo 650", "medicine_id": None})
    text = _texts(_send(client, db_session, world))[0][0]
    assert text.startswith('I read "Dolo 650" on it. It is not on your medicine list. Please don\'t take it')


def test_an_id_outside_the_parents_list_is_ignored(client, db_session, world, gemini):
    gemini({"name_seen": "Dolo 650", "medicine_id": "someone-elses-medicine"})
    text = _texts(_send(client, db_session, world))[0][0]
    assert "not on your medicine list" in text


def test_unreadable_photo(client, db_session, world, gemini):
    gemini({"name_seen": None, "medicine_id": None})
    assert _texts(_send(client, db_session, world)) == [
        ("I couldn't read the medicine name. Please take a clearer photo of the name on the strip or box.", False),
    ]


@pytest.mark.parametrize("error", [ValueError("no key"), RuntimeError("down")])
def test_gemini_unavailable(client, db_session, world, gemini, error):
    gemini(error)
    text = _texts(_send(client, db_session, world))[0][0]
    assert text.startswith("I can't read photos right now. Please ask ")


def test_no_gemini_key_needs_no_mock(client, db_session, world, offline):  # noqa: F811
    text = _texts(_send(client, db_session, world))[0][0]
    assert text.startswith("I can't read photos right now.")


def test_the_photo_turn_is_stored_in_the_chat(client, db_session, world, gemini):
    gemini({"name_seen": None, "medicine_id": None})
    _send(client, db_session, world)
    rows = db_session.execute(select(ChatMessage).order_by(ChatMessage.seq)).scalars().all()
    assert [(m.sender, m.text) for m in rows][-2:] == [
        ("parent", "I sent a photo of a medicine."),
        ("bot", "I couldn't read the medicine name. Please take a clearer photo of the name on the strip or box."),
    ]


@pytest.mark.parametrize("content_type,data,code", [
    ("application/pdf", JPEG, 415),
    ("image/jpeg", b"", 400),
])
def test_bad_uploads(client, db_session, world, gemini, content_type, data, code):
    calls = gemini({"name_seen": None, "medicine_id": None})
    assert _send(client, db_session, world, content_type, data).status_code == code
    assert calls == []
