"""Analysis jobs: the request, its story, and its result.

A job is one scouting question ("we play <opponent>, what should we know?") run
in the background by the Celery worker. Three models carry it:

* :class:`AnalysisJob`      the request, its live status, and the finished report;
* :class:`AnalysisEvent`    the story: every step, in order, kept after the run so
  a finished job can still be read back rather than only watched live;
* :class:`AnalysisArtifact` the files a run produced, mainly heatmaps.

Ported from cstat's ``hltv/models/jobs.py``. Differences: ``requested_by`` records
which User asked, and the deprecated ``n_matches`` field is gone.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Column, ForeignKey, Index, Integer, String, Table, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import BigId, DateTime6, PositiveSmallInt, TimestampMixin

if TYPE_CHECKING:
    from app.models.analysis import Player
    from app.models.source import Demo, Match, Team
    from app.models.user import User

analysis_job_matches = Table(
    "analysis_job_matches",
    Base.metadata,
    Column(
        "analysis_job_id",
        BigId,
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("match_id", BigId, ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True),
)


class JobKind(StrEnum):
    # The common case: my team versus an opponent.
    SCOUT = "scout"
    # One already-known map whose tick bundle went missing on disk and needs
    # re-parsing. Reuses this model so it inherits the job list and live progress;
    # `demo` carries the target instead of the two team fields.
    REPARSE_MAP = "reparse_map"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobStage(StrEnum):
    QUEUED = "queued"
    RESOLVING = "resolving"  # Resolving teams
    FETCHING = "fetching"  # Downloading demos
    UNPACKING = "unpacking"  # Unpacking archives
    PARSING = "parsing"  # Parsing demos
    ANALYSING = "analysing"
    RENDERING = "rendering"  # Rendering heatmaps
    DONE = "done"


FINISHED_STATUSES = (JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED)


class AnalysisJob(TimestampMixin, Base):
    """One background run: a scouting report, or a single map re-parse."""

    __tablename__ = "analysis_jobs"
    # cstat indexes (status, -created_at); MySQL reads an ascending index backwards
    # just as well, and a plain one keeps autogenerate comparisons clean.
    __table_args__ = (Index("ix_analysis_jobs_status_created_at", "status", "created_at"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    # A UUID keeps job URLs unguessable and stable.
    public_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True)

    kind: Mapped[str] = mapped_column(String(16), default=JobKind.SCOUT, index=True)
    requested_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    # Set only for a REPARSE_MAP job. Points at the *demo* rather than the MatchMap
    # it produces, because re-ingesting deletes and recreates the MatchMap row (that
    # is how a reparse is idempotent), so an FK to it would go NULL on success.
    demo_id: Mapped[int | None] = mapped_column(BigId, ForeignKey("demos.id", ondelete="SET NULL"))

    my_team_name: Mapped[str] = mapped_column(String(120), default="", doc="As typed.")
    opponent_name: Mapped[str] = mapped_column(String(120), default="", doc="As typed.")
    my_team_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("teams.id", ondelete="SET NULL")
    )
    opponent_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("teams.id", ondelete="SET NULL")
    )

    # Three separate windows, because they answer different questions: how each
    # team plays in general, and how they play against each other.
    n_my_matches: Mapped[int] = mapped_column(
        PositiveSmallInt, default=1, doc="My team's recent matches, excluding the opponent."
    )
    n_opponent_matches: Mapped[int] = mapped_column(
        PositiveSmallInt, default=1, doc="The opponent's recent matches, excluding my team."
    )
    n_h2h_matches: Mapped[int] = mapped_column(
        PositiveSmallInt, default=1, doc="Recent matches between the two teams."
    )
    download: Mapped[bool] = mapped_column(default=True, doc="False: only what is on disk.")

    status: Mapped[str] = mapped_column(String(12), default=JobStatus.QUEUED, index=True)
    stage: Mapped[str] = mapped_column(String(12), default=JobStage.QUEUED)
    progress: Mapped[int] = mapped_column(PositiveSmallInt, default=0, doc="0-100.")

    celery_task_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime6)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime6)
    error: Mapped[str] = mapped_column(Text, default="")
    # Cancellation is cooperative: the threads pool used in local dev cannot
    # force-kill a task, so the running task polls this flag between items and
    # stops itself. A job still QUEUED is revoked from the broker instead.
    cancel_requested: Mapped[bool] = mapped_column(default=False)

    # What the run is doing right now (sub-step and its own progress). A snapshot,
    # overwritten constantly, stored so a reload mid-download still shows it.
    activity: Mapped[dict] = mapped_column(JSON, default=dict)
    # The record the snapshot is not: one entry per stage entered, with timings
    # and tallies. It survives the run, so a finished job shows where time went.
    stage_log: Mapped[list] = mapped_column(JSON, default=list)
    # The finished scouting report. Denormalised on purpose: it must keep reading
    # correctly even if the models move on.
    result: Mapped[dict] = mapped_column(JSON, default=dict)

    requested_by: Mapped[User | None] = relationship()
    demo: Mapped[Demo | None] = relationship(back_populates="reparse_jobs")
    my_team: Mapped[Team | None] = relationship(foreign_keys=[my_team_id])
    opponent: Mapped[Team | None] = relationship(foreign_keys=[opponent_id])
    matches: Mapped[list[Match]] = relationship(
        secondary=analysis_job_matches, back_populates="analysis_jobs"
    )
    events: Mapped[list[AnalysisEvent]] = relationship(back_populates="job", passive_deletes=True)
    artifacts: Mapped[list[AnalysisArtifact]] = relationship(
        back_populates="job", passive_deletes=True
    )

    def __str__(self) -> str:
        return f"{self.label} [{self.status}]"

    @property
    def label(self) -> str:
        """What the job list and the page title call this run."""
        if self.kind == JobKind.REPARSE_MAP:
            if self.demo is not None:
                map_name = (self.demo.map or "").replace("de_", "").title() or "map"
                return f"Re-parse {map_name} — {self.demo.match}"
            return "Re-parse map"
        return f"{self.my_team_name} vs {self.opponent_name}"

    @property
    def windows(self) -> str:
        """The three request sizes, as they read on the page: a / b / c."""
        return f"{self.n_my_matches}/{self.n_opponent_matches}/{self.n_h2h_matches}"

    @property
    def is_finished(self) -> bool:
        return self.status in FINISHED_STATUSES

    @property
    def duration_seconds(self) -> float | None:
        if not self.started_at:
            return None
        end = self.finished_at or self.updated_at
        return (end - self.started_at).total_seconds()


class EventLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class AnalysisEvent(TimestampMixin, Base):
    """One line of a job's story, kept so a finished run can be read back."""

    __tablename__ = "analysis_events"
    __table_args__ = (Index("ix_analysis_events_job_id_id", "job_id", "id"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    job_id: Mapped[int] = mapped_column(BigId, ForeignKey("analysis_jobs.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(String(8), default=EventLevel.INFO)
    stage: Mapped[str] = mapped_column(String(12), default="")
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    job: Mapped[AnalysisJob] = relationship(back_populates="events")

    def __str__(self) -> str:
        return f"[{self.level}] {self.message[:60]}"


class ArtifactKind(StrEnum):
    HEATMAP_DEATHS = "deaths"  # Where they die
    HEATMAP_KILLS = "kills"  # Where they kill
    HEATMAP_PLAYER = "player"  # Player positions
    ROUTE_MAP = "route"  # Routes taken
    ROUTE_GIF = "route_gif"  # Routes, animated
    POST_PLANT = "post_plant"  # Post-plant positions


class AnalysisArtifact(TimestampMixin, Base):
    """A picture the analysis drew: a heatmap, normally."""

    __tablename__ = "analysis_artifacts"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    # Null when nothing asked for it as part of a run: a heatmap is a picture of a
    # team on a map, so the game plan draws the same ones without a job behind it.
    job_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("analysis_jobs.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(16), doc="An ArtifactKind value.")
    title: Mapped[str] = mapped_column(String(160))
    subtitle: Mapped[str] = mapped_column(String(200), default="")
    map_name: Mapped[str] = mapped_column(String(32), default="")
    player_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("players.id", ondelete="SET NULL"), doc="Per-player artifacts."
    )
    team_id: Mapped[int | None] = mapped_column(BigId, ForeignKey("teams.id", ondelete="SET NULL"))
    side: Mapped[str] = mapped_column(String(3), default="", doc="Blank: both sides.")
    path: Mapped[str] = mapped_column(String(500), doc="Relative to the media root.")
    # Whether awpy's radar renderer was available; the fallback draws the same data
    # without the map underneath.
    renderer: Mapped[str] = mapped_column(String(16), default="")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    job: Mapped[AnalysisJob | None] = relationship(back_populates="artifacts")
    player: Mapped[Player | None] = relationship()
    team: Mapped[Team | None] = relationship()

    def __str__(self) -> str:
        return self.title
