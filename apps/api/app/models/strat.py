"""The Stratbook (CONTEXT.md: Stratbook, Strat; docs/plans/08 SB-1, SB-7).

A Strat is written by Staff for one of the Workspace's my teams on one Map and
Side: its name and kind, who does what in each slot, its grenades with their
timing, the calls, and example Rounds from Matches and Scrims. Every save keeps
the Strat as it was before (``strat_versions``). It is the Workspace's most
sensitive data: only Staff edit, a Strat reaches the Players only when shared
with the team, and every read, print and change is logged (``strat_events``).
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, TimestampMixin


class StratKind(StrEnum):
    DEFAULT = "default"
    EXECUTE = "execute"
    FAKE = "fake"
    RETAKE = "retake"
    SETUP = "setup"  # a CT setup
    PISTOL = "pistol"
    ANTI_ECO = "anti_eco"
    FORCE = "force"


class StratStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class StratVisibility(StrEnum):
    STAFF = "staff"
    TEAM = "team"  # the Workspace's Player logins read it


class Strat(TimestampMixin, Base):
    __tablename__ = "strats"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="CASCADE"))
    map_name: Mapped[str] = mapped_column(String(32), index=True)  # de_inferno
    side: Mapped[str] = mapped_column(String(3))
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(12), default=StratKind.DEFAULT)
    description: Mapped[str] = mapped_column(Text, default="")
    # [{slot, player (Steam id or ""), role, does}] in slot order
    roles: Mapped[list] = mapped_column(JSON, default=list)
    # [{slot, type, place, at, note, lineup}]: what lands where, seconds after freeze end
    grenades: Mapped[list] = mapped_column(JSON, default=list)
    timings: Mapped[str] = mapped_column(Text, default="")
    variations: Mapped[str] = mapped_column(Text, default="")
    calls: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(12), default=StratStatus.DRAFT)
    visibility: Mapped[str] = mapped_column(String(8), default=StratVisibility.STAFF)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class StratExample(TimestampMixin, Base):
    """A Round the Strat was played in: picked by Staff, or found (SB-4) and kept
    once Staff confirm it."""

    __tablename__ = "strat_examples"
    __table_args__ = (
        UniqueConstraint("strat_id", "match_map_id", "round", name="uq_strat_example"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    strat_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("strats.id", ondelete="CASCADE"), index=True
    )
    match_map_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("match_maps.id", ondelete="CASCADE")
    )
    round: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(8), default="manual")  # manual | auto
    confirmed: Mapped[bool] = mapped_column(default=True)
    note: Mapped[str] = mapped_column(String(300), default="")


class StratVersion(TimestampMixin, Base):
    """The Strat as it was before a save."""

    __tablename__ = "strat_versions"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    strat_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("strats.id", ondelete="CASCADE"), index=True
    )
    payload: Mapped[dict] = mapped_column(JSON)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class StratEvent(TimestampMixin, Base):
    """Who opened, printed, exported or changed a Strat, and when (SB-7)."""

    __tablename__ = "strat_events"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    strat_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("strats.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(12))  # view | print | export | edit | share
