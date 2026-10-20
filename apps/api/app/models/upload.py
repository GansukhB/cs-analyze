"""A Workspace's own Demos on their way in (CONTEXT.md: Scrim; docs/plans/02 DATA-1).

An ``Upload`` is what Staff said about the file (a Scrim or an official Match
HLTV doesn't carry, the date, my team and the other side) and where it stands.
Its bytes arrive in ``UploadPart`` rows of at most :data:`PART_BYTES`, in MySQL
rather than on disk, because the request that receives a part is not the job
that parses it (docs/adr/0002); the parts are deleted once the job has them.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, MediumBlob, TimestampMixin

# One MEDIUMBLOB holds 16 MiB; a part stays under it, and under nginx's limit.
PART_BYTES = 15 * 1024 * 1024
MAX_PARTS = 80  # 1.2 GB: more than any Demo archive


class UploadStatus(StrEnum):
    RECEIVING = "receiving"
    QUEUED = "queued"
    PARSING = "parsing"
    NEEDS_SIDES = "needs_sides"  # a Map waits for Staff to say which five are ours
    DONE = "done"
    FAILED = "failed"


class Upload(TimestampMixin, Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16))  # MatchKind
    played_on: Mapped[date] = mapped_column(Date)
    my_team_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    opponent_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("teams.id", ondelete="RESTRICT")
    )
    opponent_name: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(String(500), default="")
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigId)
    parts_total: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=UploadStatus.RECEIVING)
    error: Mapped[str] = mapped_column(Text, default="")
    job_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("analysis_jobs.id", ondelete="SET NULL")
    )
    match_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("matches.id", ondelete="SET NULL")
    )
    # Per Map: {"map_number", "map", "groups": [[{steamid, name}], [...]], "mine": 0 | 1 | None,
    # "match_map_id"}. "mine" None is the "who is who" step a Staff member answers.
    maps: Mapped[list] = mapped_column(JSON, default=list)


class UploadPart(Base):
    __tablename__ = "upload_parts"
    __table_args__ = (UniqueConstraint("upload_id", "n", name="uq_upload_part"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    upload_id: Mapped[int] = mapped_column(BigId, ForeignKey("uploads.id", ondelete="CASCADE"))
    n: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(MediumBlob)
