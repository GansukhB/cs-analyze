"""Development plans (CONTEXT.md: Development plan; docs/plans/07 RV-9).

A goal is one Player's KPI over a block of weeks: where it stood when the goal
was set, where Staff want it, and by when. Its progress is read from the
Player's Match Maps and Scrims since it started, never typed in.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, Float, TimestampMixin


class GoalStatus(StrEnum):
    ACTIVE = "active"
    DONE = "done"
    DROPPED = "dropped"


class DevelopmentGoal(TimestampMixin, Base):
    __tablename__ = "development_goals"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("players.id", ondelete="CASCADE"), index=True
    )
    kpi: Mapped[str] = mapped_column(String(32))  # a key of development.KPIS
    baseline: Mapped[float | None] = mapped_column(Float)
    target: Mapped[float] = mapped_column(Float)
    start_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12), default=GoalStatus.ACTIVE)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
