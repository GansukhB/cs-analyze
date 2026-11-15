"""The warm-up: every analytic page computed before anyone opens it (docs/adr/0014).

One thread of the worker (`tasks._start_warmer`), at a low CPU priority, keeps
the stored answers (`app/services/answers.py`) current. Each round it plans the
pages Staff are likely to open and works through them in this order:

1. the answers a page has just read stale (``wanted_at``), newest first:
   someone is looking at it now; checked again between every two pages;
2. the planned pages with no answer yet, which a first visit would compute
   inside the request;
3. the planned pages whose answer is stale, in the same order;
4. the other pages someone opened in the last :data:`LEARNED_DAYS` days (a
   picked Lineup, a Playbook view, another period), when stale.

The plan: for each my team of every Workspace, its own pages (the team page,
the overview, management, utility and Self-scout over each window and Map, the
five's profiles, positions), then its whole Game Plan against each opponent
(header, every tab, each Map's Playbook, style, timeout card and utility, the
break between Maps, the veto lab, the scouting page by Map, their team page):
first the latest Scouts' fixtures, then the Upcoming matches', the Teams it met
most recently, then every other Team with :data:`MIN_MAPS` parsed Maps, most
Maps first.

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


@dataclass
class Item:
    kind: str
    params: dict
    scope: dict
    group: str
    fixture: tuple[int, int] | None = None
    key: str = ""
    digest: str = ""


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
    out = [Item("team.page", {"team": t}, where, group)]
    out += [Item("v2.overview", {"team": t, "period": p, "scrims": False}, where, group)
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
        out.append(item("gp.style", {**base, "map": m}))
        out.append(item("gp.timeout", {**base, "map": m}))
        for side in SIDES:
            for whose in ("theirs", "mine"):
                out.append(item("gp.utility", {**base, "map": m, "side": side, "whose": whose}))
    out.append(item("team.page", {"team": theirs.id}))
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

    # A Workspace's own pages first, then the Game Plans, my team by my team.
    parts: dict[int, str] = {}
    for team_id, workspace_id in pairs:
        answers.bind_spec(db, {"ws": workspace_id, "scrims": False})
        parts[workspace_id] = answers.scope_part(db)
        team = names.get(team_id)
        if team is not None:
            keep(team_items(db, team, {"ws": workspace_id, "scrims": False}, maps),
                 parts[workspace_id])  # fmt: skip
    for team_id, workspace_id in pairs:
        team = names.get(team_id)
        if team is None:
            continue
        for opponent_id in opponents(db, team_id, counts):
            theirs = names.get(opponent_id)
            if theirs is None:
                continue
            where = {"ws": workspace_id, "scrims": False}
            before = len(plan.items)
            keep(fixture_items(team, theirs, where, workspace_id, maps), parts[workspace_id])
            if len(plan.items) > before or (team_id, opponent_id) not in plan.fixtures:
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
    return [_from_row(r, "wanted") for r in rows if r.kind in answers.KINDS]


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
    k = answers.KINDS["gp.panel"]
    current = answers.stamp_for(k, answers.data_stamp(db))
    keys = {}
    for o in opponents_:
        params = {"mine": mine, "theirs": o, "my_lineup": "", "their_lineup": "", "since": "",
                  "tab": "todo"}  # fmt: skip
        keys[o] = answers.hash_of(answers.key_of("gp.panel", params, part))
    stored = answers.stamps(db, list(keys.values()))
    out = {}
    for o, digest in keys.items():
        found = stored.get(digest)
        out[o] = "none" if found is None else ("fresh" if found == current else "stale")
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
            stored = answers.stamps(db, [it.digest for it in plan.items])
            current = _Stamps(self.sessions)
            missing = [it for it in plan.items if it.digest not in stored]
            stale = [
                it for it in plan.items
                if it.digest in stored and stored[it.digest] != current.of(it)
            ]  # fmt: skip
            others = learned_items(db, planned)
            known = answers.stamps(db, [it.digest for it in others])
            learned = [it for it in others if known.get(it.digest) != current.of(it)]
        queue = missing + stale + learned
        todo = {fx: 0 for fx in plan.fixtures}
        for it in queue:
            if it.fixture in todo:
                todo[it.fixture] += 1
        ready = sum(1 for n in todo.values() if n == 0)
        self._say(state="working", round_started_at=datetime.now(UTC).isoformat(),
                  total=len(queue), done=0, missing=len(missing), stale=len(stale),
                  learned=len(learned), planned=len(plan.items),
                  fixtures_total=len(plan.fixtures), fixtures_ready=ready, current="")  # fmt: skip
        did = self._wanted()
        done = 0
        db, group = None, None
        try:
            for it in queue:
                if self.stop.is_set() or answers.take_replan():
                    break  # a job ended: plan again, its fixture first
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
                if it.fixture in todo:
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
            stamp = answers.stamp_for(answers.KINDS[it.kind], base)
            if self.failed.get(it.digest) == stamp:
                return False
            if answers.stamps(db, [it.digest]).get(it.digest) == stamp:
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
            self.failed[it.digest] = answers.stamp_for(
                answers.KINDS[it.kind], answers.data_stamp(db)
            )
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


class _Stamps:
    """The current stamp of each scope, read once a minute rather than per page."""

    TTL = 60.0

    def __init__(self, session_factory):
        self.sessions = session_factory
        self.cache: dict[str, tuple[float, str]] = {}

    def forget(self) -> None:
        self.cache.clear()

    def of(self, it: Item) -> str:
        scope_key = json.dumps(it.scope, sort_keys=True)
        hit = self.cache.get(scope_key)
        if hit is None or time.monotonic() - hit[0] > self.TTL:
            with self.sessions() as db:
                answers.bind_spec(db, it.scope)
                hit = (time.monotonic(), answers.data_stamp(db))
            self.cache[scope_key] = hit
        return answers.stamp_for(answers.KINDS[it.kind], hit[1])


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
    "team.page": "багийн хуудас",
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
