"""Dose history: the recorded answers behind the Overview chart and its report."""

from datetime import date, timedelta

from app.models.care_profile import CareProfile
from app.models.dose import MedicineDose
from app.models.medicine import Medicine
from app.models.user import User
from app.services import families as families_svc
from app.services.auth import create_auth_session

START = date(2026, 3, 1)


def test_dose_history(client, db_session):
    manager = User(email="m@example.com", display_name="Manager")
    stranger = User(email="s@example.com", display_name="Stranger")
    db_session.add_all([manager, stranger])
    db_session.commit()
    family = families_svc.create_family(db_session, manager, "Doe family")
    other = families_svc.create_family(db_session, stranger, "Other family")
    parent, rival = (
        CareProfile(family_id=f.id, display_name="P", greeting_name="P", timezone="Asia/Kolkata")
        for f in (family, other)
    )
    db_session.add_all([parent, rival])
    db_session.commit()
    removed = Medicine(care_profile_id=parent.id, display_name="Old pill", active=False)
    theirs = Medicine(care_profile_id=rival.id, display_name="Rival pill")
    db_session.add_all([removed, theirs])
    db_session.commit()

    def dose(f, profile, medicine, day, status):
        db_session.add(
            MedicineDose(
                family_id=f.id,
                care_profile_id=profile.id,
                medicine_id=medicine.id,
                dose_date=START + timedelta(days=day),
                slot="08:00",
                status=status,
                source="manual",
            )
        )

    for day, status in [(-1, "missed"), (0, "taken"), (6, "skipped"), (7, "taken")]:
        dose(family, parent, removed, day, status)
    dose(other, rival, theirs, 2, "taken")
    db_session.commit()

    def get(user=manager, profile=parent, days=6):
        headers = {"Authorization": f"Bearer {create_auth_session(db_session, user.id)}"}
        params = {
            "care_profile_id": profile.id,
            "start": START.isoformat(),
            "end": (START + timedelta(days=days)).isoformat(),
        }
        return client.get(f"/api/families/{family.id}/dose-history", params=params, headers=headers)

    r = get()
    assert r.status_code == 200, r.text
    assert [(d["dose_date"], d["medicine_name"], d["status"]) for d in r.json()] == [
        ("2026-03-01", "Old pill", "taken"),
        ("2026-03-07", "Old pill", "skipped"),
    ]
    assert get(days=89).status_code == 200
    assert get(days=90).status_code == 422
    assert get(days=-1).status_code == 422
    assert get(profile=rival).status_code == 404
    assert get(user=stranger).status_code in (403, 404)
