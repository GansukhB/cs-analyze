import datetime as dt
import uuid
from typing import Any, Literal

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


class MyTeamRef(BaseModel):
    """One of the Workspace's my teams (CONTEXT.md)."""

    id: int
    name: str
    label: str


class WorkspaceRead(BaseModel):
    id: int
    name: str
    my_teams: list[MyTeamRef]


class UserRead(BaseModel):
    """Who is signed in, and for which club: the pages read "we" from ``my_teams``."""

    id: int
    username: str
    role: str
    player_id: int | None
    workspace: WorkspaceRead

    @classmethod
    def of(cls, user) -> "UserRead":
        ws = user.workspace
        return cls(
            id=user.id,
            username=user.username,
            role=user.role,
            player_id=user.player_id,
            workspace=WorkspaceRead(
                id=ws.id,
                name=ws.name,
                my_teams=[
                    MyTeamRef(id=wt.team_id, name=wt.team.name, label=wt.label) for wt in ws.teams
                ],
            ),
        )


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
    # An upload's job (DATA-1): where its Demos went.
    upload: uuid.UUID | None = None
    match_id: int | None = None


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


class JobTiming(BaseModel):
    label: str
    n: int
    median: float | None  # seconds


class JobTimings(BaseModel):
    """How long a Scout's stages take, over the latest finished ones (OPS-5)."""

    jobs: int
    rows: list[JobTiming]


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


# -- system ------------------------------------------------------------------------
class Usage(BaseModel):
    """Bytes in use out of the bytes there are."""

    used: int
    total: int


class HostStats(BaseModel):
    """The whole host's load right now (app/services/system.py)."""

    cpu_percent: float
    cpus: int
    load: list[float] = Field(description="Load average over 1, 5 and 15 minutes")
    memory: Usage
    swap: Usage
    disk: Usage
    uptime: float = Field(description="Seconds since the host booted")


class ScoutNow(BaseModel):
    """The Analysis Job the worker is on."""

    public_id: uuid.UUID
    label: str
    stage_label: str
    cycle: JobCycle | None


class SystemState(BaseModel):
    """What the footer shows: the host, the worker's pulse, and the Scouts."""

    host: HostStats
    worker: bool
    scout: ScoutNow | None
    queued: int
    # The commit this API runs ("" when it wasn't deployed, as in development).
    version: str


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
    steamid: str = Field(description="As a string: Steam ids exceed JavaScript's safe integers.")
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


class TeamTier(BaseModel):
    tier: str
    maps: int
    won: int
    expected: float
    residual: float  # Maps won above (or below) what the two Ratings expected


class TeamTrendPoint(BaseModel):
    date: dt.date
    rating: float


class TeamStrength(BaseModel):
    """The Team's Rating and its results by the opponent's tier (TM-2, TM-10)."""

    name: str
    rating: float
    series: int
    last: dt.date | None
    cold: bool
    region: str | None
    lineup_changed: bool
    rank: int | None
    ranked: int
    trend: list[TeamTrendPoint]
    tiers: list[TeamTier]


class MapPoolRow(BaseModel):
    map: str
    label: str
    active: bool
    maps: int
    won: int
    rounds: int
    share: float | None  # Rounds won, percent
    shrunk: float | None  # pulled toward the Team's own share over every Map
    recent: int  # Match Maps in the last 90 days of its data
    last: str | None
    status: str  # deep | weak | thin | untested


class TeamMapPool(BaseModel):
    """How strong and how deep a Team's map pool is (TM-6)."""

    mean: float
    depth: int
    active: list[str]
    rows: list[MapPoolRow]


class TeamDetail(BaseModel):
    team: TeamRow
    record: MatchRecord
    results: list[TeamResult]
    n_parsed_maps: int
    map_record: list[MapRecordRow]
    players: list[TeamPlayer]
    plannable: list[TeamRef] = []
    strength: TeamStrength | None = None
    map_pool: TeamMapPool | None = None


# -- matches -----------------------------------------------------------------------
class MatchMapTab(BaseModel):
    map_number: int
    label: str
    scoreline: str
    parsed: bool
    playable: bool


class PatchRef(BaseModel):
    """A CS2 patch that starts an era (DATA-7)."""

    date: str
    name: str
    note: str = ""


class PatchList(BaseModel):
    patches: list[PatchRef]
    active: list[str]  # the Active Duty Maps today


class MatchInfo(BaseModel):
    id: int
    hltv_id: int | None  # None for a Match a Workspace uploaded
    hltv_url: str
    kind: str = "official"  # or "scrim" (CONTEXT.md)
    opponent_label: str = ""  # the other side's name when it has no Team row
    team1: TeamRef | None
    team2: TeamRef | None
    score: str
    tournament: str
    played_at: dt.datetime | None
    maps: list[MatchMapTab]
    default_map: int | None
    patch: PatchRef | None = None  # the era it was played in

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


class SpotLabel(BaseModel):
    """A Spot's name and where to print it."""

    name: str
    x: float
    y: float
    level: int | None = Field(description="Index into the scene's levels; None for every floor.")


class Scene(BaseModel):
    plate: Plate
    labels: list[CalloutLabel]
    levels: list[SceneLevel]
    spots: list[SpotLabel] = []


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


class LineupPlayer(BaseModel):
    """One Player a Lineup can hold. ``steamid`` is a string: it outgrows a JS number."""

    steamid: str
    name: str
    team: str = Field(description="The Team they played for here, or last played for.")
    maps: int
    last_played: dt.datetime | None = None
    default: bool = Field(description="In the Team's most recent parsed Match.")

    @field_validator("last_played")
    @classmethod
    def last_played_utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value)


class LineupPlayers(BaseModel):
    players: list[LineupPlayer]


class LineupMember(BaseModel):
    steamid: str
    name: str
    elsewhere: str = Field("", description="A new signing: the Team their numbers come from.")


class GameplanLineup(BaseModel):
    """One side's Lineup, as the plan was built with it."""

    picked: bool = Field(description="False: the five from the most recent parsed Match.")
    players: list[LineupMember]


class GameplanLineups(BaseModel):
    mine: GameplanLineup
    theirs: GameplanLineup


class GameplanHeader(BaseModel):
    my_team: TeamRef
    opponent: TeamRef
    lede: GameplanLede
    tabs: list[GameplanTab]
    default_tab: str
    stamp: str
    lineups: GameplanLineups


class GameplanPanel(BaseModel):
    """One panel's data. Its shape differs per tab and is typed on the page."""

    tab: str
    stamp: str
    cached: bool
    ms: float
    data: dict[str, Any]


# -- Workspace members and invites (docs/plans/01 WS-3) -----------------------------
class MemberPlayer(BaseModel):
    steamid: str
    name: str


class MemberRead(BaseModel):
    id: int
    username: str
    role: str
    player: MemberPlayer | None
    is_active: bool
    created_at: dt.datetime | None
    last_login_at: dt.datetime | None

    @field_validator("created_at", "last_login_at")
    @classmethod
    def stamped_utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value)


class MemberPatch(BaseModel):
    is_active: bool | None = None
    role: Literal["staff", "player"] | None = None
    player_steamid: str | None = Field(default=None, pattern=r"^(\d{1,20})?$")


class InviteCreate(BaseModel):
    role: Literal["staff", "player"] = "staff"
    player_steamid: str | None = Field(default=None, pattern=r"^\d{1,20}$")
    # A password reset for this member instead of a new one.
    user_id: int | None = None


class InviteRead(BaseModel):
    id: int
    role: str
    player: MemberPlayer | None
    username: str  # the member a reset is for, else ""
    created_at: dt.datetime
    expires_at: dt.datetime
    used_at: dt.datetime | None
    token: str = ""  # only in the answer to the POST that made it

    @field_validator("created_at", "expires_at", "used_at")
    @classmethod
    def stamped_utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value)


class InvitePublic(BaseModel):
    """What the invite page shows before anyone signs in."""

    workspace: str
    role: str
    player: str
    username: str  # set for a password reset: the name stays


class InviteAccept(BaseModel):
    username: str = Field(default="", max_length=32)
    password: str = Field(min_length=1, max_length=200)


class WorkspaceMembers(BaseModel):
    members: list[MemberRead]
    invites: list[InviteRead]


# -- A Player's own page (docs/plans/01 WS-4) --------------------------------------
class MeMap(BaseModel):
    match_id: int
    map_number: int
    map: str
    played_at: dt.datetime | None
    team: str
    opponent: str
    scrim: bool
    won: bool | None
    score: str
    kills: int
    deaths: int
    adr: float | None
    swing_per_round: float | None
    reviewed: bool

    @field_validator("played_at")
    @classmethod
    def played_utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value)


class MeFinding(BaseModel):
    match_id: int
    map_number: int
    map: str
    round: int | None
    t: float | None
    code: str
    kind: str
    label: str
    title: str
    text: str
    swing: float
    scrim: bool


class MeOverview(BaseModel):
    player: MemberPlayer
    maps: list[MeMap]
    focus: list[MeFinding]
    keep: list[MeFinding]
    focus_maps: int


# -- Declared roles (docs/plans/04 PL-4) -------------------------------------------
class DeclaredRoleRead(BaseModel):
    side: str
    map: str
    role: str
    label: str


class DeclaredRolePut(BaseModel):
    side: Literal["ct", "t"]
    map: str = Field(default="", pattern=r"^(de_[a-z0-9_]{2,30})?$")
    # "" clears it: the role is inferred again.
    role: str = Field(default="", max_length=16)


class DeclaredRoles(BaseModel):
    roles: list[DeclaredRoleRead]
    # Each Side's roles to choose from: [{"role", "label"}].
    choices: dict[str, list[dict[str, str]]]


# -- Development plans (docs/plans/07 RV-9) -----------------------------------------
class GoalProgress(BaseModel):
    value: float | None
    low: float | None
    high: float | None
    maps: int
    rounds: int
    events: int | None
    verdict: str  # "reached", "close", "not_yet" or "no_data"


class GoalRead(BaseModel):
    id: int
    kpi: str
    label: str
    better: str
    unit: str
    baseline: float | None
    target: float
    start_on: dt.date
    due_on: dt.date
    status: str
    notes: str
    progress: GoalProgress


class GoalSuggestion(BaseModel):
    kpi: str
    label: str
    baseline: float
    target: float
    events: int
    rounds: int
    over: float | None
    excess: float


class KpiChoice(BaseModel):
    kpi: str
    label: str
    better: str
    unit: str


class DevelopmentPlan(BaseModel):
    goals: list[GoalRead]
    suggestions: list[GoalSuggestion]
    kpis: list[KpiChoice]


class GoalCreate(BaseModel):
    kpi: str = Field(max_length=32)
    target: float
    baseline: float | None = None  # read from the last 90 days when left out
    start_on: dt.date | None = None
    due_on: dt.date | None = None
    notes: str = Field(default="", max_length=4000)


class GoalPatch(BaseModel):
    target: float | None = None
    due_on: dt.date | None = None
    status: Literal["active", "done", "dropped"] | None = None
    notes: str | None = Field(default=None, max_length=4000)


# -- Scrim log (docs/plans/07 RV-6) -------------------------------------------------
class ScrimMap(BaseModel):
    map_number: int
    label: str
    scoreline: str
    won: bool | None


class ScrimLine(BaseModel):
    text: str
    advice: str = ""
    weight: float = 0.0


class ScrimRow(BaseModel):
    match_id: int
    played_at: dt.datetime | None
    partner: str
    maps: list[ScrimMap]
    focus: list[ScrimLine]
    strengths: list[ScrimLine]

    @field_validator("played_at")
    @classmethod
    def played_utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value)


class ScrimLog(BaseModel):
    team: TeamRef
    scrims: list[ScrimRow]


# -- Review meeting agenda (docs/plans/07 RV-10) ------------------------------------
class AgendaRef(BaseModel):
    map_number: int
    round: int | None


class AgendaItem(BaseModel):
    text: str
    advice: str = ""
    refs: list[AgendaRef] = []


class AgendaSection(BaseModel):
    key: str
    title: str
    minutes: int
    items: list[AgendaItem]


class AgendaPlayer(BaseModel):
    player: str
    swing: float
    lines: list[AgendaItem]


class Agenda(BaseModel):
    team: str
    opponent: str
    minutes: int
    sections: list[AgendaSection]
    players: list[AgendaPlayer]


# -- Review notes and disputes (docs/plans/07 RV-7) ---------------------------------
class NoteShape(BaseModel):
    """One mark drawn on the Replay (VIZ-8), in world units."""

    kind: Literal["arrow", "circle", "text"]
    points: list[tuple[float, float]] = Field(min_length=1, max_length=2)
    text: str = Field(default="", max_length=80)


class NoteRead(BaseModel):
    id: int
    kind: str
    match_id: int
    map_number: int
    round: int | None
    t: float | None
    code: str
    sids: list[str]
    text: str
    tag: str
    reason: str
    drawing: list[NoteShape] | None = None
    created_by: str
    created_at: dt.datetime

    @field_validator("created_at")
    @classmethod
    def created_utc(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)


class NoteCreate(BaseModel):
    kind: Literal["note", "dispute"] = "note"
    round: int | None = None
    t: float | None = None
    code: str = Field(default="", max_length=32)
    sids: list[str] = Field(default_factory=list, max_length=10)
    text: str = Field(default="", max_length=4000)
    tag: str = Field(default="", max_length=32)
    reason: str = Field(default="", max_length=32)
    drawing: list[NoteShape] | None = Field(default=None, max_length=12)


class NoteList(BaseModel):
    notes: list[NoteRead]
    reasons: dict[str, str]


class PlaylistItem(BaseModel):
    match_id: int
    map_number: int
    round: int
    t: float | None = None
    sid: str | None = None
    text: str = Field(default="", max_length=1000)


class PlaylistItemRead(PlaylistItem):
    label: str  # "Team vs Team · Map", read from the Match now


class PlaylistWrite(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    note: str = Field(default="", max_length=4000)
    items: list[PlaylistItem] = Field(default_factory=list, max_length=60)
    shared: bool = False


class PlaylistSummary(BaseModel):
    id: int
    title: str
    rounds: int
    shared: bool
    created_by: str
    updated_at: dt.datetime

    @field_validator("updated_at")
    @classmethod
    def updated_utc(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)


class PlaylistRead(PlaylistSummary):
    note: str
    items: list[PlaylistItemRead]


class DisputeRate(BaseModel):
    code: str
    label: str
    disputes: int
    findings: int
    rate: float | None
    reasons: dict[str, int]


# -- Timeout audit and opening duels (docs/plans/07 RV-8) --------------------------
class AuditTimeout(BaseModel):
    round: int
    team_id: int
    team: str
    side: str
    lost_before: int
    won_next: bool
    expected: float | None


class AuditMissed(BaseModel):
    round: int
    team_id: int
    team: str
    lost_before: int
    won_next: bool
    left: int


class OpeningLine(BaseModel):
    sid: str
    name: str
    team_id: int | None
    team: str
    attempts: int
    won: int
    won_pct: float | None
    traded: int
    traded_pct: float | None
    after_kill_won_pct: float | None
    after_death_won_pct: float | None


class AuditPoolLine(BaseModel):
    rounds: int
    won: int
    pct: float | None


class AuditPool(BaseModel):
    maps: int
    after_timeout: AuditPoolLine
    without: AuditPoolLine


class MapAudit(BaseModel):
    known: bool
    timeouts: list[AuditTimeout]
    missed: list[AuditMissed]
    openings: list[OpeningLine]
    pool: AuditPool


# -- A Team's style (docs/plans/05 TM-5) --------------------------------------------
class StyleMetric(BaseModel):
    key: str
    label: str
    value: float
    unit: str  # "s" a median in seconds, "%" a share
    n: int
    thin: bool
    pct: int | None  # percentile among the Teams on the Map
    teams: int
    more: str  # what a high percentile means


class StyleSide(BaseModel):
    side: str
    label: str
    metrics: list[StyleMetric]


class TeamStyle(BaseModel):
    map: str
    label: str
    sides: list[StyleSide]


class RosterSpan(BaseModel):
    from_: dt.date = Field(alias="from")
    to: dt.date
    maps: int

    model_config = {"populate_by_name": True}


class RosterPlayer(BaseModel):
    steamid: str
    name: str
    maps: int
    spans: list[RosterSpan]


class RosterTimeline(BaseModel):
    """Who played for a Team when (TM-10): each Player's stretches of Match Maps."""

    from_: dt.date | None = Field(alias="from")
    to: dt.date | None
    players: list[RosterPlayer]

    model_config = {"populate_by_name": True}


class TeamStyleView(BaseModel):
    maps: list[str]
    style: TeamStyle | None


class FixtureStyle(BaseModel):
    mine: TeamStyle
    theirs: TeamStyle


# -- After the Match: the Briefing checked (docs/plans/06 GP-8) ---------------------
class CheckRef(BaseModel):
    match: int
    map: int
    round: int


# -- After the first contact (docs/plans/05 TM-7) -----------------------------------
class AfterBranch(BaseModel):
    then: str  # the plant: "A", "B" or "none"
    n: int
    won: int
    refs: list[CheckRef]


class AfterNode(BaseModel):
    won: bool | None  # the opening was the Team's (None: a Setup, not an opening)
    where: str  # "A", "mid" or "B"
    n: int
    # Named "wins": "won" says whose opening it was.
    wins: int
    then: list[AfterBranch]
    looked: int = 0  # CT, opening lost at a site: Rounds with tokens to look at
    reinforced: int = 0  # ... of which another CT reached that site within 10 s


class AfterPlantSpots(BaseModel):
    site: str
    rounds: int
    places: list[tuple[str, int]]


class AfterRetake(BaseModel):
    site: str
    situation: str  # CT alive at the plant against T: "ahead", "even", "behind"
    n: int
    won: int
    refs: list[CheckRef]


class AfterT(BaseModel):
    rounds: int
    openings: list[AfterNode]
    setups: list[AfterNode]
    plants: int
    plant_median: float | None
    late: int
    late_won: int
    post_plant: list[AfterPlantSpots]


class AfterCT(BaseModel):
    rounds: int
    openings: list[AfterNode]
    retakes: list[AfterRetake]


class AfterContact(BaseModel):
    map: str
    t: AfterT
    ct: AfterCT


class AfterContactView(BaseModel):
    maps: list[str]
    after: AfterContact | None


class CheckResult(BaseModel):
    judged: bool
    showed: bool
    hits: int
    chances: int
    rate_before: int | None
    rate: int | None
    won: int
    refs: list[CheckRef]
    median: float | None = None
    pct: int | None = None
    unchecked: str | None = None


class CheckLine(BaseModel):
    title: str
    section: str
    result: CheckResult | None


class CheckMap(BaseModel):
    map: str
    label: str
    played: bool
    map_number: int | None
    lines: list[CheckLine]


class CheckVeto(BaseModel):
    played: list[str]
    briefed: list[str]
    hit: int


class CheckForecast(BaseModel):
    format: str | None
    p: float | None
    won: bool
    brier: float | None
    winner: str


class PlanCheck(BaseModel):
    match_id: int | None
    maps: list[CheckMap]
    totals: dict[str, int]
    veto: CheckVeto | None
    forecast: CheckForecast | None


# -- The veto lab (docs/plans/06 GP-10) ---------------------------------------------
class VetoLabSide(BaseModel):
    maps: int
    won: int
    shrunk: float | None
    recent: int
    status: str


class VetoLabScrims(BaseModel):
    maps: int
    rounds: int
    share: float


class VetoLabStrats(BaseModel):
    active: int
    recent: int


class VetoLabMap(BaseModel):
    map: str
    base: float | None
    adjust: float
    p: float | None
    mine: VetoLabSide | None
    theirs: VetoLabSide | None
    scrims: VetoLabScrims | None
    strats: VetoLabStrats | None = None  # our active Strats there (SB-4)


class VetoOption(BaseModel):
    map: str
    expected: float
    minimax: float
    chance: float | None


class VetoNext(BaseModel):
    who: str
    kind: str
    options: list[VetoOption]


class VetoStep(BaseModel):
    who: str
    kind: str


class VetoLine(BaseModel):
    who: str
    kind: str
    map: str
    chance: float | None = None


class VetoState(BaseModel):
    format: str
    we_start: bool
    steps: list[VetoStep]
    done: list[str]
    expected: float
    minimax: float
    next: VetoNext | None
    line: list[VetoLine]
    maps: list[str]
    decider: str | None


class VetoLab(BaseModel):
    maps: list[VetoLabMap]
    limits: list[dict]
    veto: VetoState | None


class VetoLabAsk(BaseModel):
    format: Literal["bo1", "bo3", "bo5"] = "bo3"
    we_start: bool = True
    done: list[str] = Field(default_factory=list, max_length=7)
    adjust: dict[str, float] = Field(default_factory=dict)


# -- The timeout card (docs/plans/06 GP-4) ------------------------------------------
class TimeoutMove(BaseModel):
    key: str
    label: str
    usual: int  # percent of their other Rounds
    pressed: int  # percent of their Rounds under pressure
    rounds: int
    counter: str
    refs: list[CheckRef]


class TimeoutSide(BaseModel):
    side: str
    moves: list[TimeoutMove]


class TimeoutCard(BaseModel):
    map: str
    rounds: int
    pressure: int
    sides: list[TimeoutSide]
    pool: AuditPool


# -- What the data covers (docs/plans/02 DATA-9) -------------------------------------
class CoverageTeam(BaseModel):
    id: int
    name: str
    mine: bool
    maps: int
    by_map: list[tuple[str, int]]
    # Match Maps per lack: behind, no_tickdata, no_loadout, no_sightings,
    # no_events, derived_stale, review_stale.
    flags: dict[str, int]
    last_played: dt.datetime | None
    last_parsed: dt.datetime | None


class CoverageMap(BaseModel):
    map: str
    maps: int
    teams: int


class CoverageQueued(BaseModel):
    match: int
    map: int
    map_name: str
    teams: str
    played_at: dt.datetime | None
    reason: str  # "no_tickdata" or "no_loadout"


class MomentumRow(BaseModel):
    """TM-11: Rounds after a streak, observed against what the buys expected."""

    key: str
    label: str
    n: int
    observed: float
    expected: float
    residual: float
    low: float  # the residual's 80% range
    high: float


class Coverage(BaseModel):
    schema_version: int
    totals: dict[str, int]
    teams: list[CoverageTeam]
    maps: list[CoverageMap]
    queue: list[CoverageQueued]
    queued: int


# -- The week's practice (docs/plans/07 RV-11) ---------------------------------------
class WeekReview(BaseModel):
    match_id: int
    opponent: str
    score: str
    played_at: dt.datetime | None


class WeekGoal(BaseModel):
    player: str
    steamid: str
    kpi: str
    target: float
    due_on: dt.date
    verdict: str  # reached, close, not_yet, no_data
    value: float | None


class WeekScrim(BaseModel):
    match_id: int
    partner: str
    played_at: dt.datetime | None
    focus: list[str]


class WeekPrep(BaseModel):
    briefing: str
    title: str
    mine: int
    theirs: int
    opponent: str
    shared: bool


class WeekDay(BaseModel):
    day: str
    theme: str
    blocks: list[str]  # which of review, goals, scrims, prep the day shows


class PracticeWeek(BaseModel):
    team: TeamRef | None
    days: list[WeekDay]
    review: list[WeekReview]
    goals: list[WeekGoal]
    scrims: list[WeekScrim]
    prep: list[WeekPrep]


# -- Staff's notes on Playbook lines (docs/plans/06 GP-13) ---------------------------
class PlaybookNoteRead(BaseModel):
    text: str
    by: str
    at: dt.datetime


class PlaybookNoteWrite(BaseModel):
    team_id: int
    map_name: str = Field(pattern=r"^de_[a-z0-9_]{2,30}$")
    key: str = Field(pattern=r"^[0-9a-f]{16}$")
    text: str = Field(default="", max_length=1000)


# -- The Workspace's audit log (docs/plans/01 WS-7) ---------------------------------
class AuditLine(BaseModel):
    id: int
    at: dt.datetime
    actor: str
    action: str
    subject: str
    detail: dict[str, Any]

    @field_validator("at")
    @classmethod
    def at_utc(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)


# -- The Round search (docs/plans/09 VIZ-7) ------------------------------------------
class SearchCondition(BaseModel):
    place: str = Field(min_length=1, max_length=40)
    min: int = Field(default=1, ge=0, le=5)
    max: int | None = Field(default=None, ge=0, le=5)
    start: int = Field(default=0, ge=0, le=180)  # seconds after freeze end
    end: int = Field(default=180, ge=0, le=180)


class SearchAsk(BaseModel):
    map_name: str = Field(pattern=r"^de_[a-z0-9_]{2,30}$")
    side: Literal["ct", "t"]
    team_id: int | None = None
    buy: Literal["full", "light"] | None = None
    conditions: list[SearchCondition] = Field(min_length=1, max_length=6)
    # Where the side died or got its kills in all the matched Rounds (a heatmap).
    heat: Literal["deaths", "kills"] | None = None
    # The Side's Team ahead or behind by two or more, or close, when the Round began.
    score: Literal["ahead", "close", "behind"] | None = None


class SearchRound(BaseModel):
    match: int
    map: int
    round: int
    team: str
    won: bool | None
    buy: str
    played_at: str | None


class SearchResult(BaseModel):
    looked: int
    found: int
    won: int
    rounds: list[SearchRound]
    heat: dict[str, Any] | None = None  # the heatmap's data, as /gameplan/.../heatmap


# -- The lineup library (docs/plans/08 SB-3) -----------------------------------------
class LineupRef(BaseModel):
    match: int
    map: int
    round: int


class Lineup(BaseModel):
    key: str
    type: str
    side: str
    throws: int
    from_: str = Field(alias="from")
    to: str
    x: float
    y: float
    z: float
    pitch: float
    yaw: float
    land: list[int]
    flight: float | None
    teams: list[tuple[str, int]]
    players: list[tuple[str, int]]
    setpos: str
    refs: list[LineupRef]

    model_config = {"populate_by_name": True}


# -- The Stratbook (docs/plans/08 SB-1, SB-7) ---------------------------------------
class StratRole(BaseModel):
    slot: int = Field(ge=1, le=5)
    player: str = Field(default="", max_length=20)  # a Steam id, or "" for the slot
    role: str = Field(default="", max_length=40)
    does: str = Field(default="", max_length=500)


class StratGrenade(BaseModel):
    slot: int | None = Field(default=None, ge=1, le=5)
    type: Literal["smoke", "flash", "he", "inferno", "decoy"] = "smoke"
    place: str = Field(default="", max_length=40)
    at: float | None = Field(default=None, ge=0, le=180)
    note: str = Field(default="", max_length=300)
    lineup: str | None = Field(default=None, max_length=64)  # a Lineup's key (SB-3)


class StratExampleWrite(BaseModel):
    match_id: int
    map_number: int
    round: int = Field(ge=1, le=60)
    note: str = Field(default="", max_length=300)


class StratWrite(BaseModel):
    team_id: int
    map_name: str = Field(pattern=r"^de_[a-z0-9_]{2,30}$")
    side: Literal["ct", "t"]
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["default", "execute", "fake", "retake", "setup", "pistol", "anti_eco",
                  "force"] = "default"  # fmt: skip
    description: str = Field(default="", max_length=8000)
    roles: list[StratRole] = Field(default_factory=list, max_length=5)
    grenades: list[StratGrenade] = Field(default_factory=list, max_length=25)
    timings: str = Field(default="", max_length=4000)
    variations: str = Field(default="", max_length=4000)
    calls: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    status: Literal["draft", "active", "retired"] = "draft"
    visibility: Literal["staff", "team"] = "staff"
    # On creation only: example Rounds to keep with it (a Set play's, SB-2).
    examples: list[StratExampleWrite] = Field(default_factory=list, max_length=12)


class StratRow(BaseModel):
    id: int
    team: TeamRef
    map_name: str
    side: str
    name: str
    kind: str
    status: str
    visibility: str
    examples: int
    updated_at: dt.datetime

    @field_validator("updated_at")
    @classmethod
    def updated_utc(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)


class StratExampleRead(BaseModel):
    id: int
    match_id: int
    map_number: int
    round: int
    label: str
    source: str
    confirmed: bool
    note: str


class StratTally(BaseModel):
    played: int
    won: int


class StratReport(BaseModel):
    """How the Strat did over its kept Rounds (SB-4)."""

    played: int
    won: int = 0
    low: int | None = None  # 80% range of the share won, percent
    high: int | None = None
    pending: int = 0  # found Rounds Staff have yet to confirm
    by_buy: dict[str, StratTally] = {}
    official: StratTally | None = None
    scrim: StratTally | None = None
    last: str | None = None


class StratCoverage(BaseModel):
    active: int
    recent: int


class StratRead(StratRow):
    description: str
    roles: list[StratRole]
    grenades: list[StratGrenade]
    timings: str
    variations: str
    calls: str
    tags: list[str]
    examples_list: list[StratExampleRead]
    versions: int
    can_edit: bool
    report: StratReport


class StratEventRead(BaseModel):
    user: str
    action: str
    at: dt.datetime

    @field_validator("at")
    @classmethod
    def at_utc(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)


class StratVersionRead(BaseModel):
    id: int
    created_by: str
    created_at: dt.datetime
    payload: dict

    @field_validator("created_at")
    @classmethod
    def created_utc(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)


# -- Briefings (docs/plans/01 WS-5) ------------------------------------------------
class BriefingMapPick(BaseModel):
    map: str = Field(pattern=r"^de_[a-z0-9_]{2,30}$")
    note: str = Field(default="", max_length=2000)
    # Each line's place in that Map's Playbook panel, e.g. "advice.ct.levers.0".
    picks: list[str] = Field(default_factory=list, max_length=40)
    # SB-6: the my team's Strats for this Map to read with it (active, shared).
    strats: list[int] = Field(default_factory=list, max_length=20)


class BriefingCreate(BaseModel):
    my_team_id: int
    opponent_id: int
    my_lineup: list[str] = Field(default_factory=list, max_length=5)
    their_lineup: list[str] = Field(default_factory=list, max_length=5)
    title: str = Field(min_length=1, max_length=160)
    note: str = Field(default="", max_length=4000)
    include_forecast: bool = False
    # The Game Plan stamp the page showed: a parse since then means reload first.
    stamp: str = ""
    maps: list[BriefingMapPick] = Field(default_factory=list, max_length=7)
    share: bool = False


class BriefingRow(BaseModel):
    id: uuid.UUID
    title: str
    my_team: TeamRef
    opponent: TeamRef
    created_at: dt.datetime
    shared_at: dt.datetime | None
    created_by: str

    @field_validator("created_at", "shared_at")
    @classmethod
    def stamped_utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value)


class BriefingRead(BriefingRow):
    include_forecast: bool
    # {"note", "lineups": {"mine": [names], "theirs": [names]}, "forecast"?,
    #  "maps": [{"map", "label", "note", "items": [{kind, section, title, lines, counter, refs}]}]}
    content: dict[str, Any]


class BriefingList(BaseModel):
    briefings: list[BriefingRow]


class BriefingDraft(BaseModel):
    """The Assistant's notes for a Briefing (AS-6), for Staff to edit."""

    note: str
    maps: dict[str, str]
    # Numbers in the draft the picked lines don't hold, per map id (or "note").
    unverified: dict[str, list[str]]
    cost_usd: float


# -- Uploads (docs/plans/02 DATA-1) -------------------------------------------------
class UploadCreate(BaseModel):
    """Describe the file first; its bytes follow in parts."""

    kind: Literal["scrim", "official"]
    played_on: dt.date
    my_team_id: int
    opponent_id: int | None = None
    opponent_name: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=500)
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)


class UploadPlayer(BaseModel):
    steamid: str
    name: str
    known: str  # "mine", "theirs" or "": whom the stored Maps have him playing for


class UploadMap(BaseModel):
    map_number: int
    map: str
    mine: int | None  # which of the two groups is my team's; None waits for Staff
    assigned: bool
    groups: list[list[UploadPlayer]]


class UploadRead(BaseModel):
    id: uuid.UUID
    created_at: dt.datetime
    kind: str
    played_on: dt.date
    my_team: TeamRef
    opponent: TeamRef | None
    opponent_name: str
    note: str
    filename: str
    size_bytes: int
    parts_total: int
    part_bytes: int
    received: int
    status: str
    error: str
    job_id: uuid.UUID | None
    match_id: int | None
    maps: list[UploadMap]

    @field_validator("created_at")
    @classmethod
    def created_utc(cls, value: dt.datetime) -> dt.datetime:
        return _utc(value)


class UploadList(BaseModel):
    uploads: list[UploadRead]


class UploadSides(BaseModel):
    map_number: int
    mine: int = Field(ge=0, le=1)


class UploadPartAck(BaseModel):
    received: int
    parts_total: int


# -- Forecasts (docs/plans/03 FC-4) -------------------------------------------------
class ForecastCreate(BaseModel):
    """Make the Fixture's Forecast now and keep it. Lineups are Steam ids."""

    my_team_id: int
    opponent_id: int
    my_lineup: list[str] = Field(default_factory=list, max_length=5)
    their_lineup: list[str] = Field(default_factory=list, max_length=5)
    format: Literal["bo1", "bo3", "bo5"] = "bo3"


class ForecastRead(BaseModel):
    id: uuid.UUID
    created_at: dt.datetime
    my_team: TeamRef
    opponent: TeamRef
    format: str
    p_series: float
    text: str
    model_version: str
    outputs: dict[str, Any]
    graded_at: dt.datetime | None
    result: dict[str, Any] | None
    log_loss: float | None
    brier: float | None

    @field_validator("created_at", "graded_at")
    @classmethod
    def stamped_utc(cls, value: dt.datetime | None) -> dt.datetime | None:
        return _utc(value)


class ReliabilityBand(BaseModel):
    lo: float
    hi: float
    n: int
    won: int
    mean_p: float
    low: float
    high: float


class ForecastSummary(BaseModel):
    made: int
    graded: int
    expired: int
    coin_log_loss: float
    log_loss: float | None
    brier: float | None
    favourites_won: int | None
    maps: int
    map_log_loss: float | None
    # FC-4: per band of our chance, the series and how many we won (80% range).
    reliability: list[ReliabilityBand] = []


class ForecastList(BaseModel):
    items: list[ForecastRead]
    summary: ForecastSummary


# -- the Assistant -----------------------------------------------------------------
class AssistantConfig(BaseModel):
    configured: bool = Field(description="Claude is set up: the chat can answer.")
    voice: bool = Field(description="ElevenLabs is set up: answers are spoken, the mic works.")


class AssistantTurn(BaseModel):
    role: str
    content: str
    page: str = Field("", description="The page a question was asked on (its label).")


class AssistantContext(BaseModel):
    """The page the Assistant was opened from. Unknown ids are ignored, not trusted."""

    mine: int | None = None
    theirs: int | None = None
    my_lineup: list[str] = Field(default_factory=list, description="Steam ids, at most five.")
    their_lineup: list[str] = Field(default_factory=list, description="Steam ids, at most five.")
    team: int | None = None
    match: int | None = None
    map: int | None = Field(default=None, description="The Match Map open on a match page.")
    round: int | None = Field(default=None, description="The Round open on the Replay.")
    player: str | None = Field(default=None, description="A Player page's Steam id.")
    job: str | None = Field(default=None, description="A Scout's job page (its public id).")
    picker: bool | None = Field(default=None, description="The Game Plan picker.")
    page: str = Field("", description="This page's label, as the history's turns name theirs.")


class AssistantChat(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[AssistantTurn] = Field(
        default_factory=list, description="Earlier turns as plain text, oldest first."
    )
    context: AssistantContext | None = None
    voice: bool = Field(True, description="Speak each paragraph (base64 MP3 in the event).")


class AssistantTranscript(BaseModel):
    text: str


class AssistantUserUsage(BaseModel):
    username: str
    today_usd: float
    month_usd: float
    turns: int
    tts_chars: int


class AssistantUsageReport(BaseModel):
    """At list prices (``assistant.PRICES``); ElevenLabs' speech is counted, not priced."""

    today_usd: float
    month_usd: float
    daily_cap_usd: float
    users: list[AssistantUserUsage]


class ReviewTeam(BaseModel):
    id: int | None
    name: str


class ReviewMark(BaseModel):
    """One of a Round's worst or best moments for a Player."""

    n: int
    swing: float


class ReviewPlayer(BaseModel):
    sid: str = Field(description="Steam id, as the Replay names players.")
    name: str
    team_id: int | None
    team: str
    rounds: int
    swing: float = Field(description="Sum of the Player's Swing over the Match Map.")
    swing_per_round: float
    best_round: ReviewMark
    worst_round: ReviewMark
    counts: dict[str, int] = Field(description="Findings led by this Player, per kind.")
    utility: dict[str, float] = Field(description="Flashes, enemies blinded, HE damage...")


class ReviewEvent(BaseModel):
    t: float = Field(description="Seconds from freeze end, the Replay's clock.")
    kind: str = Field(description="kill, plant or defuse.")
    sid: str | None
    victim: str | None = None
    d_ct: float = Field(description="The CT side's Win probability change.")
    hs: bool | None = None
    weapon: str | None = None


class ReviewFinding(BaseModel):
    id: str
    kind: str = Field(description="key_play, mistake, missed_chance or utility.")
    code: str
    kind_label: str
    code_label: str
    round: int | None = Field(description="None for a Finding about the whole Match Map.")
    t: float | None
    side: str
    team_id: int | None
    sids: list[str] = Field(description="The Players involved, the one it is about first.")
    swing: float
    sight: bool = Field(description="Needed Sightings (schema 13).")
    title: str
    text: str


class SummaryRef(BaseModel):
    """Where a Summary line can be seen in the Replay."""

    map_number: int | None
    round: int
    t: float = Field(description="Seconds from freeze end.")
    sid: str | None


class SummaryCount(BaseModel):
    sid: str | None = None
    name: str | None = None
    n: int


class SummaryNumber(BaseModel):
    key: str
    label: str
    value: str
    tone: str = Field(description="good, bad, or empty when the number says nothing.")


class SummaryMapText(BaseModel):
    map_number: int
    text: str


class SummaryItem(BaseModel):
    """One thing a Summary says went well or wrong: a number past its threshold,
    or a Pattern of Findings."""

    key: str = Field(description="The number (opening, trade, force...) or the Finding code.")
    kind: str = Field(description="metric or pattern.")
    good: bool
    label: str
    text: str
    weight: float = Field(description="What it won or cost, in Rounds.")
    refs: list[SummaryRef]
    count: int
    advice: str = Field(description="What to work on; set on problems.")
    players: list[SummaryCount] = []
    spots: list[SummaryCount] = []
    maps: list[int] = Field(default=[], description="Across a Match: the Maps it showed on.")
    texts: list[SummaryMapText] = Field(default=[], description="Across a Match: per Map.")


class TeamSummary(BaseModel):
    team_id: int | None
    rounds: int
    won: int
    numbers: list[SummaryNumber]
    strengths: list[SummaryItem]
    problems: list[SummaryItem]
    focus: list[SummaryItem] = Field(description="The Focus points, costliest first.")


class MapSummary(BaseModel):
    """Both Teams' Summaries over both Sides, and over each one."""

    all: list[TeamSummary]
    ct: list[TeamSummary]
    t: list[TeamSummary]


class RoundBullet(BaseModel):
    text: str
    label: str
    swing: float
    finding: str | None = Field(description="The Finding's id, or None for a Round fact.")
    map_number: int | None
    round: int
    t: float
    sid: str | None


class RoundFocus(RoundBullet):
    advice: str


class RoundTeamSummary(BaseModel):
    side: str
    team_id: int | None
    won: bool
    line: str
    good: list[RoundBullet]
    bad: list[RoundBullet]
    focus: RoundFocus | None


class ReviewRound(BaseModel):
    n: int
    winner_side: str
    winner_team_id: int | None
    ct_team_id: int | None
    t_team_id: int | None
    reason: str
    site: str
    ct_buy: str
    t_buy: str
    seconds: float
    wp: list[list[float]] = Field(description="[t, CT Win probability] through the Round.")
    events: list[ReviewEvent]
    swing: dict[str, float]
    sides: dict[str, str]
    decider: str | None
    summary: str
    findings: list[str] = Field(description="Ids of this Round's Findings, in reading order.")
    teams: list[RoundTeamSummary] = Field(description="Each Team's Summary of the Round.")


class Review(BaseModel):
    version: str
    # OPS-8: an older cut, served while the worker rebuilds it.
    stale: bool = False
    sightings: bool
    missing: str = Field(description="What this Match Map's Review lacks without Sightings.")
    teams: list[ReviewTeam]
    players: list[ReviewPlayer]
    rounds: list[ReviewRound]
    findings: list[ReviewFinding]
    kinds: dict[str, str]
    summary: MapSummary


class MatchReviewSummaryMapTeam(BaseModel):
    team_id: int | None
    won: int
    rounds: int
    strength: SummaryItem | None
    problem: SummaryItem | None


class MatchReviewSummaryMap(BaseModel):
    map_number: int
    label: str
    scoreline: str
    winner_team_id: int | None
    reviewed: bool = Field(description="False for a Map with no Tick Data: its score only.")
    teams: list[MatchReviewSummaryMapTeam]


class MatchReviewSummaryPlayer(BaseModel):
    sid: str
    name: str
    maps: int
    rounds: int
    swing: float
    swing_per_round: float
    counts: dict[str, int]


class MatchTeamSummary(BaseModel):
    team_id: int | None
    maps_played: int
    rounds: int
    won: int
    strengths: list[SummaryItem] = Field(description="Said on two Maps or more.")
    problems: list[SummaryItem] = Field(description="Said on two Maps or more.")
    focus: list[SummaryItem]
    players: list[MatchReviewSummaryPlayer]


class MatchReviewSummary(BaseModel):
    """Each Team's Summary of a Match, from its Maps' Reviews."""

    teams: list[ReviewTeam]
    maps: list[MatchReviewSummaryMap]
    summaries: list[MatchTeamSummary]
    names: dict[str, str] = Field(description="Steam id to name, for the Players a line names.")


# -- players (docs/plans PL-2) ------------------------------------------------------
class PlayerRef(BaseModel):
    steamid: str = Field(description="As a string: Steam ids exceed JavaScript's safe integers.")
    name: str
    aliases: list[str]


class PlayerTeamSpan(BaseModel):
    team_id: int
    name: str
    maps: int
    first: dt.datetime | None
    last: dt.datetime | None


class PlayerLine(BaseModel):
    rounds: int
    kills: int
    deaths: int
    adr: float | None
    kast_pct: float | None
    opening_attempts: int
    opening_win_pct: float | None
    traded_death_pct: float | None


class PlayerTotals(PlayerLine):
    swing_per_round: float | None
    # 80% range from resampling his Match Maps, with three or more (RV-2).
    swing_low: float | None = None
    swing_high: float | None = None
    maps: int


class PlayerMapLine(PlayerLine):
    map: str
    side: str


class PlayerFormRow(BaseModel):
    match_id: int
    map_number: int
    map: str
    played_at: dt.datetime | None
    team: str
    opponent: str
    won: bool | None
    rounds: int
    kills: int
    deaths: int
    adr: float | None
    kast_pct: float | None
    swing_per_round: float | None
    # A Scrim for one of the Workspace's my teams (RV-6): his own development,
    # shown in his form, counted in none of the page's totals.
    scrim: bool = False


class PlayerFindingRate(BaseModel):
    code: str
    kind: str
    label: str
    count: int
    per24: float | None = Field(description="This Player's, per 24 reviewed Rounds.")
    pool_per24: float | None = Field(description="Every reviewed Player's, per 24 Rounds.")


class PlayerSpot(BaseModel):
    map: str
    side: str
    place: str
    rounds: int
    share: float | None


class PlayerWeapon(BaseModel):
    weapon: str
    kills: int
    share: float | None


class PlayerDuels(BaseModel):
    """Duels against what the guns on both sides expected (PL-6)."""

    duels: int
    won: int
    won_pct: float
    expected_pct: float
    over_per_round: float


class PlayerAim(BaseModel):
    """Aim from his engagements (PL-5); ``rank`` 0-100 among every Player past the bar."""

    engagements: int
    maps: int
    ttd_ms: int | None
    xhair_deg: float | None
    counter_strafe_pct: float | None
    first_hit_pct: float | None
    enough: bool
    players: int | None = None
    rank: dict[str, int] = {}


class PlayerTierLine(BaseModel):
    tier: str
    maps: int
    rounds: int
    swing_per_round: float


class PressureLine(BaseModel):
    key: str  # pistol, match_point, close, other
    label: str
    rounds: int
    per_round: float | None  # Swing per Round
    pool_per_round: float | None


class Consistency(BaseModel):
    maps: int
    sd: float  # the spread of per-Map Swing per Round
    pct: int  # high: their Maps differ more than most Players'
    players: int


class PlayerPage(BaseModel):
    player: PlayerRef
    teams: list[PlayerTeamSpan]
    totals: PlayerTotals
    sides: dict[str, PlayerLine]
    maps: list[PlayerMapLine]
    form: list[PlayerFormRow]
    findings: list[PlayerFindingRate]
    rounds_reviewed: int
    spots: list[PlayerSpot]
    weapons: list[PlayerWeapon]
    openings: OpeningLine | None = None
    duels: PlayerDuels | None = None
    by_tier: list[PlayerTierLine] = []
    aim: PlayerAim | None = None
    pressure: list[PressureLine] = []
    consistency: Consistency | None = None
