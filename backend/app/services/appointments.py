"""Appointments for a care recipient. The family is never in the URL: it is taken from the care profile (list) or from the appointment (get, update, delete), and membership is checked against that family with require()."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.models.membership import FamilyMember
from app.models.role import Role
from app.models.user import User
from app.services.activity import log_activity
from app.services.errors import NotFound
from app.services.notifications import notify
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


def _check_responsible(db: Session, family_id: str, user_id: str | None) -> None:
    if user_id is None:
        return
    member = db.execute(
        select(FamilyMember.id).where(
            FamilyMember.family_id == family_id, FamilyMember.user_id == user_id, FamilyMember.status == "active"
        )
    ).first()
    if member is None:
        raise ValueError("The responsible person must be an active member of this family")


def _notify_completed(db: Session, actor_id: str, appointment: Appointment) -> None:
    """Tell the family managers and the responsible person that the visit is done (not the one who marked it).
    The caller commits."""
    managers = db.execute(
        select(FamilyMember.user_id)
        .join(Role, Role.id == FamilyMember.role_id)
        .where(
            FamilyMember.family_id == appointment.family_id,
            FamilyMember.status == "active",
            Role.name == "Family manager",
        )
    ).scalars()
    recipients = list(dict.fromkeys([*managers, appointment.responsible_user_id]))
    profile = db.get(CareProfile, appointment.care_profile_id)
    actor = db.get(User, actor_id)
    payload = {
        "appointment_id": appointment.id,
        "care_profile_id": appointment.care_profile_id,
        "parent_name": profile.display_name if profile else None,
        "reason": appointment.reason,
        "provider": appointment.provider,
        "scheduled_date": appointment.scheduled_date.isoformat(),
        "start_time": appointment.start_time,
        "completed_by": actor.display_name if actor else None,
    }
    for user_id in recipients:
        if user_id and user_id != actor_id:
            notify(db, user_id, "appointment.completed", appointment.family_id, payload)


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
    location: str | None = None,
    fee=None,
    doctor_notes: str | None = None,
    responsible_user_id: str | None = None,
) -> Appointment:
    require(db, actor_id, family_id, "appointments.create")
    _profile_in_family(db, family_id, care_recipient_id)
    _check_responsible(db, family_id, responsible_user_id)
    appointment = Appointment(
        family_id=family_id,
        care_profile_id=care_recipient_id,
        scheduled_date=scheduled_date,
        start_time=start_time.strip(),
        provider=provider.strip(),
        reason=reason.strip(),
        location=_clean(location) or None,
        notes=notes or "",
        fee=fee,
        doctor_notes=_clean(doctor_notes) or None,
        responsible_user_id=responsible_user_id,
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
        if value is None and key not in ("notes", "location", "fee", "doctor_notes", "responsible_user_id"):
            raise ValueError(f"{key} cannot be null")
    completing = changes.get("status") == "completed" and appointment.status != "completed"
    if "responsible_user_id" in changes:
        _check_responsible(db, appointment.family_id, changes["responsible_user_id"])
        appointment.responsible_user_id = changes["responsible_user_id"]
    if "care_recipient_id" in changes:
        _profile_in_family(db, appointment.family_id, changes["care_recipient_id"])
        appointment.care_profile_id = changes["care_recipient_id"]
    for key in ("scheduled_date", "start_time", "provider", "reason", "status"):
        if key in changes:
            setattr(appointment, key, _clean(changes[key]))
    if "location" in changes:
        appointment.location = _clean(changes["location"]) or None
    if "notes" in changes:
        appointment.notes = changes["notes"] or ""
    if "fee" in changes:
        appointment.fee = changes["fee"]
    if "doctor_notes" in changes:
        appointment.doctor_notes = _clean(changes["doctor_notes"]) or None
    log_activity(
        db, appointment.family_id, actor_id, "appointment.updated", "appointment", appointment.id,
        {"fields": sorted(changes)},
    )
    if completing:
        _notify_completed(db, actor_id, appointment)
    db.commit()
    return appointment


def delete_appointment(db: Session, actor_id: str, appointment_id: str) -> None:
    appointment = _appointment(db, appointment_id)
    require(db, actor_id, appointment.family_id, "appointments.delete")
    log_activity(
        db, appointment.family_id, actor_id, "appointment.deleted", "appointment", appointment.id,
        {"scheduled_date": appointment.scheduled_date.isoformat()},
    )
    # The medicines stay; they just no longer point at this appointment.
    for medicine in db.execute(select(Medicine).where(Medicine.appointment_id == appointment.id)).scalars():
        medicine.appointment_id = None
    db.delete(appointment)
    db.commit()


def appointment_medicines(db: Session, appointment_id: str) -> list[Medicine]:
    return list(
        db.execute(
            select(Medicine).where(Medicine.appointment_id == appointment_id).order_by(Medicine.display_name)
        ).scalars()
    )


def check_medicine_appointment(db: Session, medicine: Medicine, appointment_id: str) -> None:
    """A medicine can only be linked to an appointment of the same parent."""
    appointment = db.get(Appointment, appointment_id)
    if appointment is None or appointment.care_profile_id != medicine.care_profile_id:
        raise ValueError("Pick an appointment of the same parent as the medicine")


def set_appointment_medicines(
    db: Session, actor_id: str, appointment_id: str, medicine_ids: list[str]
) -> Appointment:
    """Make exactly these medicines the ones given at this appointment (others linked to it are unlinked)."""
    appointment = _appointment(db, appointment_id)
    require(db, actor_id, appointment.family_id, "appointments.update")
    require(db, actor_id, appointment.family_id, "medicines.edit")
    wanted = list(dict.fromkeys(medicine_ids))
    medicines = [db.get(Medicine, mid) for mid in wanted]
    if any(m is None or m.care_profile_id != appointment.care_profile_id for m in medicines):
        raise ValueError("Only this parent's medicines can be linked to the appointment")
    for current in appointment_medicines(db, appointment.id):
        if current.id not in wanted:
            current.appointment_id = None
    for medicine in medicines:
        medicine.appointment_id = appointment.id
    log_activity(
        db, appointment.family_id, actor_id, "appointment.medicines_set", "appointment", appointment.id,
        {"medicines": [m.display_name for m in medicines]},
    )
    db.commit()
    return appointment
