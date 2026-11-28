"""One medical file per parent: prescriptions, lab reports, scans, discharge summaries and insurance papers.

Each document is a PDF or a photo (10 MB at most), or only typed text. When Gemini is set up it reads the
document once, on upload, and its words are kept so the file can be searched ("When was the last HbA1c?").
Without Gemini the family types the title and, if they like, the words that matter.

A share link lets a doctor open the file without signing in. The token is `<link id>.<HMAC>`, as for task
links, and is checked for revoking and expiry on every request. The link shows the medical card and the
documents of that one parent, and nothing else.

Reading needs reports.view; adding, deleting and sharing need reports.upload.
"""

import base64
import hashlib
import hmac
import re
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.care_circle import MedicalDocument, MedicalShareLink
from app.models.care_profile import CareProfile
from app.services.activity import log_activity
from app.services.care_circle import _profile_in, card
from app.services.errors import LinkGone, NotFound
from app.services.insurance_document import check_file
from app.services.permissions import require
from app.services.task_links import as_utc
from app.services.understanding import ask_gemini_image

KINDS = ("prescription", "lab", "scan", "discharge", "insurance", "other")
LINK_DAYS = (1, 7, 30)
_STOP = {"when", "was", "the", "last", "what", "is", "a", "an", "of", "my", "her", "his", "their", "did", "do",
         "show", "me", "find", "latest", "recent", "and", "or", "for", "in", "on", "to", "test", "report", "date"}

PROMPT = """This is an Indian medical document (a PDF or a photo of it). Return JSON with:
- "kind": one of prescription, lab, scan, discharge, insurance, other
- "title": a short title, such as "HbA1c and lipid profile" or "Discharge summary, Apollo"
- "doc_date": the date on the document as YYYY-MM-DD, or null
- "text": every test name with its value and unit, every diagnosis and every medicine with its dose, one per
  line, copied as written. Leave out addresses, phone numbers and IDs.
Copy only what is written. Do not guess."""


def _now_date(now: datetime) -> date:
    return now.date()


def _read(content: bytes, mime: str) -> dict:
    if not settings.gemini_api_key:
        return {}
    try:
        raw = ask_gemini_image(PROMPT, content, mime)
    except Exception:  # noqa: BLE001 - reading is a help; the family can still type the title
        return {}
    return raw if isinstance(raw, dict) else {}


def _date(value) -> date | None:
    try:
        d = date.fromisoformat(str(value).strip())
    except ValueError:
        return None
    return d if 1950 <= d.year <= 2100 else None


def add_document(db: Session, actor_id: str, family_id: str, care_profile_id: str, *, kind: str | None,
                 title: str | None, doc_date: date | None, text: str | None, data: bytes | None,
                 mime: str | None, file_name: str | None, now: datetime) -> MedicalDocument:
    require(db, actor_id, family_id, "reports.upload")
    profile = _profile_in(db, family_id, care_profile_id)
    read: dict = {}
    if data is not None:
        check_file(data, mime or "")
        read = _read(data, mime or "")
    elif not (text or "").strip():
        raise ValueError("Add a file or type what the document says")
    kind = kind or (read.get("kind") if read.get("kind") in KINDS else None) or "other"
    if kind not in KINDS:
        raise ValueError("Unknown document kind")
    title = (title or "").strip() or str(read.get("title") or "").strip()[:160] or (file_name or "Document")[:160]
    words = "\n".join(t for t in ((text or "").strip(), str(read.get("text") or "").strip()) if t) or None
    doc = MedicalDocument(
        family_id=family_id, care_profile_id=profile.id, kind=kind, title=title[:160],
        doc_date=doc_date or _date(read.get("doc_date")), text=words, data=data,
        content_type=mime if data is not None else None,
        file_name=re.sub(r"[\\/\x00-\x1f]", "", file_name or "")[-200:] or None if data is not None else None,
        uploaded_by_user_id=actor_id, created_at=now,
    )
    db.add(doc)
    db.flush()
    log_activity(db, family_id, actor_id, "medical_file.added", "medical_document", doc.id, {"kind": kind})
    db.commit()
    return doc


def _docs(db: Session, care_profile_id: str) -> list[MedicalDocument]:
    return list(db.execute(
        select(MedicalDocument).where(MedicalDocument.care_profile_id == care_profile_id)
        .order_by(MedicalDocument.doc_date.desc().nulls_last(), MedicalDocument.created_at.desc())
    ).scalars())


def _words(query: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in _STOP and len(w) > 1]


def _snippet(text: str, word: str) -> str:
    at = text.lower().find(word)
    if at < 0:
        return ""
    line_start = text.rfind("\n", 0, at) + 1
    line_end = text.find("\n", at)
    return text[line_start: line_end if line_end >= 0 else None].strip()[:200]


def search(db: Session, actor_id: str, family_id: str, care_profile_id: str, query: str | None) -> list[dict]:
    """Documents newest first. With a query, only those whose title, kind or words hold a word of it, best
    match first, each with the line that matched, so "When was the last HbA1c?" puts the newest HbA1c on top."""
    require(db, actor_id, family_id, "reports.view")
    _profile_in(db, family_id, care_profile_id)
    docs = _docs(db, care_profile_id)
    words = _words(query or "")
    if not words:
        return [{"doc": d, "match": None} for d in docs]
    found = []
    for i, d in enumerate(docs):
        hay = f"{d.title}\n{d.kind}\n{d.text or ''}".lower()
        hits = [w for w in words if w in hay]
        if hits:
            found.append((-len(hits), i, {"doc": d, "match": _snippet(d.text or "", hits[0]) or None}))
    return [row for *_, row in sorted(found, key=lambda r: (r[0], r[1]))]


def _doc_in(db: Session, care_profile_id: str, doc_id: str) -> MedicalDocument:
    doc = db.get(MedicalDocument, doc_id)
    if doc is None or doc.care_profile_id != care_profile_id:
        raise NotFound("Document not found")
    return doc


def family_document(db: Session, actor_id: str, family_id: str, doc_id: str) -> MedicalDocument:
    require(db, actor_id, family_id, "reports.view")
    doc = db.get(MedicalDocument, doc_id)
    if doc is None or doc.family_id != family_id:
        raise NotFound("Document not found")
    return doc


def delete_document(db: Session, actor_id: str, family_id: str, doc_id: str) -> None:
    require(db, actor_id, family_id, "reports.upload")
    doc = family_document(db, actor_id, family_id, doc_id)
    db.delete(doc)
    log_activity(db, family_id, actor_id, "medical_file.deleted", "medical_document", doc_id, {})
    db.commit()


# ---------- share links ----------

def _signature(link_id: str) -> str:
    digest = hmac.new(settings.secret_key.encode("utf-8"), f"medical-link:{link_id}".encode("utf-8"),
                      hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def token_for(link: MedicalShareLink) -> str:
    return f"{link.id}.{_signature(link.id)}"


def share(db: Session, actor_id: str, family_id: str, care_profile_id: str, days: int,
          now: datetime) -> MedicalShareLink:
    require(db, actor_id, family_id, "reports.upload")
    if days not in LINK_DAYS:
        raise ValueError("A link lasts 1, 7 or 30 days")
    profile = _profile_in(db, family_id, care_profile_id)
    link = MedicalShareLink(family_id=family_id, care_profile_id=profile.id, created_by_user_id=actor_id,
                            expires_at=now + timedelta(days=days), created_at=now)
    db.add(link)
    db.flush()
    log_activity(db, family_id, actor_id, "medical_file.shared", "care_profile", profile.id, {"days": days})
    db.commit()
    return link


def links(db: Session, actor_id: str, family_id: str, care_profile_id: str, now: datetime) -> list[MedicalShareLink]:
    require(db, actor_id, family_id, "reports.upload")
    rows = db.execute(
        select(MedicalShareLink).where(MedicalShareLink.care_profile_id == care_profile_id,
                                       MedicalShareLink.family_id == family_id,
                                       MedicalShareLink.revoked_at.is_(None))
        .order_by(MedicalShareLink.created_at.desc())
    ).scalars()
    return [r for r in rows if as_utc(r.expires_at) > now]


def revoke(db: Session, actor_id: str, family_id: str, link_id: str, now: datetime) -> None:
    require(db, actor_id, family_id, "reports.upload")
    link = db.get(MedicalShareLink, link_id)
    if link is None or link.family_id != family_id:
        raise NotFound("Link not found")
    link.revoked_at = now
    log_activity(db, family_id, actor_id, "medical_file.link_revoked", "care_profile", link.care_profile_id, {})
    db.commit()


def resolve(db: Session, token: str, now: datetime) -> MedicalShareLink:
    link_id, _, signature = token.partition(".")
    if not link_id or not signature or len(link_id) > 36:
        raise NotFound("Link not found")
    if not hmac.compare_digest(signature.encode("utf-8"), _signature(link_id).encode("utf-8")):
        raise NotFound("Link not found")
    link = db.get(MedicalShareLink, link_id)
    if link is None:
        raise NotFound("Link not found")
    if link.revoked_at is not None:
        raise LinkGone("This link was turned off")
    if as_utc(link.expires_at) <= now:
        raise LinkGone("This link has expired")
    return link


def shared_file(db: Session, token: str, now: datetime) -> tuple[MedicalShareLink, dict, list[MedicalDocument]]:
    link = resolve(db, token, now)
    profile = db.get(CareProfile, link.care_profile_id)
    return link, card(db, profile), _docs(db, link.care_profile_id)


def shared_document(db: Session, token: str, doc_id: str, now: datetime) -> MedicalDocument:
    link = resolve(db, token, now)
    return _doc_in(db, link.care_profile_id, doc_id)
