"""Medicines for a family's care profiles. Viewing needs medicines.view; editing needs medicines.edit; quantity needs medicine_quantity.update."""

from fastapi import APIRouter, File, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.medicine import Medicine
from app.models.user import User
from app.schemas import MedicineCreate, MedicineOut, MedicineUpdate, QuantityUpdate
from app.services import care as svc
from app.services.prescription_scan import MAX_IMAGE_BYTES

router = APIRouter(prefix="/api/families/{family_id}/medicines", tags=["medicines"])


def _out(medicine: Medicine) -> MedicineOut:
    return MedicineOut(
        id=medicine.id,
        care_profile_id=medicine.care_profile_id,
        display_name=medicine.display_name,
        instructions_text=medicine.instructions_text,
        quantity_remaining=medicine.quantity_remaining,
        refill_date=medicine.refill_date,
        responsible_user_id=medicine.responsible_user_id,
        active=medicine.active,
    )


@router.get("", response_model=list[MedicineOut])
def list_medicines(family_id: str, db: Session = DbSession, user: User = CurrentUser) -> list[MedicineOut]:
    return [_out(m) for m in svc.list_medicines(db, user.id, family_id)]


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
    return _out(medicine)


@router.get("/{medicine_id}", response_model=MedicineOut)
def get_medicine(
    family_id: str, medicine_id: str, db: Session = DbSession, user: User = CurrentUser
) -> MedicineOut:
    return _out(svc.get_medicine(db, user.id, family_id, medicine_id))


@router.patch("/{medicine_id}", response_model=MedicineOut)
def update_medicine(
    family_id: str, medicine_id: str, body: MedicineUpdate,
    db: Session = DbSession, user: User = CurrentUser,
) -> MedicineOut:
    changes = body.model_dump(exclude_unset=True)
    return _out(svc.update_medicine(db, user.id, family_id, medicine_id, changes))


@router.patch("/{medicine_id}/quantity", response_model=MedicineOut)
def update_medicine_quantity(
    family_id: str, medicine_id: str, body: QuantityUpdate,
    db: Session = DbSession, user: User = CurrentUser,
) -> MedicineOut:
    return _out(svc.update_medicine_quantity(db, user.id, family_id, medicine_id, body.quantity))


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
    return _out(medicine)


@router.get("/{medicine_id}/image")
def get_medicine_image(
    family_id: str, medicine_id: str, db: Session = DbSession, user: User = CurrentUser
) -> Response:
    image_bytes, content_type = svc.get_medicine_image(db, user.id, family_id, medicine_id)
    return Response(content=image_bytes, media_type=content_type)
