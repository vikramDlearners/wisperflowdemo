"""Parent care profiles and medicines. Quantity updates have their own permission."""

from datetime import date
from decimal import Decimal
from functools import cache
from zoneinfo import available_timezones

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.models.prescription_scan import PrescriptionScan
from app.services.activity import log_activity
from app.services.errors import NotFound
from app.services.languages import LANGUAGE_CODES
from app.services.permissions import require
from app.services.prescription_scan import ALLOWED_MIME_TYPES, MAX_IMAGE_BYTES

ALLOWED_LANGUAGES = frozenset(LANGUAGE_CODES)


def list_care_profiles(db: Session, actor_id: str, family_id: str) -> list[CareProfile]:
    require(db, actor_id, family_id, "parent_profile.view")
    stmt = select(CareProfile).where(CareProfile.family_id == family_id).order_by(CareProfile.created_at)
    return list(db.execute(stmt).scalars())


def _profile_in_family(db: Session, family_id: str, profile_id: str) -> CareProfile:
    profile = db.get(CareProfile, profile_id)
    if profile is None or profile.family_id != family_id:
        raise NotFound("Care profile not found")
    return profile


@cache
def _timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def is_valid_timezone(name: object) -> bool:
    """True for an IANA time zone name the server knows, e.g. "Asia/Kolkata"."""
    return isinstance(name, str) and name in _timezones()


def _check_timezone(name: object) -> None:
    if not is_valid_timezone(name):
        raise ValueError("timezone must be a valid IANA time zone, e.g. Asia/Kolkata")


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
        raise ValueError("preferred_language must be one of en, ta, hi, te, ml, kn")
    _check_timezone(timezone)
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
        raise ValueError("preferred_language must be one of en, ta, hi, te, ml, kn")
    if "timezone" in changes:
        _check_timezone(changes["timezone"])
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
    purpose: str | None = None,
) -> Medicine:
    require(db, actor_id, family_id, "medicines.edit")
    _profile_in_family(db, family_id, care_profile_id)
    if quantity_remaining is not None and quantity_remaining < 0:
        raise ValueError("quantity_remaining cannot be negative")
    medicine = Medicine(
        care_profile_id=care_profile_id,
        display_name=display_name.strip(),
        instructions_text=instructions_text,
        purpose=purpose,
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
    allowed = {
        "display_name", "instructions_text", "purpose", "refill_date", "responsible_user_id", "active",
        "unit_price", "total_medicine_count",
    }
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"Cannot update fields: {sorted(unknown)}")
    for field, value in changes.items():
        setattr(medicine, field, value)
    if "unit_price" in changes or "total_medicine_count" in changes:
        if medicine.unit_price is not None and medicine.total_medicine_count is not None:
            medicine.total_price = (medicine.unit_price * medicine.total_medicine_count).quantize(Decimal("0.01"))
        else:
            medicine.total_price = None
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


def _linked_scan(db: Session, medicine: Medicine) -> PrescriptionScan | None:
    if medicine.prescription_scan_id is None:
        return None
    return db.get(PrescriptionScan, medicine.prescription_scan_id)


def medicine_has_image(db: Session, medicine: Medicine) -> bool:
    """True if the medicine has its own image or its linked prescription scan has one."""
    if medicine.image_data is not None:
        return True
    scan = _linked_scan(db, medicine)
    return scan is not None and scan.image_data is not None


def get_medicine_image(db: Session, actor_id: str, family_id: str, medicine_id: str) -> tuple[bytes, str]:
    """Return (image_bytes, content_type) for a medicine's own image, else its linked prescription scan image."""
    require(db, actor_id, family_id, "medicines.view")
    medicine = _medicine_in_family(db, family_id, medicine_id)
    if medicine.image_data is not None and medicine.image_content_type is not None:
        return medicine.image_data, medicine.image_content_type
    scan = _linked_scan(db, medicine)
    if scan is not None and scan.image_data is not None and scan.image_content_type is not None:
        return scan.image_data, scan.image_content_type
    raise NotFound("Medicine image not found")
