"""Parent care profiles and medicines. Quantity updates have their own permission."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.services.activity import log_activity
from app.services.errors import NotFound
from app.services.permissions import require
from app.services.prescription_scan import ALLOWED_MIME_TYPES, MAX_IMAGE_BYTES

ALLOWED_LANGUAGES = frozenset({"en", "ta", "hi"})


def list_care_profiles(db: Session, actor_id: str, family_id: str) -> list[CareProfile]:
    require(db, actor_id, family_id, "parent_profile.view")
    stmt = select(CareProfile).where(CareProfile.family_id == family_id).order_by(CareProfile.created_at)
    return list(db.execute(stmt).scalars())


def _profile_in_family(db: Session, family_id: str, profile_id: str) -> CareProfile:
    profile = db.get(CareProfile, profile_id)
    if profile is None or profile.family_id != family_id:
        raise NotFound("Care profile not found")
    return profile


def create_care_profile(
    db: Session,
    actor_id: str,
    family_id: str,
    display_name: str,
    greeting_name: str,
    preferred_language: str = "en",
    timezone: str = "Asia/Kolkata",
) -> CareProfile:
    require(db, actor_id, family_id, "parent_profile.edit")
    if preferred_language not in ALLOWED_LANGUAGES:
        raise ValueError("preferred_language must be one of en, ta, hi")
    profile = CareProfile(
        family_id=family_id,
        display_name=display_name.strip(),
        greeting_name=greeting_name.strip(),
        preferred_language=preferred_language,
        timezone=timezone,
    )
    db.add(profile)
    db.flush()
    log_activity(db, family_id, actor_id, "care_profile.created", "care_profile", profile.id)
    db.commit()
    return profile


def update_care_profile(
    db: Session, actor_id: str, family_id: str, profile_id: str, changes: dict
) -> CareProfile:
    require(db, actor_id, family_id, "parent_profile.edit")
    profile = _profile_in_family(db, family_id, profile_id)
    allowed = {"display_name", "greeting_name", "preferred_language", "timezone"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Cannot update fields: {sorted(unknown)}")
    if "preferred_language" in changes and changes["preferred_language"] not in ALLOWED_LANGUAGES:
        raise ValueError("preferred_language must be one of en, ta, hi")
    for field, value in changes.items():
        setattr(profile, field, value.strip() if isinstance(value, str) else value)
    log_activity(
        db, family_id, actor_id, "care_profile.updated", "care_profile", profile.id,
        {"fields": sorted(changes)},
    )
    db.commit()
    return profile

def get_care_profile(db: Session, actor_id: str, family_id: str, profile_id: str) -> CareProfile:
    require(db, actor_id, family_id, "parent_profile.view")
    return _profile_in_family(db, family_id, profile_id)


def delete_care_profile(db: Session, actor_id: str, family_id: str, profile_id: str) -> None:
    require(db, actor_id, family_id, "parent_profile.edit")
    profile = _profile_in_family(db, family_id, profile_id)
    log_activity(db, family_id, actor_id, "care_profile.deleted", "care_profile", profile.id)
    db.delete(profile)
    db.commit()




def list_medicines(db: Session, actor_id: str, family_id: str) -> list[Medicine]:
    require(db, actor_id, family_id, "medicines.view")
    stmt = (
        select(Medicine)
        .join(CareProfile, CareProfile.id == Medicine.care_profile_id)
        .where(CareProfile.family_id == family_id)
        .order_by(Medicine.display_name)
    )
    return list(db.execute(stmt).scalars())


def _medicine_in_family(db: Session, family_id: str, medicine_id: str) -> Medicine:
    medicine = db.get(Medicine, medicine_id)
    if medicine is None:
        raise NotFound("Medicine not found")
    _profile_in_family(db, family_id, medicine.care_profile_id)
    return medicine


def create_medicine(
    db: Session,
    actor_id: str,
    family_id: str,
    care_profile_id: str,
    display_name: str,
    instructions_text: str | None = None,
    quantity_remaining: int | None = None,
    refill_date: date | None = None,
    responsible_user_id: str | None = None,
) -> Medicine:
    require(db, actor_id, family_id, "medicines.edit")
    _profile_in_family(db, family_id, care_profile_id)
    if quantity_remaining is not None and quantity_remaining < 0:
        raise ValueError("quantity_remaining cannot be negative")
    medicine = Medicine(
        care_profile_id=care_profile_id,
        display_name=display_name.strip(),
        instructions_text=instructions_text,
        quantity_remaining=quantity_remaining,
        refill_date=refill_date,
        responsible_user_id=responsible_user_id,
    )
    db.add(medicine)
    db.flush()
    log_activity(db, family_id, actor_id, "medicine.created", "medicine", medicine.id)
    db.commit()
    return medicine


def update_medicine(
    db: Session, actor_id: str, family_id: str, medicine_id: str, changes: dict
) -> Medicine:
    require(db, actor_id, family_id, "medicines.edit")
    medicine = _medicine_in_family(db, family_id, medicine_id)
    allowed = {"display_name", "instructions_text", "refill_date", "responsible_user_id", "active"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Cannot update fields: {sorted(unknown)}")
    for field, value in changes.items():
        setattr(medicine, field, value)
    log_activity(
        db, family_id, actor_id, "medicine.updated", "medicine", medicine.id,
        {"fields": sorted(changes)},
    )
    db.commit()
    return medicine


def update_medicine_quantity(
    db: Session, actor_id: str, family_id: str, medicine_id: str, quantity: int
) -> Medicine:
    """Only needs medicine_quantity.update, so a 'Medicine tracker' role can use it alone."""
    require(db, actor_id, family_id, "medicine_quantity.update")
    if quantity < 0:
        raise ValueError("quantity cannot be negative")
    medicine = _medicine_in_family(db, family_id, medicine_id)
    previous = medicine.quantity_remaining
    medicine.quantity_remaining = quantity
    log_activity(
        db, family_id, actor_id, "medicine.quantity_updated", "medicine", medicine.id,
        {"from": previous, "to": quantity},
    )
    db.commit()
    return medicine


def get_medicine(db: Session, actor_id: str, family_id: str, medicine_id: str) -> Medicine:
    require(db, actor_id, family_id, "medicines.view")
    return _medicine_in_family(db, family_id, medicine_id)


def delete_medicine(db: Session, actor_id: str, family_id: str, medicine_id: str) -> None:
    require(db, actor_id, family_id, "medicines.edit")
    medicine = _medicine_in_family(db, family_id, medicine_id)
    log_activity(db, family_id, actor_id, "medicine.deleted", "medicine", medicine.id)
    db.delete(medicine)
    db.commit()


def upload_medicine_image(
    db: Session,
    actor_id: str,
    family_id: str,
    medicine_id: str,
    image_bytes: bytes,
    mime_type: str,
) -> Medicine:
    require(db, actor_id, family_id, "medicines.edit")
    medicine = _medicine_in_family(db, family_id, medicine_id)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError("Upload a JPEG, PNG or WebP image")
    if not image_bytes:
        raise ValueError("Uploaded image is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Uploaded image must be 10 MB or smaller")
    medicine.image_data = image_bytes
    medicine.image_content_type = mime_type
    log_activity(db, family_id, actor_id, "medicine.image_uploaded", "medicine", medicine.id)
    db.commit()
    return medicine


def get_medicine_image(db: Session, actor_id: str, family_id: str, medicine_id: str) -> tuple[bytes, str]:
    """Return (image_bytes, content_type) for a medicine that has an image."""
    require(db, actor_id, family_id, "medicines.view")
    medicine = _medicine_in_family(db, family_id, medicine_id)
    if medicine.image_data is None or medicine.image_content_type is None:
        raise NotFound("Medicine image not found")
    return medicine.image_data, medicine.image_content_type
