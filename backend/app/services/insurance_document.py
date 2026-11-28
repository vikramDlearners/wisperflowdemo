"""Insurance policy documents: a PDF or a photo, attached to a policy, and read by Gemini to fill in the form.

Files are checked by their first bytes, not only the type the browser claims, and kept to 10 MB.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.insurance import InsurancePolicy
from app.services.activity import log_activity
from app.services.errors import NotFound
from app.services.insurance import _policy
from app.services.permissions import require
from app.services.understanding import ask_gemini_image

MAX_BYTES = 10 * 1024 * 1024
TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
POLICY_TYPES = {"health", "life", "accident", "critical_illness", "home", "vehicle", "other"}
FREQUENCIES = {"yearly", "half_yearly", "quarterly", "monthly"}

PROMPT = """This is an Indian insurance policy document (a PDF or a photo of it). Read it and return JSON with:
- "policy_type": one of health, life, accident, critical_illness, home, vehicle, other
- "insurer": the insurance company's name
- "plan_name": the plan / product name, or null
- "policy_number": the policy number, or null
- "insured_name": the name of the person insured (if several, the first), or null
- "sum_insured": the sum insured / sum assured in rupees as a number, or null
- "premium": the total premium paid for one period in rupees as a number (with GST if shown), or null
- "premium_frequency": one of yearly, half_yearly, quarterly, monthly (yearly if not said)
- "start_date": the policy start date as YYYY-MM-DD, or null
- "renewal_date": the date the policy must be renewed / the policy end date as YYYY-MM-DD, or null
- "agent_name", "agent_phone": the agent or intermediary, or null
- "helpline": the claims / customer care phone number, or null
Copy only what is written in the document. Do not guess."""


def check_file(content: bytes, mime: str) -> None:
    if not content:
        raise ValueError("The file is empty")
    if len(content) > MAX_BYTES:
        raise ValueError("The file must be 10 MB or smaller")
    looks_like = {
        "application/pdf": content.startswith(b"%PDF"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": content[:4] == b"RIFF" and content[8:12] == b"WEBP",
    }
    if mime not in TYPES or not looks_like.get(mime, False):
        raise ValueError("Upload a PDF, or a JPG, PNG or WebP photo")


def _clean_name(name: str | None) -> str:
    name = re.sub(r"[\\/\x00-\x1f]", "", (name or "").strip())[-200:]
    return name or "policy document"


def attach(
    db: Session, actor_id: str, family_id: str, policy_id: str, content: bytes, mime: str, name: str | None
) -> InsurancePolicy:
    require(db, actor_id, family_id, "reports.upload")
    policy = _policy(db, family_id, policy_id)
    check_file(content, mime)
    policy.document_data = content
    policy.document_content_type = mime
    policy.document_name = _clean_name(name)
    log_activity(db, family_id, actor_id, "insurance.document_added", "insurance", policy.id,
                 {"insurer": policy.insurer})
    db.commit()
    return policy


def detach(db: Session, actor_id: str, family_id: str, policy_id: str) -> InsurancePolicy:
    require(db, actor_id, family_id, "reports.upload")
    policy = _policy(db, family_id, policy_id)
    policy.document_data = None
    policy.document_content_type = None
    policy.document_name = None
    log_activity(db, family_id, actor_id, "insurance.document_removed", "insurance", policy.id,
                 {"insurer": policy.insurer})
    db.commit()
    return policy


def get_document(db: Session, actor_id: str, family_id: str, policy_id: str) -> tuple[bytes, str, str]:
    require(db, actor_id, family_id, "reports.view")
    policy = _policy(db, family_id, policy_id)
    if policy.document_content_type is None or policy.document_data is None:
        raise NotFound("No document attached")
    return policy.document_data, policy.document_content_type, policy.document_name or "policy document"


# ---- reading a document into the form ----

def _text(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:limit] or None


def _money(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    raw = re.sub(r"[^0-9.]", "", str(value))  # "Rs. 5,00,000" -> "500000"
    try:
        d = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    return d.quantize(Decimal("0.01")) if d.is_finite() and d >= 0 else None


def _date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        d = date.fromisoformat(value.strip())
    except ValueError:
        return None
    return d if 1990 <= d.year <= 2100 else None


def _phone(value: Any) -> str | None:
    text = _text(value, 32)
    return text if text and len(re.sub(r"\D", "", text)) >= 6 else None


EMPTY = {
    "policy_type": None, "insurer": None, "plan_name": None, "policy_number": None, "insured_name": None,
    "sum_insured": None, "premium": None, "premium_frequency": None, "start_date": None, "renewal_date": None,
    "agent_name": None, "agent_phone": None, "helpline": None,
}


def read_document(db: Session, actor_id: str, family_id: str, content: bytes, mime: str) -> dict:
    """What Gemini could read from the document; source "none" when Gemini is off or could not read it."""
    require(db, actor_id, family_id, "reports.upload")
    check_file(content, mime)
    if not settings.gemini_api_key:
        return {**EMPTY, "source": "none"}
    try:
        raw = ask_gemini_image(PROMPT, content, mime)
    except Exception:  # noqa: BLE001 - reading is a help; the family can still type the details
        return {**EMPTY, "source": "none"}
    if not isinstance(raw, dict):
        return {**EMPTY, "source": "none"}
    policy_type = raw.get("policy_type") if raw.get("policy_type") in POLICY_TYPES else None
    frequency = raw.get("premium_frequency") if raw.get("premium_frequency") in FREQUENCIES else None
    return {
        "policy_type": policy_type,
        "insurer": _text(raw.get("insurer"), 120),
        "plan_name": _text(raw.get("plan_name"), 160),
        "policy_number": _text(raw.get("policy_number"), 80),
        "insured_name": _text(raw.get("insured_name"), 120),
        "sum_insured": _money(raw.get("sum_insured")),
        "premium": _money(raw.get("premium")),
        "premium_frequency": frequency,
        "start_date": _date(raw.get("start_date")),
        "renewal_date": _date(raw.get("renewal_date")),
        "agent_name": _text(raw.get("agent_name"), 120),
        "agent_phone": _phone(raw.get("agent_phone")),
        "helpline": _phone(raw.get("helpline")),
        "source": "gemini",
    }
