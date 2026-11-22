"""Prescription photo scans. Gemini classifies an upload; a family member confirms the medicines and reminders.

Staging and commits follow the other services: notify() only stages rows, the caller commits once.
"""

import base64
import json
import re
import urllib.error
import urllib.request
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.care_profile import CareProfile
from app.models.medicine import Medicine
from app.models.prescription_scan import MedicineReminder, PrescriptionScan
from app.services.activity import log_activity
from app.services.errors import NotFound
from app.services.notifications import notify
from app.services.permissions import get_membership, require

ALLOWED_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_IMAGE_BYTES = 10 * 1024 * 1024
DOCUMENT_TYPES = frozenset({"prescription", "invoice", "other"})
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_TIMEOUT_SECONDS = 60


class PrescriptionScanUpstreamError(Exception):
    """The Gemini request failed or returned a response that could not be read."""

PROMPT = (
    "You are reading a photo of a document for a family caring for an elderly parent. "
    'Classify it as "prescription" (a doctor\'s medicine prescription), "invoice" (a bill or receipt), '
    'or "other". For a prescription, list every medicine with its name, dose, instructions, and its '
    'dosing times as 24-hour "HH:MM" strings (for example "08:00" or "20:30"). '
    "Respond only with JSON in this shape: "
    '{"document_type": "prescription" | "invoice" | "other", '
    '"medicines": [{"name": string, "dose": string, "instructions": string, "times": ["HH:MM"]}]}. '
    "Use an empty medicines list for anything that is not a prescription."
)


def scan_document(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    """The single point that calls the Gemini REST API. Tests mock this function."""
    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured")
    body = {
        "contents": [
            {
                "parts": [
                    {"text": PROMPT},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    request = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=settings.gemini_model),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=GEMINI_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise PrescriptionScanUpstreamError(f"Gemini request failed with HTTP status {exc.code}") from None
    except urllib.error.URLError:
        raise PrescriptionScanUpstreamError("Gemini request failed (network error)") from None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        raise PrescriptionScanUpstreamError("Gemini request failed (could not read response)") from None
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not read the scan result") from exc
    return _normalise(result)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalise(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("Could not read the scan result")
    document_type = result.get("document_type")
    if document_type not in DOCUMENT_TYPES:
        document_type = "other"
    medicines = []
    for item in result.get("medicines") or []:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if not name:
            continue
        times = item.get("times") or []
        medicines.append(
            {
                "name": name,
                "dose": _text(item.get("dose")),
                "instructions": _text(item.get("instructions")),
                "times": [str(t).strip() for t in times if isinstance(t, str)],
            }
        )
    return {"document_type": document_type, "medicines": medicines}


def _profile_in_family(db: Session, family_id: str, profile_id: str) -> CareProfile:
    profile = db.get(CareProfile, profile_id)
    if profile is None or profile.family_id != family_id:
        raise NotFound("Care profile not found")
    return profile


def _scan_in_profile(db: Session, family_id: str, profile_id: str, scan_id: str) -> PrescriptionScan:
    scan = db.get(PrescriptionScan, scan_id)
    if scan is None or scan.family_id != family_id or scan.care_profile_id != profile_id:
        raise NotFound("Prescription scan not found")
    return scan


def create_scan(
    db: Session,
    actor_id: str,
    family_id: str,
    care_profile_id: str,
    image_bytes: bytes,
    mime_type: str,
) -> PrescriptionScan:
    require(db, actor_id, family_id, "medicines.edit")
    _profile_in_family(db, family_id, care_profile_id)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError("Upload a JPEG, PNG or WebP image")
    if not image_bytes:
        raise ValueError("Uploaded image is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Uploaded image must be 10 MB or smaller")
    result = scan_document(image_bytes, mime_type)
    is_prescription = result["document_type"] == "prescription"
    scan = PrescriptionScan(
        family_id=family_id,
        care_profile_id=care_profile_id,
        uploaded_by_user_id=actor_id,
        document_type=result["document_type"],
        status="pending_review" if is_prescription else "rejected",
        proposed={"medicines": result["medicines"]} if is_prescription else {"medicines": []},
        image_data=image_bytes if is_prescription else None,
        image_content_type=mime_type if is_prescription else None,
    )
    db.add(scan)
    db.flush()
    log_activity(db, family_id, actor_id, "prescription_scan.created", "prescription_scan", scan.id)
    db.commit()
    return scan


def get_scan(
    db: Session, actor_id: str, family_id: str, care_profile_id: str, scan_id: str
) -> PrescriptionScan:
    require(db, actor_id, family_id, "medicines.view")
    return _scan_in_profile(db, family_id, care_profile_id, scan_id)


def confirm_scan(
    db: Session,
    actor_id: str,
    family_id: str,
    care_profile_id: str,
    scan_id: str,
    medicines: list[dict],
) -> tuple[list[str], list[str]]:
    """Create medicines and reminders from reviewed entries; return (medicine_ids, notified_user_ids)."""
    require(db, actor_id, family_id, "medicines.edit")
    profile = _profile_in_family(db, family_id, care_profile_id)
    scan = _scan_in_profile(db, family_id, care_profile_id, scan_id)
    if scan.status != "pending_review":
        raise ValueError("This scan is not waiting for review")

    medicine_ids: list[str] = []
    names: list[str] = []
    times_by_name: dict[str, list[str]] = {}
    caregiver_ids: list[str] = []
    for item in medicines:
        responsible_user_id = item.get("responsible_user_id")
        if responsible_user_id:
            # Only active members of this family can be made responsible.
            get_membership(db, responsible_user_id, family_id)
            caregiver_ids.append(responsible_user_id)
        name = item["name"].strip()
        instructions = "; ".join(p for p in (item.get("dose"), item.get("instructions")) if p) or None
        medicine = Medicine(
            care_profile_id=care_profile_id,
            display_name=name,
            instructions_text=instructions,
            active=True,
            responsible_user_id=responsible_user_id,
            prescription_scan_id=scan.id,
        )
        db.add(medicine)
        db.flush()
        for time_of_day in item["times"]:
            db.add(MedicineReminder(medicine_id=medicine.id, time_of_day=time_of_day))
        medicine_ids.append(medicine.id)
        names.append(name)
        times_by_name[name] = list(item["times"])

    recipients: list[str] = []
    for user_id in [profile.linked_user_id, *caregiver_ids]:
        if user_id and user_id != actor_id and user_id not in recipients:
            recipients.append(user_id)
    for user_id in recipients:
        notify(
            db,
            user_id,
            "medicine_reminders_created",
            family_id=family_id,
            payload={"medicines": names, "times": times_by_name},
        )

    scan.status = "confirmed"
    log_activity(
        db, family_id, actor_id, "prescription_scan.confirmed", "prescription_scan", scan.id,
        {"medicine_count": len(medicine_ids)},
    )
    db.commit()
    return medicine_ids, recipients
