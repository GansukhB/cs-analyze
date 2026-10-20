"""Results known without their Demos: what Ratings are fitted on (docs/plans DATA-2, FC-1).

``SeriesResult`` is one series between two Teams, its winner and the five each
fielded, as Valve Regional Standings counted it (``source = "vrs"``). Names
are kept as published: a Team or opponent HLTV never showed us has no Team row,
and Ratings follow the name (and its roster) all the same. ``VrsStanding`` is one
roster's line in one monthly snapshot of the standings.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.base import BigId, Float, TimestampMixin


class SeriesResult(TimestampMixin, Base):
    __tablename__ = "series_results"
    __table_args__ = (UniqueConstraint("source", "key", name="uq_series_source_key"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    source: Mapped[str] = mapped_column(String(16), default="vrs")
    # Stable across re-imports: date, both names, winner and the occurrence that day.
    key: Mapped[str] = mapped_column(String(190))
    played_on: Mapped[date] = mapped_column(Date, index=True)
    team_a: Mapped[str] = mapped_column(String(120))
    team_b: Mapped[str] = mapped_column(String(120))
    team_a_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    team_b_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    a_won: Mapped[bool] = mapped_column()
    # Known only from a winner's side of the table: Valve counts LAN wins.
    lan: Mapped[bool | None] = mapped_column()
    roster_a: Mapped[list] = mapped_column(JSON, default=list)
    roster_b: Mapped[list] = mapped_column(JSON, default=list)


class VrsStanding(TimestampMixin, Base):
    __tablename__ = "vrs_standings"
    __table_args__ = (UniqueConstraint("snapshot", "global_rank", name="uq_vrs_snapshot_rank"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    snapshot: Mapped[date] = mapped_column(Date, index=True)
    global_rank: Mapped[int] = mapped_column(Integer)
    region: Mapped[str] = mapped_column(String(24), default="")
    regional_rank: Mapped[int | None] = mapped_column(Integer)
    points: Mapped[float] = mapped_column(Float)
    team_name: Mapped[str] = mapped_column(String(120), index=True)
    team_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    roster: Mapped[list] = mapped_column(JSON, default=list)
