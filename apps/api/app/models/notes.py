"""Staff's notes on a Review, Findings they dispute, and Playlists
(docs/plans/07 RV-7).

A note pins Staff's words to a Match Map, optionally a Round and moment and the
Players it is about; a Player sees the notes that name him. A dispute says a
Finding is wrong and why: how often each code is disputed is the one real
feedback a detector's thresholds get. A Playlist puts Rounds from any Match Map
in an order, each with a line, for the Players to watch once it is shared.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, Float, TimestampMixin


class NoteKind(StrEnum):
    NOTE = "note"
    DISPUTE = "dispute"


class ReviewNote(TimestampMixin, Base):
    __tablename__ = "review_notes"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    match_map_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("match_maps.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(12), default=NoteKind.NOTE)
    round: Mapped[int | None] = mapped_column(Integer)
    t: Mapped[float | None] = mapped_column(Float)
    code: Mapped[str] = mapped_column(String(32), default="")  # the Finding disputed or noted
    sids: Mapped[list] = mapped_column(JSON, default=list)  # Steam ids, as strings
    text: Mapped[str] = mapped_column(Text, default="")
    tag: Mapped[str] = mapped_column(String(32), default="")
    reason: Mapped[str] = mapped_column(String(32), default="")  # a dispute's DISPUTE_REASONS key
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Playlist(TimestampMixin, Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(160))
    note: Mapped[str] = mapped_column(Text, default="")
    # [{match_id, map_number, round, t, sid, text}], in watching order
    items: Mapped[list] = mapped_column(JSON, default=list)
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
