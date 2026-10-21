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

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, Float, MediumBlob, TimestampMixin


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
    # VIZ-8: what Staff drew on the Replay, in world units:
    # [{kind: arrow|circle|text, points: [[x, y], ...], text}]
    drawing: Mapped[list | None] = mapped_column(JSON)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


# VIZ-13: a clip under one MEDIUMBLOB (16 MiB); ten seconds of WebM is a few MB.
CLIP_BYTES = 15 * 1024 * 1024


class NoteClip(TimestampMixin, Base):
    """Ten seconds of the Replay recorded in the browser at a note's moment (VIZ-13).

    Kept apart from the note so listing notes never reads the video."""

    __tablename__ = "note_clips"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    note_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("review_notes.id", ondelete="CASCADE"), unique=True
    )
    content_type: Mapped[str] = mapped_column(String(64), default="video/webm")
    data: Mapped[bytes] = mapped_column(MediumBlob)


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


class PlaybookNote(TimestampMixin, Base):
    """Staff's note on one habit line of a Team's Playbook on a Map (GP-13), kept
    across parses by the habit's key (``playbook_notes.habit_key``)."""

    __tablename__ = "playbook_notes"
    __table_args__ = (
        UniqueConstraint("workspace_id", "team_id", "map_name", "key", name="uq_playbook_note"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    team_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="CASCADE"))
    map_name: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
