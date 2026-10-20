"""Forecasts kept and graded (CONTEXT.md: Forecast; docs/plans/03 FC-4).

A Forecast is written once, with the model version and every number it was made
from, and never changed: a newer Rating makes a new Forecast. When the series
is played, its result, log loss and Brier are added (``graded_at``), which is
how the model shows how far to trust it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, DateTime6, Float, TimestampMixin


class Forecast(TimestampMixin, Base):
    __tablename__ = "forecasts"
    __table_args__ = (Index("ix_forecasts_ws_created", "workspace_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True)
    # None for the system's own Forecasts on Pool fixtures (FC-4's "auto" kind).
    workspace_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(16), default="request")
    # users.id is a plain INTEGER, unlike the ported tables' BIGINT.
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    my_team_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    opponent_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    my_lineup: Mapped[list] = mapped_column(JSON, default=list)  # Steam ids, as strings
    their_lineup: Mapped[list] = mapped_column(JSON, default=list)
    format: Mapped[str] = mapped_column(String(8), default="bo3")
    model_version: Mapped[str] = mapped_column(String(32), default="")
    # What forecast.build returned: Ratings, limits, each Map, each format.
    outputs: Mapped[dict] = mapped_column(JSON, default=dict)
    p_series: Mapped[float] = mapped_column(Float)  # ours, in ``format``
    match_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("matches.id", ondelete="SET NULL")
    )
    graded_at: Mapped[datetime | None] = mapped_column(DateTime6)
    # {"won", "score", "source", "played_on", "maps": [{"map", "won", "p"}]} or {"expired": true}
    result: Mapped[dict | None] = mapped_column(JSON)
    log_loss: Mapped[float | None] = mapped_column(Float)
    brier: Mapped[float | None] = mapped_column(Float)
