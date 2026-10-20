"""The Workspace (CONTEXT.md): one club's private space, and the Teams it calls my team.

Everything a club keeps to itself belongs to its Workspace (docs/adr/0011);
what HLTV shows stays shared. Users sign in to one Workspace, as Staff or tied
to one of its Players.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import BigId, TimestampMixin

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
