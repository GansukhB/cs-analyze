"""The Workspace (CONTEXT.md): one club's private space, and the Teams it calls my team.

Everything a club keeps to itself belongs to its Workspace (docs/adr/0011);
what HLTV shows stays shared. Users sign in to one Workspace, as Staff or tied
to one of its Players.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import BigId, DateTime6, TimestampMixin

if TYPE_CHECKING:
    from app.models.source import Team


class UserRole(StrEnum):
    """Staff see and change everything in their Workspace; a Player sees their own."""

    STAFF = "staff"
    PLAYER = "player"


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)

    teams: Mapped[list[WorkspaceTeam]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", order_by="WorkspaceTeam.id"
    )


class WorkspaceTeam(TimestampMixin, Base):
    """One of a Workspace's my teams, such as its main roster or its academy."""

    __tablename__ = "workspace_teams"
    __table_args__ = (UniqueConstraint("workspace_id", "team_id", name="uq_ws_team"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    team_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    label: Mapped[str] = mapped_column(String(40), default="", doc="'main', 'academy', ...")

    workspace: Mapped[Workspace] = relationship(back_populates="teams")
    team: Mapped[Team] = relationship()


class Invite(TimestampMixin, Base):
    """A one-time link that makes a User in a Workspace (docs/plans WS-3), or, with
    ``user_id``, sets a forgotten password. Only the token's SHA-256 is kept."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(12), default=UserRole.STAFF)
    player_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("players.id", ondelete="SET NULL")
    )
    # A password reset for this User instead of a new one.
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime6)
    used_at: Mapped[datetime | None] = mapped_column(DateTime6)
    used_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class DeclaredRole(TimestampMixin, Base):
    """The role Staff say one of their Players plays on a Side (docs/plans PL-4).

    It is the truth for their own Players: their role, and which cohort they are
    judged against. ``map`` is "" for every Map. Opponents keep inferred roles.
    """

    __tablename__ = "declared_roles"
    __table_args__ = (
        UniqueConstraint("workspace_id", "player_id", "side", "map", name="uq_declared_role"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    player_id: Mapped[int] = mapped_column(BigId, ForeignKey("players.id", ondelete="CASCADE"))
    side: Mapped[str] = mapped_column(String(2))
    map: Mapped[str] = mapped_column(String(32), default="")
    role: Mapped[str] = mapped_column(String(16))
