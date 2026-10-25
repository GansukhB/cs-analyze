"""What Staff plan for a my team (CONTEXT.md: Upcoming match, Team goal,
Practice schedule, Review queue), kept for the v2 pages. All of it belongs to a
Workspace (docs/adr/0011) and is Staff's alone.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, DateTime6, TimestampMixin


class UpcomingMatch(TimestampMixin, Base):
    """A Match a my team is due to play, as Staff entered it. ``match_id`` is set
    once a stored Match between the two Teams is found around ``starts_at``."""

    __tablename__ = "upcoming_matches"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    opponent_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    starts_at: Mapped[datetime] = mapped_column(DateTime6, doc="UTC.")
    best_of: Mapped[int] = mapped_column(default=3)
    tournament: Mapped[str] = mapped_column(String(160), default="")
    match_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("matches.id", ondelete="SET NULL")
    )
    # The pre-match checklist, [{"text", "done"}], and the counters Staff picked on
    # the scouting page, [{"key", "title", "body"}] (grilling Q8).
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    counters: Mapped[list] = mapped_column(JSON, default=list)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
