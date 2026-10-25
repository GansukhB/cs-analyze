"""The v2 pages' shapes (the DEMOLAB design). Kept apart from ``schemas.py``
so the v1 contract reads as it did; shared shapes are imported from there."""

import datetime as dt
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from app.schemas import TeamRef, _utc

# Stored datetimes are naive UTC; every v2 one says so.
Utc = Annotated[dt.datetime, AfterValidator(_utc)]


class ReplayRef(BaseModel):
    """A Round on the Replay: /matches/{match}/m/{map}?round={round}."""

    match: int
    map: int
    round: int


# ---------------------------------------------------------------- Upcoming match


class ChecklistItem(BaseModel):
    text: str = Field(max_length=200)
    done: bool = False


class CounterPick(BaseModel):
    """A counter Staff picked on the scouting page for this Upcoming match."""

    key: str = Field(max_length=200)
    title: str = Field(max_length=300)
    body: str = Field(default="", max_length=1000)
    map: str = Field(default="", max_length=32)


class UpcomingRead(BaseModel):
    id: int
    team: TeamRef
    opponent: TeamRef
    starts_at: Utc
    best_of: int
    tournament: str
    match_id: int | None
    checklist: list[ChecklistItem]
    counters: list[CounterPick]


class UpcomingWrite(BaseModel):
    team_id: int
    opponent_id: int
    starts_at: dt.datetime
    best_of: Literal[1, 3, 5] = 3
    tournament: str = Field(default="", max_length=160)


class UpcomingPatch(BaseModel):
    starts_at: dt.datetime | None = None
    best_of: Literal[1, 3, 5] | None = None
    tournament: str | None = Field(default=None, max_length=160)
    checklist: list[ChecklistItem] | None = Field(default=None, max_length=30)
    counters: list[CounterPick] | None = Field(default=None, max_length=30)


class UpcomingList(BaseModel):
    upcoming: list[UpcomingRead]


# ---------------------------------------------------------------- Overview


class Share(BaseModel):
    """``won`` of ``of``; ``pct`` is None when ``of`` is 0."""

    won: int
    of: int
    pct: float | None
    prev: float | None = None


class Insight(BaseModel):
    key: str
    kind: str
    tone: Literal["strength", "risk", "watch"]
    label: str
    title: str
    advice: str
    map: str | None
    map_label: str | None
    side: str
    value: float
    pool: float
    z: float
    of: int
    n: int
    maps: int
    strength: str
    refs: list[ReplayRef]
    players: list[str]


class MapRow(BaseModel):
    map: str
    label: str
    active: bool
    played: int
    won: int
    win: float | None
    t: float | None
    ct: float | None
    pistol: float | None
    trend: list[float]
    status: Literal["strong", "improve", "test", "untested"]
    shrunk: float | None


class FormItem(BaseModel):
    match_id: int
    played_at: Utc | None
    opponent: str
    ours: int | None
    theirs: int | None
    won: bool | None
    scrim: bool


class TrendPoint(BaseModel):
    match_map_id: int
    played_at: Utc | None
    map: str
    rating: float


class PlayerNote(BaseModel):
    good: bool
    text: str


class PlayerCard(BaseModel):
    steamid: str
    name: str
    rating: float | None
    adr: float | None
    kast: float | None
    maps: int
    note: PlayerNote | None


class JobLine(BaseModel):
    public_id: str
    kind: str
    label: str
    status: str
    stage: str
    progress: int
    started_at: Utc | None
    finished_at: Utc | None
    error: str


class DemoLine(BaseModel):
    match_id: int
    map_number: int
    played_at: Utc | None
    opponent: str
    map: str
    ours: int | None
    theirs: int | None
    kind: str
    parsed: bool


class UploadLine(BaseModel):
    id: int
    filename: str
    kind: str
    status: str
    played_on: dt.date
    error: str


class Overview(BaseModel):
    team: TeamRef
    days: int | None
    scrims: bool
    n_matches: int
    n_scrims: int
    n_maps: int
    n_all_matches: int
    updated_at: Utc | None
    kpis: dict[str, Share]
    insights: list[Insight]
    maps: list[MapRow]
    form: list[FormItem]
    trend: list[TrendPoint]
    players: list[PlayerCard]
    jobs: list[JobLine]
    demos: list[DemoLine]
    uploads: list[UploadLine]
    upcoming: UpcomingRead | None


# ---------------------------------------------------------------- Match report


class ReportHalf(BaseModel):
    side: str | None
    ours: int
    theirs: int


class ReportRound(BaseModel):
    n: int
    won: bool | None
    side: str | None
    end: str
    site: str
    ours: int | None
    theirs: int | None
    our_buy: str
    their_buy: str
    turning: bool


class ReportFactor(BaseModel):
    key: str
    label: str
    us: float
    them: float


class ReportPlayer(BaseModel):
    steamid: str
    name: str
    kills: int
    deaths: int
    assists: int
    adr: float | None
    kast: float | None
    opening_kills: int
    opening_deaths: int
    multi: int
    clutch_won: int
    clutch_of: int
    utility_damage: int
    flash_assists: int
    awp_kills: int
    rating: float | None
    swing_per_round: float | None


class ReportTeam(BaseModel):
    team: TeamRef
    rating: float
    players: list[ReportPlayer]


class ReportBuy(BaseModel):
    buy: str
    label: str
    won: int
    of: int
    won_rounds: list[int]
    lost_rounds: list[int]


class ReportTurn(BaseModel):
    n: int
    won: bool
    title: str
    body: str
    from_wp: float
    to_wp: float
    site: str


class ReportQuick(BaseModel):
    opening: list[int]
    trade: list[int]
    clutch: list[int]
    post_plant: list[int]


class ReportMapTab(BaseModel):
    map_number: int
    label: str
    parsed: bool
    score: str


class MatchReport(BaseModel):
    match_id: int
    map_number: int
    map: str
    label: str
    kind: str
    best_of: int
    played_at: Utc | None
    tournament: str
    us: TeamRef
    them: TeamRef | None
    ours: int | None
    theirs: int | None
    maps: list[ReportMapTab]
    seconds: int | None
    halves: list[ReportHalf]
    rounds: list[ReportRound]
    factors: list[ReportFactor]
    teams: list[ReportTeam]
    buys: list[ReportBuy]
    turning: list[ReportTurn]
    quick: ReportQuick
    reviewed: bool


class MatchListItem(BaseModel):
    match_id: int
    played_at: Utc | None
    opponent: str
    ours: int | None
    theirs: int | None
    kind: str
    tournament: str
    maps: list[ReportMapTab]


class MatchList(BaseModel):
    matches: list[MatchListItem]


# ---------------------------------------------------------------- Player profile


class ProfileKpis(BaseModel):
    rating: float | None = None
    adr: float | None = None
    kast: float | None = None
    opening_pct: float | None = None
    hs: float | None = None
    traded_pct: float | None = None


class ProfileAxes(BaseModel):
    firepower: float | None = None
    entry: float | None = None
    trade: float | None = None
    utility: float | None = None
    clutch: float | None = None
    survival: float | None = None
    opening: float | None = None


class ProfileMate(BaseModel):
    steamid: str
    name: str
    axes: ProfileAxes
    kpis: ProfileKpis


class FormMap(BaseModel):
    match_id: int
    map_number: int
    map: str
    played_at: Utc | None
    opponent: str
    scrim: bool
    won: bool | None
    rating: float


class ProfileForm(BaseModel):
    maps: list[FormMap]
    sigma: float | None
    official: float | None
    scrim: float | None
    t: float | None
    ct: float | None


class ProfileMechanics(BaseModel):
    engagements: int
    maps: int
    enough: bool
    ttd_ms: float | None
    xhair_deg: float | None
    counter_strafe_pct: float | None
    first_hit_pct: float | None
    rank: dict[str, float] = {}
    medians: dict[str, float | None]
    players: int | None = None


class DuelCell(BaseModel):
    distance: Literal["near", "mid", "far"]
    phase: Literal["early", "mid", "late"]
    won: int
    lost: int


class PositionMap(BaseModel):
    map: str
    n: int


class ProfilePositions(BaseModel):
    maps: list[PositionMap]
    map: str | None
    side: str
    url: str | None
    kills: list[list[float]]
    deaths: list[list[float]]


class ProfileWeapon(BaseModel):
    weapon: str
    kills: int
    hs: float | None
    distance: float | None
    share: float
    dpr: float | None


class ProfileLine(BaseModel):
    good: bool
    text: str


class DevNote(BaseModel):
    text: str
    updated_at: Utc | None


class NoteWrite(BaseModel):
    text: str = Field(max_length=4000)


class PlayerProfile(BaseModel):
    steamid: str
    name: str
    aliases: list[str]
    team: TeamRef
    rounds: int
    maps: int
    clutch_won: int
    clutch_of: int
    pool_players: int
    kpis: ProfileKpis
    team_kpis: ProfileKpis
    pool_kpis: ProfileKpis
    axes: ProfileAxes
    team_axes: ProfileAxes
    mates: list[ProfileMate]
    form: ProfileForm
    mechanics: ProfileMechanics | None
    duels: list[DuelCell]
    positions: ProfilePositions
    weapons: list[ProfileWeapon]
    lines: list[ProfileLine]
    note: DevNote | None


class FivePlayer(BaseModel):
    steamid: str
    name: str


class Five(BaseModel):
    players: list[FivePlayer]


# ---------------------------------------------------------------- Scouting


class ScoutMap(BaseModel):
    map: str
    label: str
    active: bool
    theirs: int
    won: int
    ours: int
    pick: float | None
    ban: float | None


class ScoutWindow(BaseModel):
    maps: int
    matches: int
    h2h_maps: int
    since: Utc | None
    rounds: int


class ScoutSites(BaseModel):
    buy: str
    n: int
    a: int
    b: int
    none: int
    won_a: int
    won_b: int
    won_none: int


class ScoutBin(BaseModel):
    from_: int = Field(alias="from")
    n: int

    model_config = {"populate_by_name": True}


class Scouting(BaseModel):
    team: TeamRef
    opponent: TeamRef
    maps: list[ScoutMap]
    map: str | None
    window: ScoutWindow
    sites: list[ScoutSites]
    timing: list[ScoutBin]
    t_rounds: int
    upcoming: UpcomingRead | None


# ---------------------------------------------------------------- Spatial


class Zone(BaseModel):
    place: str
    shares: list[float]
    all: float


class SpatialHeat(BaseModel):
    points: list[list[list[float]]]
    zones: list[Zone]


class SpatialRoute(BaseModel):
    label: str
    rounds: int
    share: float
    win: float | None
    kills: int
    deaths: int
    path: list[list[float]]


class TradePlayer(BaseModel):
    name: str
    deaths: int
    traded: int
    pct: float | None


class SpatialTrade(BaseModel):
    players: list[TradePlayer]
    traders: list[str]
    matrix: list[list[int]]
    segments: list[list[list[float]]]
    lone: list[list[float]]


class SpatialLurk(BaseModel):
    steamid: str
    name: str
    share: float
    rule: bool
    played: int
    curve: list[float | None]
    team_curve: list[float | None]
    rounds: int
    kills: int
    deaths: int
    untraded: int
    won: int


class SpatialTeam(BaseModel):
    team: TeamRef
    rounds: int
    heat: SpatialHeat | None = None
    routes: list[SpatialRoute] | None = None
    trade: SpatialTrade | None = None
    lurk: SpatialLurk | None = None


class SpatialLabel(BaseModel):
    name: str
    x: float
    y: float


class SpatialPlate(BaseModel):
    url: str | None
    lower: str | None = None
    width: int
    height: int
    extent: list[float]


class SpatialMap(BaseModel):
    map: str
    label: str
    n: int


class Spatial(BaseModel):
    maps: list[SpatialMap]
    map: str | None
    side: str
    mode: str
    windows: list[list[int]]
    plate: SpatialPlate | None
    labels: list[SpatialLabel]
    us: SpatialTeam | None
    them: SpatialTeam | None
    opponent: TeamRef | None


# ---------------------------------------------------------------- Utility


class UtilityKpis(BaseModel):
    damage_per_round: float | None
    assists_per_map: float | None
    blinded_per_flash: float | None
    team_flash_pct: float | None
    execute_seconds: float | None
    unused_per24: float | None


class SyncBin(BaseModel):
    from_: float = Field(alias="from")
    to: float | None
    n: int
    won: int

    model_config = {"populate_by_name": True}


class UtilitySync(BaseModel):
    bins: list[SyncBin]
    fights: int
    won: int
    flashes: int


class UtilityLineup(BaseModel):
    type: str
    side: str
    from_place: str
    to_place: str
    throws: int
    accuracy: float
    radius: float
    scatter: list[list[float]]
    throwers: list[str]


class UtilityPlayer(BaseModel):
    steamid: str
    name: str
    rounds: int
    per_round: float | None
    smokes: int
    flashes_thrown: int
    molotovs: int
    hes: int
    utility_damage: int
    flash_assists: int
    flashes: int
    enemies_blinded: int
    team_flashes: int
    team_flash_pct: float | None
    unused: int
    loadout_rounds: int


class UtilityReport(BaseModel):
    team: TeamRef
    days: int | None
    rounds: int
    maps: int
    throws: int
    kpis: UtilityKpis
    sync: UtilitySync
    map_choices: list[SpatialMap]
    map: str | None
    lineups: list[UtilityLineup]
    players: list[UtilityPlayer]


# ---------------------------------------------------------------- Practice


class TeamGoalProgress(BaseModel):
    value: float | None
    of: int
    low: float | None
    high: float | None
    verdict: str
    overdue: bool


class TeamGoalRead(BaseModel):
    id: int
    kpi: str
    label: str
    better: str
    unit: str
    map: str
    side: str
    title: str
    notes: str
    baseline: float | None
    target: float
    start_on: dt.date
    due_on: dt.date
    status: str
    progress: TeamGoalProgress


class TeamGoalWrite(BaseModel):
    kpi: str = Field(max_length=32)
    map: str = Field(default="", max_length=32)
    side: Literal["", "ct", "t"] = ""
    title: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=4000)
    baseline: float | None = None
    target: float
    start_on: dt.date | None = None
    due_on: dt.date


class TeamGoalPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)
    target: float | None = None
    due_on: dt.date | None = None
    status: Literal["active", "done", "dropped"] | None = None


class GoalKpi(BaseModel):
    kpi: str
    label: str
    better: str
    unit: str


class BlockRead(BaseModel):
    id: int
    day: dt.date
    start: str
    end: str
    kind: str
    title: str
    note: str
    opponent: TeamRef | None
    hours: float


class BlockWrite(BaseModel):
    day: dt.date
    start: str = Field(default="", pattern=r"^(|([01]\d|2[0-3]):[0-5]\d)$")
    end: str = Field(default="", pattern=r"^(|([01]\d|2[0-3]):[0-5]\d)$")
    kind: Literal["scrim", "drill", "review", "match", "rest"]
    title: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=500)
    opponent_id: int | None = None


class QueueRead(BaseModel):
    id: int
    match_id: int
    map_number: int
    map: str
    round: int
    t: float
    seconds: int
    title: str
    tag: str
    source: str
    position: int
    watched: bool


class QueueWrite(BaseModel):
    match_id: int
    map_number: int = Field(ge=1, le=9)
    round: int = Field(ge=1, le=99)
    t: float = Field(default=0.0, ge=0, le=300)
    seconds: int = Field(default=30, ge=5, le=180)
    title: str = Field(default="", max_length=300)
    tag: str = Field(default="", max_length=40)
    source: str = Field(default="", max_length=80)
    week: dt.date | None = None


class QueuePatch(BaseModel):
    watched: bool | None = None
    position: int | None = None
    title: str | None = Field(default=None, max_length=300)
    tag: str | None = Field(default=None, max_length=40)


class PlayerGoalLine(BaseModel):
    id: int
    player: str
    steamid: str
    label: str
    better: str
    unit: str
    baseline: float | None
    target: float
    due_on: dt.date
    value: float | None
    verdict: str


class Drill(BaseModel):
    text: str
    source: str
    match_id: int


class PracticePlan(BaseModel):
    team: TeamRef
    week: dt.date
    today: dt.date
    blocks: list[BlockRead]
    hours: dict[str, float]
    queue: list[QueueRead]
    goals: list[TeamGoalRead]
    history: list[TeamGoalRead]
    player_goals: list[PlayerGoalLine]
    drills: list[Drill]
    upcoming: UpcomingRead | None
