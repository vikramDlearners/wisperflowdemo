"""Family dashboard: parents, today's medicine status, stock, next appointment, emergency and recent activity.

Every query is scoped by family_id or by the selected care_profile_id. Permission is checked by the caller.
"""

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import ActivityLog
from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.models.dose import MedicineDose
from app.models.medicine import Medicine
from app.models.membership import FamilyMember
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.services.doses import ANY_SLOT, no_time_slots, today_for
from app.services.emergencies import open_emergencies
from app.services.errors import NotFound
from app.services.profile import age_from, get_care_profile_onboarding
from app.services.reminders import list_reminder_times

LOW_STOCK_DAYS = 7
RECENT_ACTIVITY_LIMIT = 10
TAKEN = "taken"
MISSED = "missed"
CANCELLED = "cancelled"



def _field(onboarding: ParentOnboardingProfile | None, name: str) -> Any:
    return getattr(onboarding, name) if onboarding is not None else None


_MALE_RELATIONSHIPS = {"father", "dad", "papa", "daddy", "son"}
_FEMALE_RELATIONSHIPS = {"mother", "mom", "mum", "mama", "mommy", "daughter"}


def _gender_for(explicit_gender: str | None, relationship: str | None) -> str | None:
    if explicit_gender and explicit_gender.strip():
        return explicit_gender.strip().lower()
    key = "".join((relationship or "").split()).lower()
    if key in _MALE_RELATIONSHIPS:
        return "male"
    if key in _FEMALE_RELATIONSHIPS:
        return "female"
    return None


def _logged_on(db: Session, profile_id: str, day: date) -> dict[tuple[str, str], MedicineDose]:
    rows = db.execute(
        select(MedicineDose).where(MedicineDose.care_profile_id == profile_id, MedicineDose.dose_date == day)
    ).scalars().all()
    return {(r.medicine_id, r.slot): r for r in rows}


def _active_medicines(
    db: Session, profile_id: str, logged: dict | None = None
) -> list[tuple[Medicine, list[str]]]:
    meds = db.execute(
        select(Medicine)
        .where(Medicine.care_profile_id == profile_id, Medicine.active.is_(True))
        .order_by(Medicine.created_at, Medicine.id)
    ).scalars().all()
    # A medicine without reminder times shows the day parts answered that day (morning, noon, night),
    # or one "any" slot when none is.
    return [(med, list_reminder_times(db, med.id) or no_time_slots(med.id, logged or {}, ANY_SLOT))
            for med in meds]


def _day_for(profile: CareProfile, on_date: date | None, now: datetime) -> date:
    return on_date if on_date is not None else today_for(profile, now)


def _parent_card(db: Session, profile: CareProfile, day: date) -> dict[str, Any]:
    onboarding = get_care_profile_onboarding(db, profile)
    logged = _logged_on(db, profile.id, day)
    # Fall back to the relationship entered on the Members page when onboarding has none.
    membership = db.get(FamilyMember, profile.linked_member_id) if profile.linked_member_id else None
    relationship = _field(onboarding, "relationship") or (membership.relationship if membership else None)
    return {
        "care_profile_id": profile.id,
        "display_name": profile.display_name,
        "relationship": relationship,
        "age": age_from(onboarding) if onboarding is not None else None,
        "photo_url": _field(onboarding, "profile_picture_url"),
        # An uploaded photo (fetched with sign-in from .../parents/{id}/profile/photo) is shown first.
        "has_photo": onboarding is not None and onboarding.profile_photo_content_type is not None,
        "known_health_conditions": _field(onboarding, "known_health_conditions"),
        "primary_caregiver_name": _field(onboarding, "caregiver_name"),
        "gender": _gender_for(_field(onboarding, "gender"), relationship),
        "all_good": not any(r.status == MISSED for r in logged.values()),
    }


# User-initiated actions shown in Recent Activity. Anything not listed here (checkin.*, family.*,
# settings.*, medicine.quantity_updated, medicine.reminders_set, ...) is hidden.
ACTIVITY_LABELS: dict[str, str] = {
    "appointment.created": "Appointment created",
    "appointment.updated": "Appointment updated",
    "appointment.deleted": "Appointment deleted",
    "medicine.created": "Medicine added",
    "medicine.deleted": "Medicine removed",
    "medicine.image_uploaded": "Medicine photo uploaded",
    "care_profile.created": "Care profile added",
    "care_profile.deleted": "Care profile removed",
    "task.notified": "Task notification sent",
    "emergency.completed": "Emergency marked as completed",
}


def _activity_text(row: ActivityLog) -> str:
    return ACTIVITY_LABELS.get(row.action, "")


def _recent_activity(db: Session, family_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ActivityLog)
        .where(ActivityLog.family_id == family_id, ActivityLog.action.in_(list(ACTIVITY_LABELS)))
        .order_by(ActivityLog.created_at.desc())
        .limit(RECENT_ACTIVITY_LIMIT)
    ).scalars().all()
    return [{"id": r.id, "text": _activity_text(r), "created_at": r.created_at} for r in rows]


def _select_profile(profiles: list[CareProfile], care_profile_id: str | None) -> CareProfile | None:
    if care_profile_id is None:
        return profiles[0] if profiles else None
    selected = next((p for p in profiles if p.id == care_profile_id), None)
    if selected is None:
        raise NotFound("Care profile not found")
    return selected


def build_family_dashboard(
    db: Session,
    family_id: str,
    care_profile_id: str | None = None,
    on_date: date | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    profiles = list(
        db.execute(
            select(CareProfile).where(CareProfile.family_id == family_id).order_by(CareProfile.created_at)
        ).scalars().all()
    )
    parents = [_parent_card(db, p, _day_for(p, on_date, now)) for p in profiles]
    selected = _select_profile(profiles, care_profile_id)
    recent = _recent_activity(db, family_id)
    emergencies = open_emergencies(db, family_id)

    if selected is None:
        return {
            "parents": parents,
            "selected_care_profile_id": None,
            "on_date": on_date or now.date(),
            "daily_medicine_count": 0,
            "medicines_today": {"taken": 0, "total": 0},
            "today_schedule": [],
            "medicine_stock": [],
            "next_appointment": None,
            "emergency": {"active": False, "last_check_at": None},
            "recent_activity": recent,
            "emergencies": emergencies,
        }

    day = _day_for(selected, on_date, now)
    logged = _logged_on(db, selected.id, day)

    schedule: list[dict[str, Any]] = []
    stock: list[dict[str, Any]] = []
    taken = total = 0
    medicine_count = 0  # "N Medicine(s) daily" counts medicines; total counts today's dose slots
    for med, slots in _active_medicines(db, selected.id, logged):
        medicine_count += 1
        total += len(slots)
        for slot in slots:
            row = logged.get((med.id, slot))
            status = row.status if row is not None else None
            if status == TAKEN:
                taken += 1
            schedule.append({
                "medicine_id": med.id,
                "medicine_name": med.display_name,
                "slot": slot,
                "status": status,
            })
        days_left = None
        if med.quantity_remaining is not None and len(slots) > 0:
            days_left = round(med.quantity_remaining / len(slots), 1)
        stock.append({
            "medicine_id": med.id,
            "display_name": med.display_name,
            "instructions_text": med.instructions_text,
            "purpose": med.purpose,
            "quantity_remaining": med.quantity_remaining,
            "days_left": days_left,
            "low": days_left is not None and days_left <= LOW_STOCK_DAYS,
        })

    appointment = db.execute(
        select(Appointment)
        .where(
            Appointment.care_profile_id == selected.id,
            Appointment.status != CANCELLED,
            Appointment.scheduled_date >= day,
        )
        .order_by(Appointment.scheduled_date, Appointment.start_time)
        .limit(1)
    ).scalar_one_or_none()
    next_appointment = None
    if appointment is not None:
        next_appointment = {
            "id": appointment.id,
            "title": appointment.reason,
            "doctor": appointment.provider,
            "location": appointment.location,
            "scheduled_date": appointment.scheduled_date,
            "start_time": appointment.start_time,
        }

    checks = [r.recorded_at for r in logged.values() if r.recorded_at is not None]
    return {
        "parents": parents,
        "selected_care_profile_id": selected.id,
        "on_date": day,
        "daily_medicine_count": medicine_count,
        "medicines_today": {"taken": taken, "total": total},
        "today_schedule": schedule,
        "medicine_stock": stock,
        "next_appointment": next_appointment,
        "emergency": {
            "active": any(r.status == MISSED for r in logged.values()),
            "last_check_at": max(checks) if checks else None,
        },
        "recent_activity": recent,
        "emergencies": emergencies,
    }
