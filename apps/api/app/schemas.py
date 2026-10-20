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
