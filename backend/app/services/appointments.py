"""Appointments for a care recipient. The family is never in the URL: it is taken from the care profile (list) or from the appointment (get, update, delete), and membership is checked against that family with require()."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.services.activity import log_activity
from app.services.errors import NotFound
from app.services.permissions import require


def _clean(value):
    return value.strip() if isinstance(value, str) else value


def _profile(db: Session, care_profile_id: str) -> CareProfile:
    profile = db.get(CareProfile, care_profile_id)
    if profile is None:
        raise NotFound("Care recipient not found")
    return profile


def _profile_in_family(db: Session, family_id: str, care_profile_id: str) -> CareProfile:
    profile = _profile(db, care_profile_id)
    if profile.family_id != family_id:
        raise NotFound("Care recipient not found")
    return profile


def _appointment(db: Session, appointment_id: str) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise NotFound("Appointment not found")
    return appointment


def list_appointments(
    db: Session, actor_id: str, care_profile_id: str, today: date | None = None
) -> tuple[list[Appointment], list[Appointment]]:
    """Return (upcoming, past): upcoming is today or later, soonest first; past is earlier, most recent first."""
    profile = _profile(db, care_profile_id)
    require(db, actor_id, profile.family_id, "appointments.view")
    today = today or date.today()
    stmt = select(Appointment).where(Appointment.care_profile_id == care_profile_id)
    rows = list(db.execute(stmt).scalars())
    upcoming = sorted((a for a in rows if a.scheduled_date >= today), key=lambda a: a.scheduled_date)
    past = sorted((a for a in rows if a.scheduled_date < today), key=lambda a: a.scheduled_date, reverse=True)
    return upcoming, past


def create_appointment(
    db: Session,
    actor_id: str,
    family_id: str,
    care_recipient_id: str,
    scheduled_date: date,
    start_time: str,
    provider: str,
    reason: str,
    notes: str = "",
) -> Appointment:
    require(db, actor_id, family_id, "appointments.create")
    _profile_in_family(db, family_id, care_recipient_id)
    appointment = Appointment(
        family_id=family_id,
        care_profile_id=care_recipient_id,
        scheduled_date=scheduled_date,
        start_time=start_time.strip(),
        provider=provider.strip(),
        reason=reason.strip(),
        notes=notes or "",
        status="scheduled",
    )
    db.add(appointment)
    db.flush()
    log_activity(
        db, family_id, actor_id, "appointment.created", "appointment", appointment.id,
        {"scheduled_date": scheduled_date.isoformat()},
    )
    db.commit()
    return appointment


def get_appointment(db: Session, actor_id: str, appointment_id: str) -> Appointment:
    appointment = _appointment(db, appointment_id)
    require(db, actor_id, appointment.family_id, "appointments.view")
    return appointment


def update_appointment(
    db: Session, actor_id: str, appointment_id: str, changes: dict
) -> Appointment:
    """Apply a partial update. Null is rejected for every field except notes, which becomes an empty string."""
    appointment = _appointment(db, appointment_id)
    require(db, actor_id, appointment.family_id, "appointments.update")
    for key, value in changes.items():
        if value is None and key != "notes":
            raise ValueError(f"{key} cannot be null")
    if "care_recipient_id" in changes:
        _profile_in_family(db, appointment.family_id, changes["care_recipient_id"])
        appointment.care_profile_id = changes["care_recipient_id"]
    for key in ("scheduled_date", "start_time", "provider", "reason", "status"):
        if key in changes:
            setattr(appointment, key, _clean(changes[key]))
    if "notes" in changes:
        appointment.notes = changes["notes"] or ""
    log_activity(
        db, appointment.family_id, actor_id, "appointment.updated", "appointment", appointment.id,
        {"fields": sorted(changes)},
    )
    db.commit()
    return appointment


def delete_appointment(db: Session, actor_id: str, appointment_id: str) -> None:
    appointment = _appointment(db, appointment_id)
    require(db, actor_id, appointment.family_id, "appointments.delete")
    log_activity(
        db, appointment.family_id, actor_id, "appointment.deleted", "appointment", appointment.id,
        {"scheduled_date": appointment.scheduled_date.isoformat()},
    )
    db.delete(appointment)
    db.commit()
