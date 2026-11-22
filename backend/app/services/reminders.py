"""Reminder times (24-hour HH:MM) for a medicine. Setting them replaces all active ones."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.prescription_scan import MedicineReminder
from app.services.activity import log_activity
from app.services.care import _medicine_in_family
from app.services.permissions import require


def list_reminder_times(db: Session, medicine_id: str) -> list[str]:
    rows = db.execute(
        select(MedicineReminder.time_of_day).where(
            MedicineReminder.medicine_id == medicine_id, MedicineReminder.active.is_(True)
        )
    ).scalars()
    return sorted(set(rows))


def set_reminder_times(
    db: Session, actor_id: str, family_id: str, medicine_id: str, times: list[str]
) -> list[str]:
    require(db, actor_id, family_id, "medicines.edit")
    _medicine_in_family(db, family_id, medicine_id)
    new_times = sorted(set(times))
    for row in db.execute(
        select(MedicineReminder).where(
            MedicineReminder.medicine_id == medicine_id, MedicineReminder.active.is_(True)
        )
    ).scalars():
        row.active = False
    for t in new_times:
        db.add(MedicineReminder(medicine_id=medicine_id, time_of_day=t, active=True))
    log_activity(
        db, family_id, actor_id, "medicine.reminders_set", "medicine", medicine_id,
        {"times": new_times},
    )
    db.commit()
    return new_times
