"""What was done in a Workspace, and by whom (docs/plans/01 WS-7).

One row per action that changes who can see or do what: a member's role or
access changed, an invite made, revoked or used, a Briefing shared or deleted,
a Strat or a Playlist deleted. Written in the action's own transaction, so a
change that rolls back leaves no line; read by Staff on the Workspace page.
"""

from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, TimestampMixin


class AuditEvent(TimestampMixin, Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    # None for the server CLI.
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40))  # e.g. "member.change", "briefing.share"
    subject: Mapped[str] = mapped_column(String(160), default="")  # what it was done to, worded
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
