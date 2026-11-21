"""Appointments for a care recipient. Permissions are checked in the service layer: viewing needs appointments.view, creating appointments.create, editing appointments.update, deleting appointments.delete."""

from fastapi import APIRouter, Response
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.appointment import Appointment
from app.models.user import User
from app.schemas import AppointmentCreate, AppointmentListOut, AppointmentOut, AppointmentUpdate
from app.services import appointments as svc

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


def _out(appointment: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=appointment.id,
        care_recipient_id=appointment.care_profile_id,
        scheduled_date=appointment.scheduled_date,
        start_time=appointment.start_time,
        provider=appointment.provider,
        reason=appointment.reason,
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
