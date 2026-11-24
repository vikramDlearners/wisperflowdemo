"""'Remind parent' sends today's untaken medicines to the parent on WhatsApp, as a text message and in the app."""

import pytest

from app.models.care_profile import CareProfile
from app.models.dose import MedicineDose
from app.models.medicine import Medicine
from app.models.notification import Notification
from app.models.user import User
from app.services import families as families_svc
from app.services.adapters import messaging
from app.services.auth import create_auth_session


@pytest.fixture()
def setup(db_session):
    manager = User(email="manager@example.com", display_name="Priya")
    parent = User(email="amma@example.com", display_name="Amma", phone="+91 98765 43210")
    outsider = User(email="o@example.com", display_name="Outsider")
    db_session.add_all([manager, parent, outsider])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    profile = CareProfile(family_id=family.id, display_name="Amma", greeting_name="Amma", linked_user_id=parent.id)
    db_session.add(profile)
    db_session.commit()
    medicine = Medicine(care_profile_id=profile.id, display_name="Amlodipine 5 mg", active=True)
    db_session.add(medicine)
    db_session.commit()
    messaging._sms_provider.outbox.clear()
    messaging._whatsapp_provider.outbox.clear()
    return {"family": family, "profile": profile, "parent": parent, "manager": manager, "outsider": outsider,
            "medicine": medicine, "url": f"/api/families/{family.id}/medicines/remind-parent"}


def _post(client, db, setup, user=None):
    return client.post(
        setup["url"],
        json={"care_profile_id": setup["profile"].id},
        headers={"Authorization": f"Bearer {create_auth_session(db, (user or setup['manager']).id)}"},
    )


def test_reminder_goes_to_whatsapp_sms_and_app(client, db_session, setup):
    r = _post(client, db_session, setup)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["channels"] == ["whatsapp", "sms", "app"]
    assert body["sent_to"] == "•••• 3210"
    assert body["medicines"] == ["Amlodipine 5 mg"]
    assert "Amlodipine 5 mg" in body["message"] and "Priya" in body["message"]

    assert [m.to for m in messaging._whatsapp_provider.outbox] == ["+91 98765 43210"]
    assert [m.to for m in messaging._sms_provider.outbox] == ["+91 98765 43210"]
    note = db_session.query(Notification).filter_by(recipient_user_id=setup["parent"].id).one()
    assert note.type == "medicine.reminder"


def test_without_a_phone_it_is_still_sent(client, db_session, setup):
    setup["parent"].phone = None
    db_session.commit()
    r = _post(client, db_session, setup)
    assert r.status_code == 200
    assert r.json()["channels"] == ["whatsapp", "sms", "app"]
    assert r.json()["sent_to"] is None
    assert len(messaging._sms_provider.outbox) == 1


def test_nothing_due_is_refused(client, db_session, setup):
    from datetime import datetime, timezone  # noqa: PLC0415

    from app.services import doses as doses_svc  # noqa: PLC0415

    now = datetime.now(timezone.utc)
    for d in doses_svc.doses_today(db_session, setup["profile"], now):
        db_session.add(MedicineDose(
            family_id=setup["family"].id, care_profile_id=setup["profile"].id, medicine_id=d.medicine_id,
            dose_date=doses_svc.local_now(setup["profile"], now).date(), slot=d.slot, status="taken",
            recorded_at=now, source="family",
        ))
    db_session.commit()
    r = _post(client, db_session, setup)
    assert r.status_code == 400
    assert "nothing to remind" in r.json()["detail"]


def test_outsider_is_refused(client, db_session, setup):
    assert _post(client, db_session, setup, user=setup["outsider"]).status_code == 403
