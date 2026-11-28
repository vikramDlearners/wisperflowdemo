"""Background jobs: missed-dose alerts every 10 minutes, daily summaries every 30 minutes, and a summary of
each finished parent chat (with tasks for important points) every 2 minutes, and parent note reminders
every minute.

Started from app.main only when settings.scheduler_enabled is true (tests turn it off).
Each run opens its own database session and closes it.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.services.conversation_summary import summarise_conversations
from app.services.family_alerts import alert_missed_doses, send_daily_summaries
from app.services.parent_notes import deliver_due_reminders
from app.services.fine_checkin import nudge_fine_checkins
from app.services.weekly_summary import send_pattern_warnings, send_weekly_summaries

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def run_job(job: Callable[[Session, datetime], object]) -> None:
    db = SessionLocal()
    try:
        job(db, datetime.now(timezone.utc))
    except Exception:  # noqa: BLE001 - keep the scheduler thread alive; the next run retries
        logger.exception("Scheduled job %s failed", getattr(job, "__name__", job))
        db.rollback()
    finally:
        db.close()


def build_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    common = {"coalesce": True, "max_instances": 1, "replace_existing": True}
    sched.add_job(run_job, "interval", minutes=10, args=[alert_missed_doses], id="alert_missed_doses", **common)
    sched.add_job(run_job, "interval", minutes=30, args=[send_daily_summaries], id="send_daily_summaries", **common)
    sched.add_job(run_job, "interval", minutes=2, args=[summarise_conversations], id="summarise_conversations",
                  **common)
    # Parent notes: reminders are chosen to the minute, so check every minute.
    sched.add_job(run_job, "interval", minutes=1, args=[deliver_due_reminders], id="deliver_note_reminders",
                  **common)
    sched.add_job(run_job, "interval", minutes=5, args=[nudge_fine_checkins], id="nudge_fine_checkins", **common)
    sched.add_job(run_job, "interval", minutes=30, args=[send_weekly_summaries], id="send_weekly_summaries", **common)
    sched.add_job(run_job, "interval", minutes=60, args=[send_pattern_warnings], id="send_pattern_warnings", **common)
    return sched


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        _scheduler = build_scheduler()
        _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
