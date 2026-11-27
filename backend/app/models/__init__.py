"""Import every model module so that Base.metadata registers all tables."""

from app.models.user import User
from app.models.login_token import LoginToken
from app.models.session import AuthSession
from app.models.family import Family
from app.models.role import Role, RolePermission
from app.models.membership import FamilyMember
from app.models.care_profile import CareProfile
from app.models.parent_onboarding_profile import ParentOnboardingProfile
from app.models.parent_invite import ParentInvite
from app.models.medicine import Medicine
from app.models.prescription_scan import MedicineReminder, PrescriptionScan
from app.models.task import Task
from app.models.task_link import TaskImage, TaskNote, TaskShareLink
from app.models.appointment import Appointment
from app.models.dose import MedicineDose
from app.models.checkin import ChatMessage, HealthCheckin
from app.models.meal import MealLog
from app.models.emergency import Emergency
from app.models.conversation_summary import ConversationSummary
from app.models.notification import Notification
from app.models.activity import ActivityLog
from app.models.app_setting import AppSetting

__all__ = [
    "User",
    "LoginToken",
    "AuthSession",
    "Family",
    "Role",
    "RolePermission",
    "FamilyMember",
    "CareProfile",
    "ParentOnboardingProfile",
    "ParentInvite",
    "Medicine",
    "PrescriptionScan",
    "MedicineReminder",
    "Task",
    "TaskShareLink",
    "TaskNote",
    "TaskImage",
    "Appointment",
    "MedicineDose",
    "HealthCheckin",
    "ChatMessage",
    "MealLog",
    "Emergency",
    "ConversationSummary",
    "Notification",
    "ActivityLog",
    "AppSetting",
]
