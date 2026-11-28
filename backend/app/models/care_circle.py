"""The care-circle features from TODO.md: errands for the family, posts to the parent, contacts, the medical
card, the parent's privacy choices, the medical file, shared costs and visits, video check-ins, paperwork
dates, and the carer's reports."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _family() -> Mapped[str]:
    return mapped_column(String(36), ForeignKey("families.id", ondelete="CASCADE"))


def _profile() -> Mapped[str]:
    return mapped_column(String(36), ForeignKey("care_profiles.id", ondelete="CASCADE"), index=True)


def _user(nullable: bool = False) -> Mapped:
    return mapped_column(String(36), ForeignKey("users.id"), nullable=nullable)


class HelpRequest(Base):
    """Something the parent can't do alone (a bill, groceries, a cab, a nurse). A family member approves it."""

    __tablename__ = "help_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = _family()
    care_profile_id: Mapped[str] = _profile()
    kind: Mapped[str] = mapped_column(String(20))  # bill | groceries | cab | nurse | other
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="asked")  # asked | approved | declined | done
    asked_by_user_id: Mapped[str | None] = _user(nullable=True)
    decided_by_user_id: Mapped[str | None] = _user(nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class FamilyPost(Base):
    """A photo, voice note or line from a family member, shown in the parent's chat."""

    __tablename__ = "family_posts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = _family()
    care_profile_id: Mapped[str] = _profile()
    author_user_id: Mapped[str] = _user()
    kind: Mapped[str] = mapped_column(String(8))  # text | photo | voice
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CareContact(Base):
    """One person in the parent's circle: doctor, pharmacy, hospital, neighbour, driver, friend."""

    __tablename__ = "care_contacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = _family()
    care_profile_id: Mapped[str] = _profile()
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(240), nullable=True)
    birthday_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    birthday_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CareCard(Base):
    """What the medical card and emergency screen need that the app does not already keep elsewhere."""

    __tablename__ = "care_cards"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    care_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("care_profiles.id", ondelete="CASCADE"), unique=True
    )
    blood_group: Mapped[str | None] = mapped_column(String(8), nullable=True)
    emergency_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    emergency_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ParentPrivacy(Base):
    """What the parent lets the family see. No row means the defaults: words and chats shared, no auto-answer."""

    __tablename__ = "parent_privacy"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    care_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("care_profiles.id", ondelete="CASCADE"), unique=True
    )
    share_words: Mapped[bool] = mapped_column(Boolean, default=True)
    share_chats: Mapped[bool] = mapped_column(Boolean, default=True)
    video_auto_answer: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MedicalDocument(Base):
    """A prescription, lab report, scan, discharge summary or insurance paper, with its text for search."""

    __tablename__ = "medical_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = _family()
    care_profile_id: Mapped[str] = _profile()
    kind: Mapped[str] = mapped_column(String(20))  # prescription | lab | scan | discharge | insurance | other
    title: Mapped[str] = mapped_column(String(160))
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    uploaded_by_user_id: Mapped[str | None] = _user(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MedicalShareLink(Base):
    """A read-only link to the medical file for a doctor. The token is `<id>.<HMAC>`, as for task links."""

    __tablename__ = "medical_share_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = _family()
    care_profile_id: Mapped[str] = _profile()
    created_by_user_id: Mapped[str] = _user()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CareExpense(Base):
    """Money one family member spent on the parent's care, split between the siblings."""

    __tablename__ = "care_expenses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = _family()
    care_profile_id: Mapped[str] = _profile()
    paid_by_user_id: Mapped[str] = _user()
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    what: Mapped[str] = mapped_column(String(160))
    spent_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CareVisit(Base):
    """A family member's visit to the parent, or who went with them to an appointment."""

    __tablename__ = "care_visits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = _family()
    care_profile_id: Mapped[str] = _profile()
    user_id: Mapped[str] = _user()
    visit_date: Mapped[date] = mapped_column(Date)
    appointment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("appointments.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VideoCall(Base):
    """One video check-in. The two browsers swap their WebRTC offer, answer and network candidates here."""

    __tablename__ = "video_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = _family()
    care_profile_id: Mapped[str] = _profile()
    caller_user_id: Mapped[str] = _user()
    status: Mapped[str] = mapped_column(String(12), default="ringing")  # ringing | live | ended
    offer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    caller_ice: Mapped[list] = mapped_column(JSON, default=list)
    callee_ice: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperworkItem(Base):
    """A dated chore: pension life certificate, tax, bank KYC, property tax, an insurance renewal."""

    __tablename__ = "paperwork_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = _family()
    care_profile_id: Mapped[str] = _profile()
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(160))
    due_date: Mapped[date] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    done_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[str | None] = _user(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CarerReport(Base):
    """A concern or note from a live-in helper or nurse."""

    __tablename__ = "carer_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    family_id: Mapped[str] = _family()
    care_profile_id: Mapped[str] = _profile()
    user_id: Mapped[str] = _user()
    kind: Mapped[str] = mapped_column(String(12))  # concern | note
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
