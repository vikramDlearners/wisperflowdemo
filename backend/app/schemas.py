"""Request and response models for the API."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class UserOut(BaseModel):
    id: str
    email: str | None
    display_name: str
    role: str | None = None
    other_role: str | None = None


class RoleIn(BaseModel):
    role: Literal["parent", "caretaker", "hospital", "manager", "others"]
    other_role: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _require_other_role_for_others(self) -> "RoleIn":
        if self.role == "others":
            text = (self.other_role or "").strip()
            if not text:
                raise ValueError("other_role is required when role is 'others'")
            self.other_role = text
        return self


class SignInRequest(BaseModel):
    email: EmailStr
    display_name: str | None = Field(default=None, max_length=255)


class VerifyRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ParentInviteAccept(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class SessionOut(BaseModel):
    session_token: str
    user: UserOut


class FamilyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class FamilyOut(BaseModel):
    id: str
    name: str


class MemberOut(BaseModel):
    membership_id: str
    user_id: str
    display_name: str
    email: str | None
    role_id: str
    role_name: str
    relationship: str | None = None


RelationshipIn = Literal["mother", "father", "grandmother", "grandfather", "son", "daughter", "other"]



class MemberCreate(BaseModel):
    # An email, a mobile number, or both. A parent is often added by mobile number only.
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    display_name: str | None = Field(default=None, max_length=255)
    role_id: str
    relationship: RelationshipIn | None = None
    # Link this member to an existing care profile of the family instead of creating a new one.
    care_profile_id: str | None = None

    @model_validator(mode="after")
    def _email_or_phone(self) -> "MemberCreate":
        if not self.email and not (self.phone and self.phone.strip()):
            raise ValueError("Enter an email address or a mobile number")
        return self


class MemberRoleChange(BaseModel):
    role_id: str


class RoleOut(BaseModel):
    id: str
    name: str
    is_system: bool
    permissions: list[str]


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    permissions: list[str]


class RolePermissionsUpdate(BaseModel):
    permissions: list[str]


class MyAccess(BaseModel):
    role: str
    permissions: list[str]


_TIMEZONES = frozenset(available_timezones())


def _valid_timezone(value: str | None) -> str | None:
    if value is not None and value not in _TIMEZONES:
        raise ValueError("timezone must be a valid IANA time zone, e.g. Asia/Kolkata")
    return value


class CareProfileCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    greeting_name: str = Field(min_length=1, max_length=255)
    preferred_language: str = "en"
    timezone: str = "Asia/Kolkata"

    _timezone = field_validator("timezone")(_valid_timezone)


class CareProfileUpdate(BaseModel):
    display_name: str | None = None
    greeting_name: str | None = None
    preferred_language: str | None = None
    timezone: str | None = None

    _timezone = field_validator("timezone")(_valid_timezone)


class CareProfileOut(BaseModel):
    id: str
    display_name: str
    greeting_name: str
    preferred_language: str
    timezone: str


class MedicineCreate(BaseModel):
    care_profile_id: str
    display_name: str = Field(min_length=1, max_length=255)
    instructions_text: str | None = None
    purpose: str | None = Field(default=None, max_length=120)
    quantity_remaining: int | None = None
    refill_date: date | None = None
    take_until: date | None = None
    responsible_user_id: str | None = None
    appointment_id: str | None = None


class MedicineUpdate(BaseModel):
    display_name: str | None = None
    instructions_text: str | None = None
    purpose: str | None = Field(default=None, max_length=120)
    refill_date: date | None = None
    take_until: date | None = None
    appointment_id: str | None = None
    responsible_user_id: str | None = None
    active: bool | None = None
    unit_price: Decimal | None = Field(default=None, ge=0)
    total_medicine_count: int | None = Field(default=None, ge=0)


class RemindParentIn(BaseModel):
    care_profile_id: str


class RemindParentOut(BaseModel):
    sent_at: datetime
    channels: list[str]  # "whatsapp", "sms", "app"
    sent_to: str | None = None  # masked phone number
    medicines: list[str]
    message: str


class MedicineTextIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class MedicineTextOut(BaseModel):
    instructions_text: str | None = None
    reminder_times: list[str] = []
    quantity_remaining: int | None = None
    unit_price: Decimal | None = None
    total_medicine_count: int | None = None
    source: str


class QuantityUpdate(BaseModel):
    quantity: int = Field(ge=0)


class MedicineOut(BaseModel):
    id: str
    care_profile_id: str
    display_name: str
    instructions_text: str | None
    purpose: str | None = None
    quantity_remaining: int | None
    refill_date: date | None
    take_until: date | None = None
    appointment_id: str | None = None
    responsible_user_id: str | None
    active: bool
    prescription_scan_id: str | None = None
    has_image: bool = False
    image_url: str | None = None
    has_prescription_image: bool = False
    unit_price: Decimal | None = None
    total_medicine_count: int | None = None
    total_price: Decimal | None = None


class DoseRecordIn(BaseModel):
    care_profile_id: str
    medicine_id: str
    slot: str
    status: Literal["taken", "skipped"]


class MedicineLastTakenOut(BaseModel):
    medicine_id: str
    last_taken_at: datetime | None



class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    due_at: datetime | None = None
    priority: str = "normal"
    assigned_to_user_id: str | None = None
    care_profile_id: str | None = None


class AskIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    tried: list[str] = Field(default_factory=list, max_length=30)  # pages already opened for this question


class AskOut(BaseModel):
    destination: str | None = None
    available: bool


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


InsuranceType = Literal["health", "life", "accident", "critical_illness", "home", "vehicle", "other"]
PremiumFrequency = Literal["yearly", "half_yearly", "quarterly", "monthly"]


class InsuranceIn(BaseModel):
    care_profile_id: str | None = None  # whose cover; empty for a family policy
    policy_type: InsuranceType = "health"
    insurer: str = Field(min_length=1, max_length=120)
    plan_name: str | None = Field(default=None, max_length=160)
    policy_number: str | None = Field(default=None, max_length=80)
    sum_insured: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    premium: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    premium_frequency: PremiumFrequency = "yearly"
    start_date: date | None = None
    renewal_date: date
    agent_name: str | None = Field(default=None, max_length=120)
    agent_phone: str | None = Field(default=None, max_length=32)
    helpline: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=4000)
    responsible_user_id: str | None = None


class InsuranceUpdate(BaseModel):
    care_profile_id: str | None = None
    policy_type: InsuranceType | None = None
    insurer: str | None = Field(default=None, max_length=120)
    plan_name: str | None = Field(default=None, max_length=160)
    policy_number: str | None = Field(default=None, max_length=80)
    sum_insured: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    premium: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    premium_frequency: PremiumFrequency | None = None
    start_date: date | None = None
    renewal_date: date | None = None
    agent_name: str | None = Field(default=None, max_length=120)
    agent_phone: str | None = Field(default=None, max_length=32)
    helpline: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=4000)
    responsible_user_id: str | None = None


class InsuranceRenewIn(BaseModel):
    renewal_date: date | None = None  # the insurer's new date; default: one premium period later
    premium: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class InsuranceOut(BaseModel):
    id: str
    care_profile_id: str | None
    policy_type: str
    insurer: str
    plan_name: str | None
    policy_number: str | None
    sum_insured: Decimal | None
    premium: Decimal | None
    premium_frequency: str
    start_date: date | None
    renewal_date: date
    last_renewed_on: date | None
    agent_name: str | None
    agent_phone: str | None
    helpline: str | None
    notes: str | None
    responsible_user_id: str | None
    has_document: bool = False
    document_name: str | None = None
    document_type: str | None = None  # e.g. application/pdf


class InsuranceDocumentRead(BaseModel):
    """What could be read from an uploaded policy document, to fill in the form (nothing is saved)."""
    policy_type: str | None = None
    insurer: str | None = None
    plan_name: str | None = None
    policy_number: str | None = None
    insured_name: str | None = None
    sum_insured: Decimal | None = None
    premium: Decimal | None = None
    premium_frequency: str | None = None
    start_date: date | None = None
    renewal_date: date | None = None
    agent_name: str | None = None
    agent_phone: str | None = None
    helpline: str | None = None
    source: Literal["gemini", "none"]


class FamilyChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    # The saved conversation this question continues; omitted for a new chat. Its saved turns are the history.
    conversation_id: str | None = None
    history: list[ChatMessageIn] = Field(default_factory=list, max_length=12)


class FamilyChatOut(BaseModel):
    reply: str
    destination: str | None = None  # a page key, as in AskOut
    source: Literal["ai", "rules"]
    conversation_id: str | None = None
    card: dict | None = None  # e.g. the month's analysis


class FamilyChatLogIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    reply: str = Field(min_length=1, max_length=4000)
    destination: str | None = Field(default=None, max_length=60)
    conversation_id: str | None = None


class FamilyChatSavedOut(BaseModel):
    conversation_id: str


class FamilyChatMessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    destination: str | None = None
    card: dict | None = None
    created_at: datetime


class FamilyChatConversationOut(BaseModel):
    id: str
    title: str
    updated_at: datetime
    message_count: int = 0


class FamilyChatConversationDetailOut(BaseModel):
    id: str
    title: str
    updated_at: datetime
    messages: list[FamilyChatMessageOut]


class FamilyChatImportMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)
    destination: str | None = Field(default=None, max_length=60)


class FamilyChatImportItem(BaseModel):
    title: str = Field(default="", max_length=200)
    messages: list[FamilyChatImportMessage] = Field(default_factory=list, max_length=200)


class FamilyChatImportIn(BaseModel):
    conversations: list[FamilyChatImportItem] = Field(max_length=30)


class TaskTextIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    # The family member's own date, so "tomorrow" means their tomorrow; defaults to the server's date.
    today: date | None = None


class TaskTextOut(BaseModel):
    title: str | None = None
    description: str | None = None
    due_date: date | None = None
    priority: str = "normal"
    assignee_user_id: str | None = None
    assignee_name: str | None = None
    source: str


class TaskAssign(BaseModel):
    assignee_user_id: str


class TaskStatusUpdate(BaseModel):
    status: str


class TaskOut(BaseModel):
    id: str
    title: str
    description: str | None
    due_at: datetime | None
    status: str
    priority: str
    assigned_to_user_id: str | None
    created_by_user_id: str


class TaskShareLinkOut(BaseModel):
    token: str
    path: str  # frontend route that opens the link, e.g. /task-link/<token>
    expires_at: datetime


class TaskLinkNoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    author_name: str | None = Field(default=None, max_length=100)


class TaskLinkNoteOut(BaseModel):
    id: str
    body: str
    author_name: str | None
    created_at: datetime


class TaskLinkImageOut(BaseModel):
    id: str
    url: str
    content_type: str
    size_bytes: int
    created_at: datetime


class TaskLinkView(BaseModel):
    id: str
    title: str
    description: str | None
    due_at: datetime | None
    status: str
    priority: str
    assignee_name: str | None
    link_expires_at: datetime
    notes: list[TaskLinkNoteOut]
    images: list[TaskLinkImageOut]


class NotificationOut(BaseModel):
    id: str
    family_id: str | None
    type: str
    payload: dict | None
    status: str
    created_at: datetime


class NotificationSummaryOut(BaseModel):
    summary: str | None = None
    count: int
    days: int
    error: str | None = None


class ActivityOut(BaseModel):
    id: str
    actor_id: str | None
    action: str
    object_type: str
    object_id: str | None
    metadata: dict | None
    created_at: datetime


class ConversationSummaryOut(BaseModel):
    id: str
    checkin_id: str
    care_profile_id: str
    from_seq: int
    to_seq: int
    summary: str
    important: list | None
    source: str
    created_at: datetime


class IntentModeOut(BaseModel):
    intent_mode: str


class IntentModeUpdate(BaseModel):
    intent_mode: str


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    due_at: datetime | None = None
    priority: str | None = None


AppointmentStatusIn = Literal["scheduled", "completed", "cancelled", "rescheduled"]


class AppointmentCreate(BaseModel):
    family_id: str
    care_recipient_id: str
    scheduled_date: date
    start_time: str = Field(min_length=1, max_length=8)
    provider: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    notes: str = ""
    fee: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    doctor_notes: str | None = None
    responsible_user_id: str | None = None


class AppointmentUpdate(BaseModel):
    care_recipient_id: str | None = None
    scheduled_date: date | None = None
    start_time: str | None = Field(default=None, min_length=1, max_length=8)
    provider: str | None = Field(default=None, min_length=1, max_length=255)
    reason: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    status: AppointmentStatusIn | None = None
    fee: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    doctor_notes: str | None = None
    responsible_user_id: str | None = None


class AppointmentMedicineOut(BaseModel):
    id: str
    display_name: str
    active: bool


class AppointmentMedicinesIn(BaseModel):
    medicine_ids: list[str] = Field(max_length=100)


class AppointmentOut(BaseModel):
    id: str
    care_recipient_id: str
    scheduled_date: date
    start_time: str
    provider: str
    reason: str
    location: str | None = None
    notes: str
    status: AppointmentStatusIn
    fee: Decimal | None = None
    doctor_notes: str | None = None
    responsible_user_id: str | None = None
    # Medicines the doctor gave at this appointment.
    medicines: list[AppointmentMedicineOut] = []


class AppointmentTextIn(BaseModel):
    family_id: str
    text: str = Field(min_length=1, max_length=2000)
    today: date | None = None  # the family member's own date, so "tomorrow" means their tomorrow


class AppointmentTextOut(BaseModel):
    care_recipient_id: str | None = None
    care_recipient_name: str | None = None
    reason: str | None = None
    provider: str | None = None
    location: str | None = None
    scheduled_date: date | None = None
    start_time: str | None = None
    notes: str | None = None
    source: str


class AppointmentListOut(BaseModel):
    upcoming: list[AppointmentOut]
    past: list[AppointmentOut]


class SignUpRequest(BaseModel):
    email: str
    display_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: str


class VerifyOtpRequest(BaseModel):
    email: str
    code: str = Field(min_length=6, max_length=6)


LanguageIn = Literal["English", "Tamil", "Hindi", "Telugu", "Malayalam", "Kannada"]
SectionIn = Literal["parent", "communication", "care", "medical", "additional"]

# Which profile fields each onboarding section may write.
SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    "parent": (
        "parent_full_name",
        "preferred_name",
        "relationship",
        "date_of_birth",
        "approximate_age",
        "preferred_language",
    ),
    "communication": ("parent_mobile", "preferred_language"),
    "care": ("caregiver_name", "caregiver_relationship", "caregiver_phone", "caregiver_email"),
    "medical": (
        "known_health_conditions",
        "allergies",
        "primary_doctor_name",
        "doctor_contact_number",
        "preferred_hospital",
        "care_instructions",
        "deficiencies",
        "notes",
    ),
    "additional": ("profile_picture_url",),
}


class ProfileIn(BaseModel):
    section: SectionIn
    parent_full_name: str | None = Field(default=None, max_length=120)
    preferred_name: str | None = Field(default=None, max_length=60)
    relationship: RelationshipIn | None = None
    date_of_birth: date | None = None
    approximate_age: int | None = Field(default=None, ge=0, le=150)
    profile_picture_url: str | None = Field(default=None, max_length=500)
    preferred_language: LanguageIn | None = None
    parent_mobile: str | None = Field(default=None, max_length=20)
    known_health_conditions: str | None = None
    allergies: str | None = None
    primary_doctor_name: str | None = Field(default=None, max_length=120)
    doctor_contact_number: str | None = Field(default=None, max_length=30)
    preferred_hospital: str | None = Field(default=None, max_length=160)
    care_instructions: str | None = None
    deficiencies: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=500)
    caregiver_name: str | None = Field(default=None, max_length=120)
    caregiver_relationship: str | None = Field(default=None, max_length=60)
    caregiver_phone: str | None = Field(default=None, max_length=30)
    caregiver_email: str | None = Field(default=None, max_length=254)

    @field_validator("*", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        # Blank strings count as not sent, so they clear the field instead of being stored.
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("date_of_birth")
    @classmethod
    def _dob_not_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return value

    @model_validator(mode="after")
    def _check_section(self) -> "ProfileIn":
        if self.section == "parent":
            for name in ("parent_full_name", "preferred_name", "relationship"):
                if not getattr(self, name):
                    raise ValueError(f"{name} is required in the parent section")
        allowed = set(SECTION_FIELDS[self.section])
        stray = sorted(
            name
            for name in self.model_fields_set
            if name != "section" and name not in allowed
        )
        if stray:
            raise ValueError(f"fields not allowed in section '{self.section}': {', '.join(stray)}")
        return self


class CompletionOut(BaseModel):
    overall: int
    sections: dict[str, int]


class ProfileOut(BaseModel):
    # True when a photo was uploaded (fetch it from .../profile/photo).
    has_photo: bool = False
    parent_full_name: str | None
    preferred_name: str | None
    relationship: str | None
    date_of_birth: date | None
    approximate_age: int | None
    age: int | None
    profile_picture_url: str | None
    preferred_language: str | None
    parent_mobile: str | None
    known_health_conditions: str | None
    allergies: str | None
    primary_doctor_name: str | None
    doctor_contact_number: str | None
    preferred_hospital: str | None
    care_instructions: str | None
    deficiencies: str | None
    notes: str | None
    caregiver_name: str | None
    caregiver_relationship: str | None
    caregiver_phone: str | None
    caregiver_email: str | None
    updated_at: datetime | None
    completion: CompletionOut


_HH_MM = re.compile(r"([01][0-9]|2[0-3]):[0-5][0-9]")


def _validate_hh_mm_list(values: list[str]) -> list[str]:
    for value in values:
        if not _HH_MM.fullmatch(value):
            raise ValueError(f"time must be 24-hour HH:MM: {value}")
    return values


class PrescriptionScanOut(BaseModel):
    id: str
    document_type: str
    status: str
    proposed: dict | None
    # What the app will keep track of from this upload, one plain line each.
    tracking: list[str] = []


class PrescriptionMedicineIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    dose: str | None = Field(default=None, max_length=120)
    instructions: str | None = Field(default=None, max_length=2000)
    times: list[str] = Field(min_length=1, max_length=12)
    responsible_user_id: str | None = None

    @field_validator("times")
    @classmethod
    def _times_are_hh_mm(cls, values: list[str]) -> list[str]:
        return _validate_hh_mm_list(values)


class ReminderTimesIn(BaseModel):
    times: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("times")
    @classmethod
    def _times_are_hh_mm(cls, values: list[str]) -> list[str]:
        return _validate_hh_mm_list(values)


class ReminderTimesOut(BaseModel):
    times: list[str]


class PrescriptionScanConfirm(BaseModel):
    medicines: list[PrescriptionMedicineIn] = Field(min_length=1, max_length=50)


class PrescriptionScanConfirmOut(BaseModel):
    medicine_ids: list[str]
    notified_user_ids: list[str]




# ---------- parent check-in ----------

class ChatMessageOut(BaseModel):
    sender: Literal["bot", "parent"]
    text: str
    created_at: datetime
    # True for "Here is the photo of ...": the chat shows the photos of the medicines it names.
    photos: bool = False


class ReminderDueOut(BaseModel):
    medicine_id: str
    name: str
    slot: str
    remind_at: datetime


class CheckinOut(BaseModel):
    checkin_id: str
    # The parent's family, for the "Move to Portal" link to its Overview page.
    family_id: str
    # True when the parent may open that page (dashboard.view); otherwise the link is not shown.
    can_open_portal: bool = False
    step: str
    messages: list[ChatMessageOut]
    call_number: str | None
    # The family's phone for the Help button, whether or not anything urgent was reported.
    help_number: str | None
    language: str
    # The language on the parent's profile, kept when the parent switches the chat to another one.
    recommended_language: str
    reminders_due: list[ReminderDueOut]
    # Speech for the bot messages this request stored (greeting / re-asked question), else null.
    audio: str | None = None
    audio_type: str | None = None


class ParentLanguageIn(BaseModel):
    language: Literal["en", "ta", "hi", "te", "ml", "kn"]


class ParentSpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class SpeechOut(BaseModel):
    # None when speech is unavailable: the page then uses the device's own voice.
    audio: str | None
    audio_type: str | None


class ParentMedicineOut(BaseModel):
    id: str
    name: str
    has_image: bool


class EmergencyOut(BaseModel):
    notified: list[str]
    channels: list[str]
    emergency_number: str


class ParentTextIn(BaseModel):
    text: str = Field(max_length=2000)


class ParentProfileOut(BaseModel):
    """A profile the signed-in parent can use the chat as."""

    id: str
    name: str
    relationship: str | None
    has_photo: bool
    photo_url: str | None
    own: bool


class TurnMessageOut(BaseModel):
    photos: bool = False
    sender: Literal["bot", "parent"]
    text: str


class TurnOut(BaseModel):
    messages: list[TurnMessageOut]
    step: str
    language: str
    urgent: bool
    call_number: str | None
    help_number: str | None
    audio: str | None
    audio_type: str | None


class VoiceTurnOut(TurnOut):
    transcript: str


# ---------- family dashboard ----------

class DashboardParentOut(BaseModel):
    care_profile_id: str
    display_name: str
    relationship: str | None
    age: int | None
    photo_url: str | None
    has_photo: bool = False
    known_health_conditions: str | None
    primary_caregiver_name: str | None
    gender: str | None = None
    all_good: bool


class DashboardMedicinesTodayOut(BaseModel):
    taken: int
    total: int


class DashboardScheduleItemOut(BaseModel):
    medicine_id: str
    medicine_name: str
    slot: str
    status: str | None


class DashboardStockItemOut(BaseModel):
    medicine_id: str
    display_name: str
    instructions_text: str | None
    purpose: str | None
    quantity_remaining: int | None
    days_left: float | None
    low: bool


class DashboardNextMonthItemOut(BaseModel):
    # One medicine's share of the money to keep aside for the next month.
    medicine_id: str
    display_name: str
    doses_per_day: int
    days_needed: int  # days of the next month the course still runs (take_until), else the whole month
    take_until: date | None
    tablets_needed: int
    in_stock: int | None  # None when the stock was never entered; counted as 0
    to_buy: int  # tablets_needed minus what is in stock, never below 0
    unit_price: float | None
    cost: float | None  # None when the medicine has no price


class DashboardNextMonthEstimateOut(BaseModel):
    # Money to keep aside so the selected profile's medicines don't run out over the next month.
    amount: float | None  # None when no active medicine has a price yet
    days: int
    priced_count: int
    unpriced_count: int  # medicines that need buying but have no price, so are left out of amount
    items: list[DashboardNextMonthItemOut] = []


class DashboardAppointmentOut(BaseModel):
    id: str
    title: str
    doctor: str
    location: str | None
    scheduled_date: date
    start_time: str


class DashboardEmergencyOut(BaseModel):
    active: bool
    last_check_at: datetime | None


class DashboardActivityOut(BaseModel):
    id: str
    text: str
    created_at: datetime


class DashboardEmergencyItemOut(BaseModel):
    id: str
    care_profile_id: str
    parent_name: str
    text: str
    source: str
    created_at: datetime


class DoseHistoryItemOut(BaseModel):
    dose_date: date
    slot: str
    medicine_name: str
    status: str
    source: str
    recorded_at: datetime


class DashboardResponse(BaseModel):
    parents: list[DashboardParentOut]
    selected_care_profile_id: str | None
    on_date: date
    daily_medicine_count: int
    medicines_today: DashboardMedicinesTodayOut
    today_schedule: list[DashboardScheduleItemOut]
    medicine_stock: list[DashboardStockItemOut]
    next_month_estimate: DashboardNextMonthEstimateOut
    next_appointment: DashboardAppointmentOut | None
    emergency: DashboardEmergencyOut
    recent_activity: list[DashboardActivityOut]
    emergencies: list[DashboardEmergencyItemOut]

