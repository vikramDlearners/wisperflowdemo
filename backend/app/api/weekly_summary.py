"""The family's weekly summary of one parent (see app/services/weekly_summary.py).

GET /api/families/{family_id}/care-profiles/{care_profile_id}/weekly-summary?end=YYYY-MM-DD
needs parent_profile.view. Without `end` the week ends today in the parent's time zone.
"""

from dataclasses import asdict
from datetime import date, datetime, timezone

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.models.care_profile import CareProfile
from app.models.user import User
from app.services import care_circle, today_plan
from app.services import weekly_summary as svc
from app.services.errors import NotFound
from app.services.permissions import require

router = APIRouter(prefix="/api/families/{family_id}/care-profiles/{care_profile_id}/weekly-summary",
                   tags=["weekly-summary"])


@router.get("")
def weekly_summary(family_id: str, care_profile_id: str, end: date | None = Query(default=None),
                   db: Session = DbSession, user: User = CurrentUser) -> dict:
    require(db, user.id, family_id, "parent_profile.view")
    profile = db.get(CareProfile, care_profile_id)
    if profile is None or profile.family_id != family_id:
        raise NotFound("Care profile not found")
    week = svc.build_week(db, profile, datetime.now(timezone.utc), end)
    return {**asdict(week), "parent_name": profile.display_name, "lines": svc.summary_lines(profile, week)}


@router.get("/visit-prep")
def visit_prep(family_id: str, care_profile_id: str, db: Session = DbSession, user: User = CurrentUser) -> dict:
    """What to tell the doctor at the next visit, from the last two weeks, and the medicines running low."""
    require(db, user.id, family_id, "parent_profile.view")
    profile = db.get(CareProfile, care_profile_id)
    if profile is None or profile.family_id != family_id:
        raise NotFound("Care profile not found")
    now = datetime.now(timezone.utc)
    return {
        "points": [asdict(p) for p in today_plan.visit_points(db, profile, now)
                   if p.kind != "said" or care_circle.shares_words(db, profile.id)],
        "refills": [asdict(r) for r in today_plan.refills(db, profile, now, profile.linked_user_id)],
    }
