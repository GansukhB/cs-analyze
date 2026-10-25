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
