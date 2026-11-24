"""Appointments for a care recipient. Permissions are checked in the service layer: viewing needs appointments.view, creating appointments.create, editing appointments.update, deleting appointments.delete."""

from datetime import date

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.appointment import Appointment
from app.models.care_profile import CareProfile
from app.models.user import User
from app.schemas import (
    AppointmentCreate,
    AppointmentListOut,
    AppointmentOut,
    AppointmentTextIn,
    AppointmentTextOut,
    AppointmentUpdate,
)
from app.services import appointments as svc
from app.services.appointment_text import parse_appointment_text
from app.services.permissions import require

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


def _out(appointment: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=appointment.id,
        care_recipient_id=appointment.care_profile_id,
        scheduled_date=appointment.scheduled_date,
        start_time=appointment.start_time,
        provider=appointment.provider,
        reason=appointment.reason,
        location=appointment.location,
        notes=appointment.notes,
        status=appointment.status,
    )


@router.get("", response_model=AppointmentListOut)
def list_appointments(
    care_recipient_id: str | None = None, db: Session = DbSession, user: User = CurrentUser
) -> AppointmentListOut:
    if care_recipient_id is None:
        raise ValueError("care_recipient_id is required")
    upcoming, past = svc.list_appointments(db, user.id, care_recipient_id)
    return AppointmentListOut(
        upcoming=[_out(a) for a in upcoming],
        past=[_out(a) for a in past],
    )


@router.post("/parse-text", response_model=AppointmentTextOut)
def parse_text(body: AppointmentTextIn, db: Session = DbSession, user: User = CurrentUser) -> AppointmentTextOut:
    """Voice mode: read a spoken appointment into the form. The parent is matched only against this
    family's care profiles."""
    require(db, user.id, body.family_id, "appointments.create")
    profiles = [
        (pid, name, greeting)
        for pid, name, greeting in db.execute(
            select(CareProfile.id, CareProfile.display_name, CareProfile.greeting_name)
            .where(CareProfile.family_id == body.family_id)
            .order_by(CareProfile.created_at)
        ).all()
    ]
    return AppointmentTextOut(**parse_appointment_text(body.text, body.today or date.today(), profiles))


@router.get("/{appointment_id}", response_model=AppointmentOut)
def get_appointment(
    appointment_id: str, db: Session = DbSession, user: User = CurrentUser
) -> AppointmentOut:
    return _out(svc.get_appointment(db, user.id, appointment_id))


@router.post("", response_model=AppointmentOut, status_code=201)
def create_appointment(
    body: AppointmentCreate, db: Session = DbSession, user: User = CurrentUser
) -> AppointmentOut:
    appointment = svc.create_appointment(
        db,
        user.id,
        body.family_id,
        body.care_recipient_id,
        body.scheduled_date,
        body.start_time,
        body.provider,
        body.reason,
        body.notes,
        location=body.location,
    )
    return _out(appointment)


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def update_appointment(
    appointment_id: str, body: AppointmentUpdate,
    db: Session = DbSession, user: User = CurrentUser,
) -> AppointmentOut:
    changes = body.model_dump(exclude_unset=True)
    return _out(svc.update_appointment(db, user.id, appointment_id, changes))


@router.delete("/{appointment_id}", status_code=204)
def delete_appointment(
    appointment_id: str, db: Session = DbSession, user: User = CurrentUser
) -> Response:
    svc.delete_appointment(db, user.id, appointment_id)
    return Response(status_code=204)
