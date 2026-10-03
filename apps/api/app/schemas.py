import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import get_settings


def _utc(value: dt.datetime | None) -> dt.datetime | None:
    """Stored datetimes are naive UTC; say so, so browsers don't read them as local."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


# -- scout jobs ------------------------------------------------------------------
class JobCreate(BaseModel):
    """The scout form: two team names, and how much to pull."""

    my_team: str = Field(min_length=1, max_length=120)
    opponent: str = Field(min_length=1, max_length=120)
    n_my_matches: int = Field(ge=0, description="Latest matches against anyone but the opponent.")
    n_opponent_matches: int = Field(ge=0, description="Latest matches against anyone but my team.")
    n_h2h_matches: int = Field(ge=0, description="Latest matches the two played each other.")
    download: bool = Field(True, description="False: analyse only what is already stored.")

    @field_validator("my_team", "opponent")
    @classmethod
    def strip(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("n_my_matches", "n_opponent_matches", "n_h2h_matches")
    @classmethod
    def within_max(cls, value: int) -> int:
        limit = get_settings().analysis_max_matches
        if value > limit:
            raise ValueError(f"at most {limit}")
        return value

    @model_validator(mode="after")
    def sensible(self) -> "JobCreate":
        if self.my_team.casefold() == self.opponent.casefold():
            raise ValueError("Pick two different teams.")
        if not (self.n_my_matches or self.n_opponent_matches or self.n_h2h_matches):
            raise ValueError("Ask for at least one match — set a, b or c above zero.")
        return self


class JobRow(BaseModel):
    """One run, as the lists show it."""

    public_id: uuid.UUID
    label: str
    kind: str
    status: str
    stage: str
    stage_label: str
    progress: int
    windows: str
    my_team_name: str
    opponent_name: str
    download: bool
    error: str
    requested_by: str | None
    created_at: dt.datetime
    duration: float | None

    @field_validator("created_at")
    @classmethod
    def created_utc(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)

    @classmethod
    def of(cls, job) -> "JobRow":
        from app.services.jobs import STAGE_LABELS

        return cls(
            public_id=job.public_id,
            label=job.label,
            kind=job.kind,
            status=job.status,
            stage=job.stage,
            stage_label=STAGE_LABELS.get(job.stage, job.stage),
            progress=job.progress,
            windows=job.windows,
            my_team_name=job.my_team_name,
            opponent_name=job.opponent_name,
            download=job.download,
            error=job.error,
            requested_by=job.requested_by.username if job.requested_by else None,
            created_at=job.created_at,
            duration=job.duration_seconds,
        )


class StageRow(BaseModel):
    stage: str
    label: str
    state: str
    seconds: float | None
    summary: str
    counts: dict[str, int]


class Activity(BaseModel):
    """What the current step is doing right now; empty when nothing is."""

    model_config = ConfigDict(extra="allow")

    key: str | None = None
    text: str | None = None
    stage: str | None = None
    pct: int | None = None
    done: int | None = None
    total: int | None = None
    at: str | None = None


class JobCycle(BaseModel):
    """Which match a match-by-match run is on: downloading, unpacking and
    parsing repeat for each one."""

    n: int
    of: int


class JobStatusPayload(BaseModel):
    """Mirrors what the WebSocket pushes as `status` (and inside `snapshot`)."""

    public_id: uuid.UUID
    status: str
    stage: str
    stage_label: str
    progress: int
    error: str
    duration: float | None
    finished: bool
    activity: Activity
    stages: list[StageRow]
    cycle: "JobCycle | None" = None


class JobEvent(BaseModel):
    id: int
    level: str
    stage: str
    message: str
    payload: dict[str, Any]
    at: str


class MatchMapSummary(BaseModel):
    map: str
    map_number: int
    scoreline: str
    rounds: int
    parsed: bool


class MatchSummary(BaseModel):
    match_id: int | None = None  # absent on results stored before it was added
    hltv_id: int
    url: str
    team1: str
    team2: str
    score: str
    tournament: str
    played_at: str | None
    demo: str
    maps: list[MatchMapSummary]


class JobResult(BaseModel):
    windows: dict[str, list[MatchSummary]] | None
    parsed_matches: list[MatchSummary]
    scanned: int | None
    h2h_found: int | None
    totals: dict[str, dict[str, int]]


class JobWords(BaseModel):
    """Mongolian stage and tally names, from the server's single dictionary."""

    stages: dict[str, str]
    counts: dict[str, str]


class JobDetail(BaseModel):
    job: JobRow
    status: JobStatusPayload
    events: list[JobEvent]
    result: JobResult | None
    words: JobWords


class JobList(BaseModel):
    jobs: list[JobRow]
    counts: dict[str, int]


class ScoutDefaults(BaseModel):
    matches: int
    max_matches: int


class HomeInfo(BaseModel):
    recent_jobs: list[JobRow]
    known_teams: list[str]
    parsed_maps: int
    defaults: ScoutDefaults


class ActiveTask(BaseModel):
    worker: str
    task: str | None
    id: str | None


class BrokerState(BaseModel):
    redis_url: str
    connected: bool
    queued: int | None
    workers: list[str]
    active: list[ActiveTask]
    error: str


# -- teams -------------------------------------------------------------------------
class TeamRef(BaseModel):
    id: int
    name: str


class TeamRow(BaseModel):
    id: int
    name: str
    hltv_id: int | None
    hltv_url: str
    identified: bool
    matches: int
    maps: int
    last: dt.datetime | None

    @field_validator("last")
    @classmethod
    def last_utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value)


class TeamList(BaseModel):
    teams: list[TeamRow]
    parsed_teams: int
    total_matches: int


class DemoState(BaseModel):
    word: str
    cls: str
    why: str


class TeamResultMap(BaseModel):
    name: str
    number: int
    score: str
    attributed: bool
    won: bool | None
    parsed: bool


class TeamResult(BaseModel):
    match_id: int
    played_at: dt.datetime | None
    opponent: TeamRef | None
    ours: int | None
    theirs: int | None
    outcome: str
    score: str
    tournament: str
    maps: list[TeamResultMap]
    n_parsed: int
    demo: DemoState

    @field_validator("played_at")
    @classmethod
    def played_utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value)


class MapRecordRow(BaseModel):
    map: str
    played: int
    won: int
    lost: int
    pct: int | None


class TeamPlayer(BaseModel):
    name: str
    maps: int
    rounds: int
    last: dt.datetime | None

    @field_validator("last")
    @classmethod
    def last_utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value)


class MatchRecord(BaseModel):
    won: int
    lost: int
    drawn: int


class TeamDetail(BaseModel):
    team: TeamRow
    record: MatchRecord
    results: list[TeamResult]
    n_parsed_maps: int
    map_record: list[MapRecordRow]
    players: list[TeamPlayer]
    plannable: list[TeamRef] = []


# -- matches -----------------------------------------------------------------------
class MatchMapTab(BaseModel):
    map_number: int
    label: str
    scoreline: str
    parsed: bool
    playable: bool


class MatchInfo(BaseModel):
    id: int
    hltv_id: int
    hltv_url: str
    team1: TeamRef | None
    team2: TeamRef | None
    score: str
    tournament: str
    played_at: dt.datetime | None
    maps: list[MatchMapTab]
    default_map: int | None

    @field_validator("played_at")
    @classmethod
    def played_utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value)


class RoundStripRow(BaseModel):
    number: int
    winner_side: str
    winner: str
    reason: str
    planted: bool
    site: str
    score: str
    mine: bool
    half_break: bool


class ScoreboardPlayer(BaseModel):
    name: str
    kills: int
    deaths: int
    kd_diff: int
    adr: float | None
    kast_pct: float | None
    hs_pct: float | None


class ScoreboardSide(BaseModel):
    team: TeamRef
    score: int | None
    won: bool
    players: list[ScoreboardPlayer]


class CalloutLabel(BaseModel):
    name: str
    x: float
    y: float


class Plate(BaseModel):
    url: str | None
    width: int
    height: int
    extent: list[float]


class SceneLevel(BaseModel):
    key: str
    url: str | None
    labels: list[CalloutLabel]


class Scene(BaseModel):
    plate: Plate
    labels: list[CalloutLabel]
    levels: list[SceneLevel]


class MatchMapDetail(BaseModel):
    map_number: int
    label: str
    parsed: bool
    playable: bool
    scene: Scene | None
    rounds: list[RoundStripRow]
    scoreboard: list[ScoreboardSide]


# -- game plan ---------------------------------------------------------------------
class GameplanTeam(BaseModel):
    id: int
    name: str
    maps: int


class GameplanPick(BaseModel):
    teams: list[GameplanTeam]
    parsed_maps: int


class GameplanTab(BaseModel):
    key: str
    label: str
    grp: int
    n: int = 0


class GameplanLede(BaseModel):
    my_maps: int
    opponent_maps: int
    h2h_maps: int


class GameplanHeader(BaseModel):
    my_team: TeamRef
    opponent: TeamRef
    lede: GameplanLede
    tabs: list[GameplanTab]
    default_tab: str
    stamp: str


class GameplanPanel(BaseModel):
    """One panel's data. Its shape differs per tab and is typed on the page."""

    tab: str
    stamp: str
    cached: bool
    ms: float
    data: dict[str, Any]
