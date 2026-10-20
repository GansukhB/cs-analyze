from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import BigId, DateTime6
from app.models.workspace import UserRole

if TYPE_CHECKING:
    from app.models.analysis import Player
    from app.models.workspace import Workspace

# Usernames are case-sensitive ("Bat" != "bat"), so MySQL needs a binary collation.
Username = String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(Username, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="RESTRICT"), index=True
    )
    # A UserRole value; a plain VARCHAR with no check, like the other choices.
    role: Mapped[str] = mapped_column(String(12), default=UserRole.STAFF)
    # The Player this User is (a Player login sees that Player's own numbers).
    player_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("players.id", ondelete="SET NULL")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime6)

    workspace: Mapped[Workspace] = relationship(lazy="joined")
    player: Mapped[Player | None] = relationship()

    @property
    def is_staff(self) -> bool:
        return self.role == UserRole.STAFF
