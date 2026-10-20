"""What the HLTV scrapers read: teams, tournaments, matches and demo files.

These models track *sources*: what HLTV said and which files are on disk.
Everything derived from parsing a demo lives in ``analysis.py`` instead.

HLTV's own numeric ids live in ``hltv_id`` rather than serving as primary keys,
because they are not always available: a row on ``/results`` names the opposing
team but does not link to it, so an opponent is first stored under its name
alone and adopts its id later. Hence ``Team.hltv_id`` is nullable, and only
*unidentified* teams are forced to have distinct names, since HLTV genuinely
hosts different teams that share a display name.

Ported from cstat's ``hltv/models/source.py``; cstat's ``Event`` is ``Tournament`` here.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import BigId, DateTime6, PositiveInt, PositiveSmallInt, TimestampMixin

if TYPE_CHECKING:
    from app.models.analysis import MatchMap, PlayerMatch, TeamAlias
    from app.models.jobs import AnalysisJob


class Team(TimestampMixin, Base):
    """A team as HLTV lists it."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    hltv_id: Mapped[int | None] = mapped_column(
        PositiveInt, unique=True, doc="HLTV team id. Null until seen on /search or /team."
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    slug: Mapped[str] = mapped_column(String(120), default="", index=True)
    # cstat uses a partial unique index (name WHERE hltv_id IS NULL); MySQL has none.
    # This column holds the name only while the team is unidentified, and a unique
    # index ignores NULLs, so the rule is enforced the same way.
    unidentified_name: Mapped[str | None] = mapped_column(
        String(120),
        Computed("CASE WHEN hltv_id IS NULL THEN name END", persisted=True),
        unique=True,
    )

    matches_as_team1: Mapped[list[Match]] = relationship(
        back_populates="team1", foreign_keys="Match.team1_id"
    )
    matches_as_team2: Mapped[list[Match]] = relationship(
        back_populates="team2", foreign_keys="Match.team2_id"
    )
    clan_aliases: Mapped[list[TeamAlias]] = relationship(back_populates="team")

    def __str__(self) -> str:
        return f"{self.name} (id={self.hltv_id})" if self.hltv_id else self.name

    @property
    def identified(self) -> bool:
        return self.hltv_id is not None

    @property
    def url(self) -> str:
        """HLTV-relative team page, or "" while the HLTV id is unknown."""
        if not self.hltv_id:
            return ""
        return f"/team/{self.hltv_id}/{self.slug}" if self.slug else f"/team/{self.hltv_id}"


class Tournament(TimestampMixin, Base):
    """A competition, as named on the results row.

    Only the display name is scraped, so the name is the identity. HLTV names
    normally carry the year ("BLAST Open Porto 2026"), which keeps editions apart.
    """

    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    hltv_id: Mapped[int | None] = mapped_column(PositiveInt, unique=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    slug: Mapped[str] = mapped_column(String(200), default="", index=True)

    matches: Mapped[list[Match]] = relationship(back_populates="tournament")

    def __str__(self) -> str:
        return self.name


class MatchKind(StrEnum):
    """A Match proper, or a Scrim (CONTEXT.md): reviewed like one, counted nowhere."""

    OFFICIAL = "official"
    SCRIM = "scrim"


class MatchSource(StrEnum):
    HLTV = "hltv"
    UPLOAD = "upload"


class Match(TimestampMixin, Base):
    """A played match from ``/results``.

    ``team1``/``team2`` are nullable because the scraper reports the side names
    as best-effort strings; a row that renders without one is still worth
    keeping. ``score`` holds HLTV's raw text and the two integer columns hold it
    parsed, so an unexpected format degrades to "raw only" rather than failing.
    """

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    # None for a Match a Workspace uploaded (DATA-1); MySQL lets many NULLs share a UNIQUE.
    hltv_id: Mapped[int | None] = mapped_column(PositiveInt, unique=True)
    slug: Mapped[str] = mapped_column(String(200), default="", index=True)
    # Private rows (docs/adr/0011): an uploaded Match is seen only in its Workspace,
    # and a Scrim stays out of every Own form, habit and Pool (docs/adr/0010).
    workspace_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16), default=MatchKind.OFFICIAL)
    source: Mapped[str] = mapped_column(String(16), default=MatchSource.HLTV)
    # The other side's name when it has no Team row (a scrim partner typed in).
    opponent_label: Mapped[str] = mapped_column(String(120), default="")

    team1_id: Mapped[int | None] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    team2_id: Mapped[int | None] = mapped_column(BigId, ForeignKey("teams.id", ondelete="RESTRICT"))
    tournament_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("tournaments.id", ondelete="SET NULL")
    )

    score: Mapped[str] = mapped_column(String(40), default="", doc='Raw, e.g. "2 - 0".')
    team1_score: Mapped[int | None] = mapped_column(PositiveSmallInt)
    team2_score: Mapped[int | None] = mapped_column(PositiveSmallInt)
    played_at: Mapped[datetime | None] = mapped_column(DateTime6, index=True)

    # Outcome of the demo-link lookup on the match page. An empty url with a
    # set timestamp means HLTV published no demo for this match.
    demo_url: Mapped[str] = mapped_column(String(200), default="")
    demo_checked_at: Mapped[datetime | None] = mapped_column(DateTime6)

    team1: Mapped[Team | None] = relationship(
        back_populates="matches_as_team1", foreign_keys=[team1_id]
    )
    team2: Mapped[Team | None] = relationship(
        back_populates="matches_as_team2", foreign_keys=[team2_id]
    )
    tournament: Mapped[Tournament | None] = relationship(back_populates="matches")
    demos: Mapped[list[Demo]] = relationship(back_populates="match", passive_deletes=True)
    map_results: Mapped[list[MatchMap]] = relationship(back_populates="match", passive_deletes=True)
    player_stats: Mapped[list[PlayerMatch]] = relationship(
        back_populates="match", passive_deletes=True
    )
    analysis_jobs: Mapped[list[AnalysisJob]] = relationship(
        secondary="analysis_job_matches", back_populates="matches"
    )

    def __str__(self) -> str:
        return self.label

    @property
    def url(self) -> str:
        if self.hltv_id is None:
            return ""
        return f"/matches/{self.hltv_id}/{self.slug}" if self.slug else f"/matches/{self.hltv_id}"

    @property
    def is_scrim(self) -> bool:
        return self.kind == MatchKind.SCRIM

    @property
    def label(self) -> str:
        when = self.played_at.date().isoformat() if self.played_at else "unknown date"
        return (
            f"{self.team1 or '?'} {self.score} {self.team2 or '?'}"
            f" — {self.tournament or '?'} ({when})"
        )

    @property
    def demo_available(self) -> bool:
        """HLTV published a demo link for this match."""
        return bool(self.demo_url)

    @property
    def archive_demo(self) -> Demo | None:
        """The row tracking this match's .rar, or None if never attempted."""
        return next((d for d in self.demos if d.is_archive), None)

    @property
    def map_demos(self) -> list[Demo]:
        """The rows tracking the individual .dem files, once unpacked."""
        return [d for d in self.demos if not d.is_archive]


class Demo(TimestampMixin, Base):
    """One tracked demo file, at either level.

    HLTV publishes a single archive per match holding one ``.dem`` per map
    played, so a match ends up with one **archive** row (``map`` blank) plus one
    **map** row per unpacked ``.dem``. A Match Map recorded as Demo parts has one
    row per part (``part`` 1, 2, ...), parsed together as one Match Map whose
    ``demo`` is part 1 (docs/adr/0009). ``(match, map, part)`` is unique: that is
    what stops a re-run from creating a second row for a file it already has.

    ==========  =====================  ==============================
    row         ``is_downloaded``      ``is_processed``
    ==========  =====================  ==============================
    archive     the ``.rar`` is here   it has been unpacked into map rows
    map         the ``.dem`` is here   its stats have been parsed
    ==========  =====================  ==============================

    Processing may only follow a download, which the check constraint enforces
    in the database rather than trusting every caller to remember.
    """

    __tablename__ = "demos"
    __table_args__ = (
        UniqueConstraint("match_id", "map", "part", name="uq_demos_match_map_part"),
        CheckConstraint("NOT is_processed OR is_downloaded", name="processed_requires_download"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_id: Mapped[int] = mapped_column(BigId, ForeignKey("matches.id", ondelete="CASCADE"))
    map: Mapped[str] = mapped_column(
        String(40), default="", doc='HLTV map name, e.g. "anubis". Blank: the match archive.'
    )
    map_number: Mapped[int | None] = mapped_column(
        PositiveSmallInt, doc="Map order within the match: the m1/m2 in the filename."
    )
    part: Mapped[int] = mapped_column(
        PositiveSmallInt,
        default=0,
        server_default="0",
        doc="Which Demo part: the p1/p2 in the filename; 0 for a map recorded whole.",
    )

    url: Mapped[str] = mapped_column(String(200), default="", doc="/download/demo/<id>")
    filename: Mapped[str] = mapped_column(String(255), default="")
    path: Mapped[str] = mapped_column(String(500), default="")
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    is_downloaded: Mapped[bool] = mapped_column(default=False)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime6)
    is_processed: Mapped[bool] = mapped_column(default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime6)
    error: Mapped[str] = mapped_column(Text, default="")

    match: Mapped[Match] = relationship(back_populates="demos")
    analysis: Mapped[MatchMap | None] = relationship(back_populates="demo")
    reparse_jobs: Mapped[list[AnalysisJob]] = relationship(back_populates="demo")

    def __str__(self) -> str:
        return f"{self.match_id}/{self.map or 'archive'} [{self.status}]"

    @property
    def is_archive(self) -> bool:
        """True for the per-match ``.rar``, False for an unpacked map demo."""
        return not self.map

    @property
    def status(self) -> str:
        """Lifecycle in one word, derived from the flags; never stored."""
        if self.is_processed:
            return "processed"
        if self.is_downloaded:
            return "downloaded"
        return "failed" if self.error else "pending"

    @property
    def exists_on_disk(self) -> bool:
        return bool(self.path) and Path(self.path).exists()
