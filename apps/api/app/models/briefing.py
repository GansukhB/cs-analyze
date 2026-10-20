"""Briefings (CONTEXT.md: Briefing; docs/plans/01 WS-5): what Staff hand the
Players before a Match. A frozen selection of one Game Plan's lines with Staff's
notes, kept as gzip JSON; it never changes when more Match Maps are parsed. The
Forecast is in it only when Staff include it (grilling Q15)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, DateTime6, MediumBlob, TimestampMixin


class Briefing(TimestampMixin, Base):
    __tablename__ = "briefings"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True)
    workspace_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    my_team_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    opponent_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    my_lineup: Mapped[list] = mapped_column(JSON, default=list)  # Steam ids, as strings
    their_lineup: Mapped[list] = mapped_column(JSON, default=list)
    match_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("matches.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(160))
    payload: Mapped[bytes] = mapped_column(MediumBlob)
    include_forecast: Mapped[bool] = mapped_column(default=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Players see it from then on; until then it is Staff's draft.
    shared_at: Mapped[datetime | None] = mapped_column(DateTime6)
