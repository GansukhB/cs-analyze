"""The warm-up: every analytic page computed before anyone opens it (docs/adr/0014).

One thread of the worker (`tasks._start_warmer`), at a low CPU priority, keeps
the stored answers (`app/services/answers.py`) current. Each round it plans the
pages Staff are likely to open and works through them in this order
(docs/adr/0015):

1. the answers a page has just read stale (``wanted_at``), newest first:
   someone is looking at it now; checked again between every two pages;
2. the answers whose own Teams or Matches changed (a Match parsed, a Review
   rebuilt), the latest change first: after each Match a Scout parses, the
   fixtures of its two Teams come before anything else; the other pages
   someone opened in the last :data:`LEARNED_DAYS` days (a picked Lineup, a
   Playbook view, another period) among them;
3. the planned pages with no answer yet, which a first visit would compute
   inside the request;
4. the answers only the Pool moved under (any parse anywhere), oldest first,
   none younger than :data:`POOL_MIN_AGE`: the page calls them fresh, and
   they come round once every day or two.

The plan: for each my team of every Workspace, its own pages (the overview,
management, utility and Self-scout over each window and Map, the five's
profiles, positions) and its Matches' pages (the list, each Map's report and
audit, each Match's summary and agenda), then its whole Game Plan against each
opponent (header, every tab, each Map's Playbook and timeout card, the break
between Maps, the veto lab, the scouting page by Map): first the latest Scouts'
fixtures, then the Upcoming matches', the Teams it met most recently, then every
other Team with :data:`MIN_MAPS` parsed Maps, most Maps first. Every Team in a
fixture brings its own pages, shared by every fixture it is in: the team page,
its roster, its style, after-contact and utility map by Map, and the first view
of its heatmaps and routes.

It never runs beside a parse: each page takes the host's heavy permit first,
and the permit goes back as soon as a parse waits for it (`heavy.someone_waiting`).
Its progress is in Redis (:data:`STATUS`), for the footer and the opponent picker.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from redis.exceptions import RedisError
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.cache import get_cache
from app.models import (
    AnalysisJob,
    JobKind,
    JobStatus,
    Match,
    MatchMap,
    StoredAnswer,
    Team,
    UpcomingMatch,
    WorkspaceTeam,
)
from app.models.base import utcnow
from app.services import answers, dbctx, heavy, scope

logger = logging.getLogger(__name__)

STATUS = "answers:status"
STATUS_TTL = 300
MIN_MAPS = 3
LEARNED_DAYS = 30
RECENT_JOB_DAYS = 7
# An answer only the Pool moved under is not computed again sooner than this.
POOL_MIN_AGE = timedelta(hours=6)
IDLE_SECONDS = 60
PAUSE_SECONDS = 5.0
START_DELAY = 20.0
NICE = 10
# Overview, utility: the windows the pages offer; management: its periods.
PERIODS = ("30", "90", "180", "all")
OWNER_PERIODS = ("q", "m", "y")
GP_TABS = ("todo", "decision", "maps", "players", "roles", "edge", "duels", "h2h",
           "heatmaps", "movement")  # fmt: skip
SIDES = ("t", "ct")
MODES = ("heat", "move", "trade", "lurk")
HEAT_KINDS = ("kills", "deaths", "positions")


@dataclass
class Item:
    kind: str
    params: dict
    scope: dict
    group: str
    fixture: tuple[int, int] | None = None
    key: str = ""
    digest: str = ""
    tier: str = ""  # wanted, stale, missing, pool: why this round computes it


@dataclass
class Plan:
    items: list[Item] = field(default_factory=list)
    fixtures: list[tuple[int, int]] = field(default_factory=list)


# ------------------------------------------------------------------ plan ---
def _names(db: Session) -> dict[int, str]:
    return dict(db.execute(select(Team.id, Team.name)).all())


def my_teams(db: Session) -> list[tuple[int, int]]:
    """(team id, workspace id) for every Workspace's my teams, in its order."""
    return list(
        db.execute(
            select(WorkspaceTeam.team_id, WorkspaceTeam.workspace_id).order_by(
                WorkspaceTeam.workspace_id, WorkspaceTeam.id
            )
        ).all()
    )


def parsed_map_counts(db: Session) -> dict[int, int]:
    """Each Team's parsed Match Maps everyone sees."""
    out: dict[int, int] = {}
    for column in (MatchMap.team1_id, MatchMap.team2_id):
        rows = db.execute(
            select(column, func.count(MatchMap.id))
            .join(Match, Match.id == MatchMap.match_id)
            .where(
                MatchMap.parsed_at.is_not(None), Match.workspace_id.is_(None), column.is_not(None)
            )
            .group_by(column)
        ).all()
        for team_id, n in rows:
            out[team_id] = out.get(team_id, 0) + n
    return out


def opponents(db: Session, team_id: int, counts: dict[int, int]) -> list[int]:
    """Who a my team's Game Plan is computed against, most likely first."""
    order: list[int] = []

    def add(team: int | None) -> None:
        if team and team != team_id and team not in order and counts.get(team, 0) >= MIN_MAPS:
            order.append(team)

    since = utcnow() - timedelta(days=RECENT_JOB_DAYS)
    for job in db.scalars(
        select(AnalysisJob)
        .where(
            AnalysisJob.kind.in_((JobKind.SCOUT, JobKind.TEAM)),
            AnalysisJob.status == JobStatus.SUCCESS,
            AnalysisJob.finished_at >= since,
        )
        .order_by(AnalysisJob.finished_at.desc())
    ):
        if job.kind == JobKind.SCOUT and job.my_team_id == team_id:
            add(job.opponent_id)
        elif job.kind == JobKind.SCOUT and job.opponent_id == team_id:
            add(job.my_team_id)
        elif job.kind == JobKind.TEAM:
            add(job.my_team_id)
    for opponent in db.scalars(
        select(UpcomingMatch.opponent_id)
        .where(
            UpcomingMatch.team_id == team_id,
            UpcomingMatch.starts_at >= utcnow() - timedelta(hours=6),
        )
        .order_by(UpcomingMatch.starts_at)
    ):
        add(opponent)
    met = db.execute(
        select(Match.team1_id, Match.team2_id, func.max(Match.played_at).label("last"))
        .where(or_(Match.team1_id == team_id, Match.team2_id == team_id))
        .group_by(Match.team1_id, Match.team2_id)
        .order_by(func.max(Match.played_at).desc())
    ).all()
    for t1, t2, _last in met:
        add(t2 if t1 == team_id else t1)
    for team, _n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        add(team)
    return order


def _active_maps(db: Session) -> tuple[str, ...]:
    from app.services import map_pool

    with dbctx.using(db):
        return tuple(map_pool.active_duty())


def _five(db: Session, team: Team) -> list[str]:
    from app.services import team_overview

    with dbctx.using(db):
        return [str(p.steamid) for p in team_overview.current_five(team)]


def team_items(db: Session, team: Team, where: dict, maps: tuple[str, ...]) -> list[Item]:
    """A my team's own pages, each over the windows and Maps it offers."""
    group = team.name
    t = team.id
    out = [Item("v2.overview", {"team": t, "period": p, "scrims": False}, where, group)
           for p in PERIODS]  # fmt: skip
    out += [Item("v2.owner", {"team": t, "period": p}, where, group) for p in OWNER_PERIODS]
    out += [Item("v2.utility", {"team": t, "period": p, "scrims": False, "map": None}, where,
                 group) for p in PERIODS]  # fmt: skip
    for m in (None, *maps):
        params = {"team": t, "map": m, "buy": "", "days": None, "since": ""}
        out.append(Item("v2.self_scout", params, where, group))
    for steamid in _five(db, team):
        params = {"team": t, "steamid": steamid, "scrims": False, "map": None, "side": "t"}
        out.append(Item("v2.player", params, where, group))
    for side in SIDES:
        for mode in MODES:
            params = {"team": t, "opponent": None, "map": None, "side": side, "mode": mode}
            out.append(Item("v2.spatial", params, where, group))
    out.append(Item("v2.matches", {"team": t, "scrims": False}, where, group))
    return out


def _team_maps(db: Session, team_id: int) -> list[str]:
    from app.services import style

    with dbctx.using(db):
        return list(style.maps_of(team_id))


def shared_items(
    db: Session, team: Team, where: dict, maps: tuple[str, ...], group: str,
    fixture: tuple[int, int] | None = None,
) -> list[Item]:  # fmt: skip
    """Any Team's own pages, which every fixture it is in shares: the team page,
    its roster, style, after-contact and utility map by Map, and the first view
    of its heatmaps and routes (both Sides, everyone, the whole Round)."""
    t = team.id

    def item(kind: str, params: dict) -> Item:
        return Item(kind, params, where, group, fixture)

    out = [item("team.page", {"team": t}), item("team.roster", {"team": t})]
    for m in _team_maps(db, t):
        out.append(item("team.after_contact", {"team": t, "map": m}))
    for m in maps:
        out.append(item("team.style", {"team": t, "map": m}))
        for side in SIDES:
            out.append(item("team.utility", {"team": t, "map": m, "side": side}))
        for k in HEAT_KINDS:
            out.append(item("gp.heatmap", heatmap_params(t, m, k)))
        out.append(item("gp.movement", movement_params(t, m)))
    return out


def heatmap_params(team: int, map_name: str, kind: str, **view) -> dict:
    """A heatmap cell's parameters as the page asks for them (`MapGrid.tsx`)."""
    return {"team": team, "map": map_name, "player": "all", "side": "all", "kind": kind,
            "level": "all", "phase": "all", "buy": "all", "compare": False, "place": "",
            **view}  # fmt: skip


def movement_params(team: int, map_name: str, **view) -> dict:
    return {"team": team, "map": map_name, "player": "all", "side": "all", "kind": "routes",
            "level": "all", **view}  # fmt: skip


def match_items(db: Session, team: Team, where: dict) -> list[Item]:
    """A my team's Matches' pages, newest first: each Match's summary and agenda,
    each parsed Map's report and audit. ``where`` lets the Workspace's Scrims in,
    as a Match's own page does."""
    group = f"{team.name} · Match"
    rows = db.execute(
        select(MatchMap.match_id, MatchMap.map_number)
        .join(Match, Match.id == MatchMap.match_id)
        .where(
            or_(Match.team1_id == team.id, Match.team2_id == team.id),
            MatchMap.parsed_at.is_not(None),
        )
        .order_by(Match.played_at.desc(), Match.id.desc(), MatchMap.map_number)
    ).all()
    out: list[Item] = []
    seen: set[int] = set()
    for match_id, number in rows:
        if match_id not in seen:
            seen.add(match_id)
            out.append(Item("match.summary", {"match": match_id}, where, group))
            out.append(Item("match.agenda", {"match": match_id, "team": team.id}, where, group))
        out.append(Item("v2.report", {"team": team.id, "match": match_id, "map_number": number},
                        where, group))  # fmt: skip
        out.append(Item("match.audit", {"match": match_id, "map_number": number}, where, group))
    return out


def fixture_items(
    mine: Team, theirs: Team, where: dict, workspace_id: int, maps: tuple[str, ...]
) -> list[Item]:
    """One my team's whole Game Plan against one opponent, as its pages ask for it."""
    from app.schemas import VetoLabAsk

    group = f"{mine.name} vs {theirs.name}"
    fx = (mine.id, theirs.id)
    base = {"mine": mine.id, "theirs": theirs.id}
    plain = {**base, "my_lineup": "", "their_lineup": "", "since": ""}

    def item(kind: str, params: dict) -> Item:
        return Item(kind, params, where, group, fx)

    out = [item("gp.header", plain)]
    out += [item("gp.panel", {**plain, "tab": tab}) for tab in GP_TABS]
    out.append(item("v2.scouting", {"team": mine.id, "opponent": theirs.id, "map": None}))
    out.append(item("gp.between", {**base, "played": None}))
    for m in maps:
        out.append(item("gp.playbook", {**base, "map": m, "my_lineup": "", "their_lineup": "",
                                        "view": None}))  # fmt: skip
        out.append(item("v2.scouting", {"team": mine.id, "opponent": theirs.id, "map": m}))
        out.append(item("gp.timeout", {**base, "map": m}))
    # Last: it lets the session see our Scrims, and the session goes with it.
    veto = VetoLabAsk(format="bo3", we_start=True, done=[], adjust={}).model_dump(mode="json")
    out.append(item("gp.veto", {**base, "workspace_id": workspace_id, **veto}))
    return out


def build_plan(db: Session) -> Plan:
    plan = Plan()
    names = {t.id: t for t in db.scalars(select(Team))}
    counts = parsed_map_counts(db)
    maps = _active_maps(db)
    pairs = my_teams(db)
    seen: set[str] = set()

    def keep(items: list[Item], part: str) -> None:
        for it in items:
            it.key = answers.key_of(it.kind, it.params, part)
            it.digest = answers.hash_of(it.key)
            if it.digest not in seen:
                seen.add(it.digest)
                plan.items.append(it)

    def part_of(where: dict) -> str:
        answers.bind_spec(db, where)
        return answers.scope_part(db)

    # A Workspace's own pages first, then its Matches', then the Game Plans, my
    # team by my team.
    for team_id, workspace_id in pairs:
        team = names.get(team_id)
        if team is None:
            continue
        where = {"ws": workspace_id, "scrims": False}
        part = part_of(where)
        keep(team_items(db, team, where, maps), part)
        keep(shared_items(db, team, where, maps, team.name), part)
        own = {"ws": workspace_id, "scrims": True}
        own_part = part_of(own)  # bound first: the query must see the Scrims
        keep(match_items(db, team, own), own_part)
    for team_id, workspace_id in pairs:
        team = names.get(team_id)
        if team is None:
            continue
        where = {"ws": workspace_id, "scrims": False}
        part = part_of(where)
        for opponent_id in opponents(db, team_id, counts):
            theirs = names.get(opponent_id)
            if theirs is None:
                continue
            keep(fixture_items(team, theirs, where, workspace_id, maps), part)
            group = f"{team.name} vs {theirs.name}"
            keep(shared_items(db, theirs, where, maps, group, (team_id, opponent_id)), part)
            # Two Workspaces with the same my team share the fixture (only its
            # veto lab is each one's own): it is counted once.
            if (team_id, opponent_id) not in plan.fixtures:
                plan.fixtures.append((team_id, opponent_id))
    db.info.pop(scope.KEY, None)
    return plan


def wanted_items(db: Session) -> list[Item]:
    rows = db.execute(
        select(StoredAnswer.kind, StoredAnswer.key, StoredAnswer.key_hash, StoredAnswer.spec)
        .where(StoredAnswer.wanted_at.is_not(None))
        .order_by(StoredAnswer.wanted_at.desc())
        .limit(50)
    ).all()
    out = [_from_row(r, "wanted") for r in rows if r.kind in answers.KINDS]
    for it in out:
        it.tier = "wanted"
    return out


def learned_items(db: Session, planned: set[str]) -> list[Item]:
    since = utcnow() - timedelta(days=LEARNED_DAYS)
    rows = db.execute(
        select(StoredAnswer.kind, StoredAnswer.key, StoredAnswer.key_hash, StoredAnswer.spec)
        .where(StoredAnswer.last_hit_at >= since)
        .order_by(StoredAnswer.last_hit_at.desc())
    ).all()
    return [
        _from_row(r, "learned")
        for r in rows
        if r.key_hash not in planned and r.kind in answers.KINDS
    ]


def _from_row(row, group: str) -> Item:
    spec = row.spec or {}
    return Item(row.kind, spec.get("params") or {}, spec.get("scope") or {"all": True}, group,
                key=row.key, digest=row.key_hash)  # fmt: skip


# ----------------------------------------------------------------- status ---
def _write_status(status: dict) -> None:
    try:
        get_cache().set(STATUS, json.dumps(status, default=str), ex=STATUS_TTL)
    except RedisError:
        pass


def status() -> dict | None:
    """The warm-up's last word on itself, or None when the worker is not running it."""
    try:
        raw = get_cache().get(STATUS)
    except RedisError:
        return None
    return json.loads(raw) if raw else None


def readiness(db: Session, mine: int, opponents_: list[int]) -> dict[int, str]:
    """For a my team's picker: each opponent's Game Plan ``fresh``, ``stale`` (it
    opens at once, then refreshes) or ``none`` (its first visit computes)."""
    part = answers.scope_part(db)
    keys, current = {}, {}
    for o in opponents_:
        params = {"mine": mine, "theirs": o, "my_lineup": "", "their_lineup": "", "since": "",
                  "tab": "todo"}  # fmt: skip
        keys[o] = answers.hash_of(answers.key_of("gp.panel", params, part))
        current[o] = answers.stamp(db, "gp.panel", params)
    stored = answers.stamps(db, list(keys.values()))
    out = {}
    for o, digest in keys.items():
        found = stored.get(digest)
        if found is None:
            out[o] = "none"
        else:
            out[o] = "fresh" if answers.is_fresh(found, current[o]) else "stale"
    return out


# ------------------------------------------------------------------- run ---
class Warmer:
    """The thread's state: one per worker process."""

    def __init__(self, session_factory=None):
        from app.db import SessionLocal

        self.sessions = session_factory or SessionLocal
        self.stop = threading.Event()
        self.token: str | None = None
        self.failed: dict[str, str] = {}  # digest -> stamp it failed at
        self.status: dict = {"state": "starting"}
        self.pruned_at: datetime | None = None

    # -- the permit ---------------------------------------------------------
    def _turn(self) -> bool:
        """Hold the heavy permit before a page; False once the worker stops."""
        while not self.stop.is_set():
            if self.token is None:
                self.token = heavy.try_hold("warm-up")
            if self.token is not None:
                return True
            self._say(state="paused")
            self.stop.wait(PAUSE_SECONDS)
        return False

    def _yield(self) -> None:
        """Hand the permit over when a parse waits for it."""
        if self.token is not None and heavy.someone_waiting():
            heavy.release(self.token)
            self.token = None
            self.stop.wait(heavy.POLL_SECONDS * 2)

    def _release(self) -> None:
        heavy.release(self.token)
        self.token = None

    def _say(self, **changes) -> None:
        self.status.update(changes, updated_at=datetime.now(UTC).isoformat())
        _write_status(self.status)

    # -- a round ----------------------------------------------------------
    def run(self) -> None:
        _lower_priority()
        self.stop.wait(START_DELAY)
        while not self.stop.is_set():
            try:
                worked = self.round()
            except Exception:
                logger.exception("warm-up round failed")
                worked = False
            finally:
                self._release()
            if not worked:
                self._say(state="idle")
                self._wait_for_wake(IDLE_SECONDS)

    def _wait_for_wake(self, seconds: float) -> None:
        try:
            get_cache().blpop(answers.WAKE, timeout=max(1, int(seconds)))
        except RedisError:
            self.stop.wait(seconds)

    def round(self) -> bool:
        """One pass over everything due. True if it computed anything."""
        started = time.monotonic()
        answers.take_replan()  # planned now
        with self.sessions() as db:
            plan = build_plan(db)
            planned = {it.digest for it in plan.items}
            self._prune(db, planned)
            others = learned_items(db, planned)
        everything = plan.items + others
        current, changed = current_stamps(self.sessions, everything)
        with self.sessions() as db:
            stored = answers.stored(db, [it.digest for it in everything])
            adopt_legacy(db, everything, stored, current, changed)
        queue = order(plan.items, others, stored, current, changed)
        todo = {fx: 0 for fx in plan.fixtures}
        for it in queue:
            if it.fixture in todo and it.tier != "pool":
                todo[it.fixture] += 1
        ready = sum(1 for n in todo.values() if n == 0)
        tiers = {t: sum(1 for it in queue if it.tier == t) for t in ("stale", "missing", "pool")}
        self._say(state="working", round_started_at=datetime.now(UTC).isoformat(),
                  total=len(queue), done=0, missing=tiers["missing"], stale=tiers["stale"],
                  pool=tiers["pool"], learned=len(others), planned=len(plan.items),
                  fixtures_total=len(plan.fixtures), fixtures_ready=ready, current="")  # fmt: skip
        did = self._wanted()
        done = 0
        db, group = None, None
        try:
            for it in queue:
                if self.stop.is_set() or answers.take_replan():
                    break  # a Match was parsed: plan again, its Teams first
                if self._wanted():
                    did = True
                # One session per run of a group: a fixture's tabs share its Report.
                if db is None or (it.group, json.dumps(it.scope, sort_keys=True)) != group:
                    if db is not None:
                        db.close()
                    db = self.sessions()
                    group = (it.group, json.dumps(it.scope, sort_keys=True))
                if self._compute(db, it):
                    did = True
                done += 1
                if it.fixture in todo and it.tier != "pool":
                    todo[it.fixture] -= 1
                    if todo[it.fixture] == 0:
                        ready += 1
                self._say(done=done, fixtures_ready=ready)
        finally:
            if db is not None:
                db.close()
        self._say(state="idle", current="", last_round_seconds=round(time.monotonic() - started))
        return did

    def _wanted(self) -> bool:
        """Compute what pages have just read stale, before anything else."""
        did = False
        for _ in range(20):  # a page asking again and again cannot hold the round
            with self.sessions() as db:
                items = wanted_items(db)
            if not items:
                break
            for it in items:
                if self.stop.is_set():
                    return did
                with self.sessions() as db:
                    if not self._compute(db, it):
                        _unwant(self.sessions, it.digest)
                did = True
        return did

    def _compute(self, db: Session, it: Item) -> bool:
        """Compute one page on ``db`` if its answer is missing or stale. True if it did."""
        if not self._turn():
            return False
        bound = None
        try:
            answers.bind_spec(db, it.scope)
            bound = scope.current(db)
            base = answers.data_stamp(db)
            # What the session remembered (a fixture's Report) was read before the
            # data moved (a parse while this waited for the permit): read it again.
            if db.info.get("warm_stamp") not in (None, base):
                db.info.pop("analysis_memo", None)
            db.info["warm_stamp"] = base
            stamp = answers.stamp(db, it.kind, it.params)
            if self.failed.get(it.digest) == stamp:
                return False
            found = answers.stamps(db, [it.digest]).get(it.digest)
            if answers.is_fresh(found, stamp) and (
                it.tier != "pool" or answers.pool_part(found) == answers.pool_part(stamp)
            ):
                _unwant(self.sessions, it.digest)
                return False
            self._say(state="working", current=f"{it.group} · {_label(it)}")
            key = it.key or answers.key_of(it.kind, it.params, answers.scope_part(db))
            answers.compute_and_store(db, it.kind, it.params, key=key, stamp=stamp)
            self.failed.pop(it.digest, None)
            return True
        except Exception as exc:
            db.rollback()
            logger.warning("warm-up: %s failed (%s: %s)", it.key, type(exc).__name__, exc)
            try:
                self.failed[it.digest] = answers.stamp(db, it.kind, it.params)
            except Exception:  # the stamp's own queries failed: try it next round
                self.failed.pop(it.digest, None)
            return False
        finally:
            # A page that let itself see the Workspace's Scrims (the veto lab) must
            # not hand what it read to the next page: the memo goes with it.
            if scope.current(db) != bound:
                db.info.pop("analysis_memo", None)
            self._yield()

    def _prune(self, db: Session, planned: set[str]) -> None:
        now = datetime.now(UTC)
        if self.pruned_at and now - self.pruned_at < timedelta(hours=6):
            return
        self.pruned_at = now
        gone = answers.prune(db, planned)
        if gone:
            logger.info("warm-up: %s stored answers no longer served were dropped", gone)


def current_stamps(session_factory, items: list[Item]):
    """Each item's current stamp and when what it reads last changed, read once
    per scope."""
    stamps: dict[str, str] = {}
    changed: dict[str, datetime | None] = {}
    by_scope: dict[str, list[Item]] = {}
    for it in items:
        by_scope.setdefault(json.dumps(it.scope, sort_keys=True), []).append(it)
    for where, group in by_scope.items():
        with session_factory() as db:
            answers.bind_spec(db, json.loads(where))
            for it in group:
                if it.kind not in answers.KINDS:
                    continue
                stamps[it.digest] = answers.stamp(db, it.kind, it.params)
                changed[it.digest] = answers.changed_at(db, it.kind, it.params)
    return stamps, changed


def adopt_legacy(db: Session, items: list[Item], stored: dict, current: dict, changed: dict):
    """An answer stored under the old, global stamp (before docs/adr/0015) whose
    Teams and Matches have not changed since it was computed is fresh: it gets the
    current stamp with no Pool part, so it waits in the Pool's turn rather than
    show every page as being refreshed after the deploy. Daily kinds are left to
    their day."""
    adopted = 0
    for it in items:
        found = stored.get(it.digest)
        if found is None or answers.POOL_SEP in (found[0] or "") or it.digest not in current:
            continue
        k = answers.KINDS.get(it.kind)
        if k is None or k.daily or k.deps is None:
            continue
        when = changed.get(it.digest)
        if when is not None and when > found[1]:
            continue
        legacy = f"{answers.fresh_part(current[it.digest])}{answers.POOL_SEP}legacy"
        answers.restamp(db, it.digest, legacy)
        stored[it.digest] = (legacy, found[1])
        adopted += 1
    if adopted:
        db.commit()
        logger.info("warm-up: %s stored answers from before per-Team stamps kept", adopted)
    return adopted


def order(planned: list[Item], learned: list[Item], stored: dict, current: dict,
          changed: dict) -> list[Item]:  # fmt: skip
    """The round's queue: stale (latest change first), missing (in plan order),
    then the Pool's turn (oldest first)."""
    stale: list[tuple] = []
    missing: list[Item] = []
    pool: list[tuple] = []
    cutoff = utcnow() - POOL_MIN_AGE
    for i, it in enumerate(planned + learned):
        if it.digest not in current:
            continue
        found = stored.get(it.digest)
        is_learned = i >= len(planned)
        if found is None:
            if not is_learned:
                it.tier = "missing"
                missing.append(it)
            continue
        stamp_, at = found
        if not answers.is_fresh(stamp_, current[it.digest]):
            it.tier = "stale"
            when = changed.get(it.digest) or datetime.min
            stale.append((-when.timestamp() if when != datetime.min else 0, is_learned, i, it))
        elif answers.pool_part(stamp_) != answers.pool_part(current[it.digest]) and at < cutoff:
            it.tier = "pool"
            pool.append((at, i, it))
    stale.sort(key=lambda r: r[:3])
    pool.sort(key=lambda r: r[:2])
    return [r[-1] for r in stale] + missing + [r[-1] for r in pool]


def _unwant(session_factory, digest: str) -> None:
    with session_factory() as db:
        db.execute(
            update(StoredAnswer).where(StoredAnswer.key_hash == digest).values(wanted_at=None)
        )
        db.commit()


LABELS = {
    "gp.header": "Game Plan", "gp.panel": "tab", "gp.playbook": "Playbook",
    "gp.style": "style", "gp.timeout": "timeout", "gp.between": "Map хооронд",
    "gp.utility": "utility", "gp.veto": "veto lab", "v2.scouting": "scouting",
    "v2.overview": "тойм", "v2.owner": "менежмент", "v2.utility": "utility",
    "v2.self_scout": "Self-scout", "v2.player": "тоглогч", "v2.spatial": "байрлал",
    "team.page": "багийн хуудас", "team.roster": "roster", "team.after_contact": "after-contact",
    "team.style": "style", "team.utility": "utility", "gp.heatmap": "heatmap",
    "gp.movement": "movement", "v2.matches": "матчууд", "v2.report": "report",
    "match.summary": "тойм", "match.agenda": "agenda", "match.audit": "audit",
}  # fmt: skip


def _label(it: Item) -> str:
    detail = it.params.get("tab") or it.params.get("map") or it.params.get("period") or ""
    return f"{LABELS.get(it.kind, it.kind)} {detail}".strip()


def _lower_priority() -> None:
    """Nice this thread alone (Linux names threads as processes); elsewhere the
    call would renice the whole worker, so it is left alone."""
    if not sys.platform.startswith("linux"):
        return
    try:
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), NICE)
    except OSError:
        logger.warning("could not lower the warm-up's priority")


_warmer: Warmer | None = None


def start() -> None:
    """Start the warm-up thread once per process (the worker's `worker_ready`)."""
    global _warmer
    if _warmer is not None:
        return
    # The kinds register when their routers are imported.
    import app.main  # noqa: F401

    _warmer = Warmer()
    threading.Thread(target=_warmer.run, name="warm-up", daemon=True).start()


def stop() -> None:
    if _warmer is not None:
        _warmer.stop.set()
        _warmer._release()
