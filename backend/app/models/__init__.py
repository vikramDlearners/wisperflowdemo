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
    "Notification",
    "ActivityLog",
    "AppSetting",
]
