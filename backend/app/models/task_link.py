"""Shareable task links, and the notes and photos people add through them."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.core.db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskShareLink(Base):
    """A link that opens one task without signing in.

    The token is not stored: it is `<id>.<HMAC(secret_key, id)>`, so the link can be shown
    again and a database dump alone cannot open it. Revoking sets revoked_at.
    """

    __tablename__ = "task_share_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TaskNote(Base):
    __tablename__ = "task_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    # Typed by whoever opened the link; it is not a verified identity.
    author_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    share_link_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("task_share_links.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TaskImage(Base):
    __tablename__ = "task_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    data: Mapped[bytes] = deferred(mapped_column(LargeBinary))
    share_link_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("task_share_links.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
