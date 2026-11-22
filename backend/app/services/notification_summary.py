"""Plain-English summary of a user's notifications from the last 7 days, written by Gemini.

The summary is advisory: any failure returns a short fixed error message, never an exception, so the
notifications screen still works without Gemini.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.notification import Notification
from app.services import understanding

logger = logging.getLogger(__name__)

SUMMARY_DAYS = 7
MAX_NOTIFICATIONS = 100
EMPTY_MESSAGE = "No notifications in the last 7 days."
UNAVAILABLE_MESSAGE = "Summary is unavailable right now."
NOT_CONFIGURED_MESSAGE = "Summary is unavailable: the Gemini key is not configured."


def _as_utc(value: datetime) -> datetime:
    # Naive datetimes (SQLite returns them without a zone) are stored as UTC.
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _prompt(rows: list[Notification]) -> str:
    lines = [
        json.dumps(
            {
                "type": row.type,
                "created_at": _as_utc(row.created_at).isoformat(),
                "payload": row.payload,
            },
            ensure_ascii=False,
        )
        for row in rows
    ]
    return (
        f"Below are one family's in-app notifications from the last {SUMMARY_DAYS} days, one JSON object per "
        "line (type, created_at, payload). "
        + "\n".join(lines)
        + ' Summarise them for the family in plain English. Respond only with JSON: {"summary": "<a short '
        "plain-English summary of the week's notifications for the family, 3-6 sentences>\"}."
    )


def summarise_recent(db: Session, user_id: str, now: datetime) -> dict[str, Any]:
    cutoff = _as_utc(now) - timedelta(days=SUMMARY_DAYS)
    window = (
        Notification.recipient_user_id == user_id,
        Notification.created_at >= cutoff,
    )
    count = db.execute(select(func.count()).select_from(Notification).where(*window)).scalar_one()
    if count == 0:
        return {"summary": EMPTY_MESSAGE, "count": 0, "days": SUMMARY_DAYS, "error": None}

    if not settings.gemini_api_key:
        return {"summary": None, "count": count, "days": SUMMARY_DAYS, "error": NOT_CONFIGURED_MESSAGE}

    rows = list(
        db.execute(
            select(Notification)
            .where(*window)
            .order_by(Notification.created_at.desc())
            .limit(MAX_NOTIFICATIONS)
        ).scalars()
    )
    try:
        result = understanding.ask_gemini(_prompt(rows))
        text = result.get("summary")
    except Exception as exc:
        logger.warning("Notification summary failed: %s: %s", type(exc).__name__, exc)
        return {"summary": None, "count": count, "days": SUMMARY_DAYS, "error": UNAVAILABLE_MESSAGE}

    if not isinstance(text, str) or not text.strip():
        logger.warning("Notification summary failed: Gemini returned no summary text")
        return {"summary": None, "count": count, "days": SUMMARY_DAYS, "error": UNAVAILABLE_MESSAGE}
    return {"summary": text.strip(), "count": count, "days": SUMMARY_DAYS, "error": None}
