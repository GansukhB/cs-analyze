"""What Staff plan for a my team (CONTEXT.md: Upcoming match, Team goal,
Practice schedule, Review queue), kept for the v2 pages. All of it belongs to a
Workspace (docs/adr/0011) and is Staff's alone.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, DateTime6, Float, TimestampMixin


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


class TeamGoal(TimestampMixin, Base):
    """A my team's goal (CONTEXT.md: Team goal): one team number on its official
    Matches, optionally on one Map and Side, from a baseline to a target by a day."""

    __tablename__ = "team_goals"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    kpi: Mapped[str] = mapped_column(String(32))  # a key of team_goals.KPIS
    map: Mapped[str] = mapped_column(String(32), default="")
    side: Mapped[str] = mapped_column(String(3), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    baseline: Mapped[float | None] = mapped_column(Float)
    target: Mapped[float] = mapped_column(Float)
    start_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default="active")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class PracticeBlock(TimestampMixin, Base):
    """One block of a my team's Practice schedule (CONTEXT.md): a day, its hours,
    what kind, and the scrim partner when it is a Scrim."""

    __tablename__ = "practice_blocks"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    day: Mapped[date] = mapped_column(Date, index=True)
    start: Mapped[str] = mapped_column(String(5), default="", doc="HH:MM, Ulaanbaatar.")
    end: Mapped[str] = mapped_column(String(5), default="")
    kind: Mapped[str] = mapped_column(String(12))  # scrim, drill, review, match, rest
    title: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(String(500), default="")
    opponent_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("teams.id", ondelete="SET NULL")
    )


class ReviewQueueItem(TimestampMixin, Base):
    """A moment a my team is to watch together in one week (CONTEXT.md: Review
    queue), marked once for the team when it has been watched."""

    __tablename__ = "review_queue_items"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    week: Mapped[date] = mapped_column(Date, index=True, doc="The Monday it belongs to.")
    match_id: Mapped[int] = mapped_column(BigId, ForeignKey("matches.id", ondelete="CASCADE"))
    map_number: Mapped[int] = mapped_column()
    round: Mapped[int] = mapped_column()
    t: Mapped[float] = mapped_column(Float, default=0.0, doc="Seconds from freeze end.")
    seconds: Mapped[int] = mapped_column(default=30)
    title: Mapped[str] = mapped_column(String(300), default="")
    tag: Mapped[str] = mapped_column(String(40), default="")
    source: Mapped[str] = mapped_column(String(80), default="")
    position: Mapped[int] = mapped_column(default=0)
    watched_at: Mapped[datetime | None] = mapped_column(DateTime6)
    watched_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
