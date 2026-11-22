"""Medicines for a family's care profiles. Viewing needs medicines.view; editing needs medicines.edit; quantity needs medicine_quantity.update."""

from datetime import datetime, timezone

from fastapi import APIRouter, File, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.medicine import Medicine
from app.models.user import User
from app.schemas import (
    MedicineCreate,
    MedicineOut,
    MedicineUpdate,
    QuantityUpdate,
    ReminderTimesIn,
    ReminderTimesOut,
)
from app.services import care as svc
from app.services import doses as doses_svc
from app.services import reminders as reminders_svc
from app.services.permissions import require
from app.services.prescription_scan import MAX_IMAGE_BYTES

router = APIRouter(prefix="/api/families/{family_id}/medicines", tags=["medicines"])


def _out(db: Session, family_id: str, medicine: Medicine) -> MedicineOut:
    has_image = svc.medicine_has_image(db, medicine)
    return MedicineOut(
        id=medicine.id,
        care_profile_id=medicine.care_profile_id,
        display_name=medicine.display_name,
        instructions_text=medicine.instructions_text,
        quantity_remaining=medicine.quantity_remaining,
        refill_date=medicine.refill_date,
        responsible_user_id=medicine.responsible_user_id,
        active=medicine.active,
        prescription_scan_id=medicine.prescription_scan_id,
        has_image=has_image,
        image_url=f"/api/families/{family_id}/medicines/{medicine.id}/image" if has_image else None,
        unit_price=medicine.unit_price,
        total_medicine_count=medicine.total_medicine_count,
        total_price=medicine.total_price,
    )


@router.get("", response_model=list[MedicineOut])
def list_medicines(family_id: str, db: Session = DbSession, user: User = CurrentUser) -> list[MedicineOut]:
    return [_out(db, family_id, m) for m in svc.list_medicines(db, user.id, family_id)]


@router.get("/doses/today")
def doses_today(
    family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser
) -> list[dict]:
    require(db, user.id, family_id, "medicines.view")
    profile = svc._profile_in_family(db, family_id, care_profile_id)
    now = datetime.now(timezone.utc)
    logged = doses_svc.logged_today(db, profile, now)
    out = []
    for d in doses_svc.doses_today(db, profile, now):
        row = logged.get((d.medicine_id, d.slot))
        out.append({
            "medicine_id": d.medicine_id,
            "slot": d.slot,
            "status": d.status,
            "recorded_at": row.recorded_at if row else None,
        })
    return out


@router.post("", response_model=MedicineOut, status_code=201)
def create_medicine(
    family_id: str, body: MedicineCreate, db: Session = DbSession, user: User = CurrentUser
) -> MedicineOut:
    medicine = svc.create_medicine(
        db,
        user.id,
        family_id,
        body.care_profile_id,
        body.display_name,
        body.instructions_text,
        body.quantity_remaining,
        body.refill_date,
        body.responsible_user_id,
    )
    return _out(db, family_id, medicine)


@router.get("/{medicine_id}", response_model=MedicineOut)
def get_medicine(
    family_id: str, medicine_id: str, db: Session = DbSession, user: User = CurrentUser
) -> MedicineOut:
    return _out(db, family_id, svc.get_medicine(db, user.id, family_id, medicine_id))


@router.patch("/{medicine_id}", response_model=MedicineOut)
def update_medicine(
    family_id: str, medicine_id: str, body: MedicineUpdate,
    db: Session = DbSession, user: User = CurrentUser,
) -> MedicineOut:
    changes = body.model_dump(exclude_unset=True)
    return _out(db, family_id, svc.update_medicine(db, user.id, family_id, medicine_id, changes))


@router.patch("/{medicine_id}/quantity", response_model=MedicineOut)
def update_medicine_quantity(
    family_id: str, medicine_id: str, body: QuantityUpdate,
    db: Session = DbSession, user: User = CurrentUser,
) -> MedicineOut:
    return _out(db, family_id, svc.update_medicine_quantity(db, user.id, family_id, medicine_id, body.quantity))


@router.delete("/{medicine_id}", status_code=204)
def delete_medicine(
    family_id: str, medicine_id: str, db: Session = DbSession, user: User = CurrentUser
) -> Response:
    svc.delete_medicine(db, user.id, family_id, medicine_id)
    return Response(status_code=204)


@router.post("/{medicine_id}/image", response_model=MedicineOut, status_code=200)
def upload_medicine_image(
    family_id: str,
    medicine_id: str,
    file: UploadFile = File(...),
    db: Session = DbSession,
    user: User = CurrentUser,
) -> MedicineOut:
    # Read one byte past the limit so the service can reject oversized uploads.
    image_bytes = file.file.read(MAX_IMAGE_BYTES + 1)
    medicine = svc.upload_medicine_image(
        db, user.id, family_id, medicine_id, image_bytes, file.content_type or ""
    )
    return _out(db, family_id, medicine)


@router.get("/{medicine_id}/image")
def get_medicine_image(
    family_id: str, medicine_id: str, db: Session = DbSession, user: User = CurrentUser
) -> Response:
    image_bytes, content_type = svc.get_medicine_image(db, user.id, family_id, medicine_id)
    return Response(content=image_bytes, media_type=content_type)


@router.get("/{medicine_id}/reminders", response_model=ReminderTimesOut)
def get_reminders(
    family_id: str, medicine_id: str, db: Session = DbSession, user: User = CurrentUser
) -> ReminderTimesOut:
    svc.get_medicine(db, user.id, family_id, medicine_id)  # medicines.view + family scoping
    return ReminderTimesOut(times=reminders_svc.list_reminder_times(db, medicine_id))


@router.put("/{medicine_id}/reminders", response_model=ReminderTimesOut)
def put_reminders(
    family_id: str, medicine_id: str, body: ReminderTimesIn,
    db: Session = DbSession, user: User = CurrentUser,
) -> ReminderTimesOut:
    times = reminders_svc.set_reminder_times(db, user.id, family_id, medicine_id, body.times)
    return ReminderTimesOut(times=times)
