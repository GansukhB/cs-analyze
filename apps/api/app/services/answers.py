"""Stored answers: every analytic page answers at once (docs/adr/0014).

A page that computes from the parsed data (a Game Plan tab, a Map's Playbook,
the overview, the team page, ...) registers its computation here as a *kind*
and asks :func:`serve` for its answer. The answer is kept in `stored_answers`
under the page's key, with no expiry, beside the data stamp it was computed at:

* the stamp still current: the stored answer, fresh;
* the stamp moved (a parse of one of *its* Teams, a Review of its Matches
  rebuilt, a new result): the stored answer all the same, marked stale and
  *wanted*, so the worker computes it before anything else
  (`app/services/warmer.py`), and the page fetches it again;
* nothing stored yet: computed here, inside the request, once.

A stamp has two parts (docs/adr/0015). The *fresh* part is what the answer
reads of its own Teams and Matches (the kind's ``deps``) and what every answer
reads (the Ratings, declared roles, the Review model, the Active Duty Maps);
only it decides fresh or stale. The *pool* part is where the Pools stood (every
parse anywhere moves it): when only that moved, the answer is still fresh, and
the warm-up computes it again last, oldest first.

The worker's warm-up computes every page Staff are likely to open (each my
team's pages and its Game Plan against every Team with three parsed Maps) after
each change, so the third case is rare. The response says which it was in
``X-Answer`` (``fresh`` or ``stale``) and ``X-Answer-At``.

A kind that also shows what Staff edit by hand (the jobs running, the practice
hours, the next Upcoming match) keeps those out of its stored answer: its
``live`` hook puts them in on every read, so an edit never waits on a refresh.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from redis.exceptions import RedisError
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.orm import Session

from app.cache import get_cache
from app.models import Match, MatchMap, MatchMapReview, MatchVeto, StoredAnswer
from app.models.base import utcnow
from app.services import dbctx, scope

logger = logging.getLogger(__name__)

WAKE = "answers:wake"
REPLAN = "answers:replan"
FRESH, STALE = "fresh", "stale"
# Pages nobody opened in this long, and that the warm-up does not plan, go.
FORGET_DAYS = 45
# A read is counted (``hits``, ``last_hit_at``) at most this often per answer:
# the warm-up only needs to know what was opened lately, not every time.
HIT_EVERY = timedelta(minutes=5)


@dataclass(frozen=True)
class Kind:
    name: str
    version: int
    compute: Callable[[Session, dict], dict]
    live: Callable[[Session, dict, dict, int | None], dict] | None = None
    # Reads a window that ends today (30 days, this quarter): the day joins its stamp.
    daily: bool = False
    # What of the data it reads, from its parameters alone: ``t:<team id>`` (a
    # Team's Match Maps, Matches, Vetoes and Reviews) and ``m:<match id>`` (one
    # Match's). None: everything, so any change makes it stale.
    deps: Callable[[dict], list[str]] | None = None


KINDS: dict[str, Kind] = {}


def kind(
    name: str,
    version: int,
    *,
    live: Callable[[Session, dict, dict, int | None], dict] | None = None,
    daily: bool = False,
    deps: Callable[[dict], list[str]] | None = None,
):
    """Register ``compute(db, params) -> dict`` as the kind ``name``.

    Bump ``version`` whenever what the page says, or its shape, changes: an
    answer of another version is never served, stale or not."""

    def register(compute: Callable[[Session, dict], dict]):
        KINDS[name] = Kind(name, version, compute, live, daily, deps)
        return compute

    return register


def teams(*names: str) -> Callable[[dict], list[str]]:
    """``deps`` for a kind that reads the Teams named by these parameters."""

    def deps(params: dict) -> list[str]:
        return [f"t:{params[n]}" for n in names if params.get(n)]

    return deps


def match(name: str = "match") -> Callable[[dict], list[str]]:
    """``deps`` for a kind that reads one Match (its Maps and their Reviews)."""

    def deps(params: dict) -> list[str]:
        return [f"m:{params[name]}"] if params.get(name) else []

    return deps


# ------------------------------------------------------------------ keys ---
def scope_part(db: Session) -> str:
    """What the session's scope adds to a key. Workspaces with no official
    uploads see what everyone sees and share it; Scrims are a Workspace's own."""
    s = scope.current(db)
    if s is None:
        return ":all"
    part = scope.cache_part(db)
    if s.scrims and ":ws" not in part:
        part = f":ws{s.workspace_id}{part}"
    return part


def scope_spec(db: Session) -> dict:
    """The scope to bind to compute it again: the reader's, even when the key is
    everyone's (a page that then shows the Workspace's Scrims needs it)."""
    s = scope.current(db)
    if s is None:
        return {"all": True}
    return {"ws": s.workspace_id, "scrims": s.scrims}


def bind_spec(db: Session, spec: dict) -> None:
    if spec.get("all"):
        db.info.pop(scope.KEY, None)
    else:
        scope.bind(db, spec.get("ws"), scrims=bool(spec.get("scrims")))


def _value(v) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, separators=(",", ":"))
    return str(v)


def key_of(name: str, params: dict, part: str) -> str:
    k = KINDS[name]
    args = ":".join(f"{p}={_value(v)}" for p, v in sorted(params.items()) if v not in (None, ""))
    return f"{name}:v{k.version}:{args}{part}"


def hash_of(key: str) -> str:
    return hashlib.sha1(key.encode()).hexdigest()


# ----------------------------------------------------------------- stamp ---
# Reading the stamps costs a handful of grouped counts (the Ratings' over every
# series, each Team's Match Maps): each process keeps them this long per scope,
# so a page's read is one row's lookup. A parse is seen a few seconds late,
# which a page cannot tell.
STAMP_SECONDS = 5.0
POOL_SEP = "~"


@dataclass
class _State:
    """Where the data stood for one scope, read at ``at``."""

    at: float
    glob: str  # what every answer reads
    pool: str  # where the Pools stood
    whole: str  # everything: the stamp of a kind with no ``deps``
    teams: dict[int, str] | None = None
    team_changed: dict[int, datetime] | None = None
    matches: dict[int, str] | None = None
    match_changed: dict[int, datetime] | None = None


_states: dict[object, _State] = {}
_states_lock = threading.Lock()


def _short(value: object) -> str:
    return hashlib.sha1(repr(value).encode()).hexdigest()[:12]


def _state(db: Session) -> _State:
    where = scope.current(db)
    now = time.monotonic()
    with _states_lock:
        hit = _states.get(where)
    if hit is not None and now - hit.at < STAMP_SECONDS:
        return hit
    from app.services import map_pool, pool_cache, rating, review, review_pool, roles

    # Read past the session's memo, and leave nothing in it: a warm-up session
    # lives for a whole fixture, and the Review stamp it remembered would never move.
    kept = db.info.pop(dbctx.MEMO, None)
    try:
        with dbctx.using(db):
            said = sorted(roles.declared().items())
            glob = _short((rating.stamp(), said, review.version(), tuple(map_pool.active_duty())))
            pool = f"{pool_cache.parse_stamp()}-{review_pool.stamp()}"
    finally:
        db.info.pop(dbctx.MEMO, None)
        if kept is not None:
            db.info[dbctx.MEMO] = kept
    n, last = db.execute(select(func.count(Match.id), func.max(Match.id))).one()
    vetoes = db.scalar(select(func.count(MatchVeto.id)))
    found = _State(now, glob, pool, f"{pool}-m{n}.{last or 0}.{vetoes}")
    with _states_lock:
        _states[where] = found
    return found


def _ts(value: datetime | None) -> int:
    # To the microsecond: two writes inside one second are two changes.
    return int(value.timestamp() * 1_000_000) if value else 0


def _later(a: datetime | None, b: datetime | None) -> datetime | None:
    return max((x for x in (a, b) if x is not None), default=None)


def _team_table(db: Session) -> tuple[dict[int, str], dict[int, datetime]]:
    """Each Team's stamp (its parsed Match Maps, Matches, Vetoes and Reviews at the
    current Review version, as this scope sees them) and when it last changed."""
    from app.services import review

    parts: dict[int, dict] = {}

    def row(team: int) -> dict:
        return parts.setdefault(team, {"maps": 0, "parsed": None, "matches": 0, "last": 0,
                                       "vetoes": 0, "reviews": 0, "reviewed": None,
                                       "edited": None})  # fmt: skip

    version = review.version()
    for column in (MatchMap.team1_id, MatchMap.team2_id):
        for team, n, last, edited in db.execute(
            select(column, func.count(MatchMap.parsed_at), func.max(MatchMap.parsed_at),
                   func.max(MatchMap.updated_at))
            .where(column.is_not(None))
            .group_by(column)
        ):  # fmt: skip
            r = row(team)
            r["maps"] += n
            r["parsed"] = _later(r["parsed"], last)
            r["edited"] = _later(r["edited"], edited)
        for team, n, last in db.execute(
            select(column, func.count(MatchMapReview.id), func.max(MatchMapReview.updated_at))
            .join(MatchMap, MatchMap.id == MatchMapReview.match_map_id)
            .where(MatchMapReview.version == version, column.is_not(None))
            .group_by(column)
        ):
            r = row(team)
            r["reviews"] += n
            r["reviewed"] = _later(r["reviewed"], last)
    for column in (Match.team1_id, Match.team2_id):
        for team, n, last, edited in db.execute(
            select(column, func.count(Match.id), func.max(Match.id), func.max(Match.updated_at))
            .where(column.is_not(None))
            .group_by(column)
        ):
            r = row(team)
            r["matches"] += n
            r["last"] = max(r["last"], last or 0)
            r["edited"] = _later(r["edited"], edited)
        for team, n in db.execute(
            select(column, func.count(MatchVeto.id))
            .join(Match, Match.id == MatchVeto.match_id)
            .where(column.is_not(None))
            .group_by(column)
        ):
            row(team)["vetoes"] += n
    out, changed = {}, {}
    for team, r in parts.items():
        times = ".".join(str(_ts(r[k])) for k in ("parsed", "reviewed", "edited"))
        out[team] = f"{r['maps']}.{r['matches']}.{r['last']}.{r['vetoes']}.{r['reviews']}.{times}"
        when = _later(r["parsed"], r["reviewed"])
        if when is not None:
            changed[team] = when
    return out, changed


def _match_table(db: Session) -> tuple[dict[int, str], dict[int, datetime]]:
    """Each Match's stamp (its parsed Maps and their Reviews) and when it last changed."""
    from app.services import review

    maps = {
        m: (n, last, edited)
        for m, n, last, edited in db.execute(
            select(MatchMap.match_id, func.count(MatchMap.parsed_at),
                   func.max(MatchMap.parsed_at), func.max(MatchMap.updated_at))
            .group_by(MatchMap.match_id)
        )
    }  # fmt: skip
    edits = dict(db.execute(select(Match.id, Match.updated_at)).all())
    reviews = {
        m: (n, last)
        for m, n, last in db.execute(
            select(MatchMap.match_id, func.count(MatchMapReview.id),
                   func.max(MatchMapReview.updated_at))
            .join(MatchMap, MatchMap.id == MatchMapReview.match_map_id)
            .where(MatchMapReview.version == review.version())
            .group_by(MatchMap.match_id)
        )
    }  # fmt: skip
    out, changed = {}, {}
    for m in set(maps) | set(reviews) | set(edits):
        n, parsed, edited = maps.get(m, (0, None, None))
        r, reviewed = reviews.get(m, (0, None))
        edited = _later(edited, edits.get(m))
        out[m] = f"{n}.{_ts(parsed)}.{r}.{_ts(reviewed)}.{_ts(edited)}"
        when = _later(parsed, reviewed)
        if when is not None:
            changed[m] = when
    return out, changed


def _tables(db: Session, st: _State) -> _State:
    if st.teams is None:
        st.teams, st.team_changed = _team_table(db)
    if st.matches is None:
        st.matches, st.match_changed = _match_table(db)
    return st


def _dep(st: _State, token: str) -> tuple[str, datetime | None]:
    what, _, ident = token.partition(":")
    try:
        key = int(ident)
    except ValueError:
        return "?", None
    if what == "t":
        return st.teams.get(key, "0"), st.team_changed.get(key)
    if what == "m":
        return st.matches.get(key, "0"), st.match_changed.get(key)
    return "?", None


def stamp(db: Session, name: str, params: dict) -> str:
    """The current stamp of kind ``name``'s answer to ``params``, read under the
    session's scope: ``<fresh>~<pool>``."""
    k = KINDS[name]
    st = _state(db)
    if k.deps is None:
        fresh = f"{st.glob}.{st.whole}"
    else:
        st = _tables(db, st)
        tokens = sorted(set(k.deps(params)))
        fresh = f"{st.glob}.{_short([(t, _dep(st, t)[0]) for t in tokens])}"
    if k.daily:
        fresh = f"{fresh}-d{datetime.now(UTC):%Y%m%d}"
    return f"{fresh}{POOL_SEP}{st.pool}"


def changed_at(db: Session, name: str, params: dict) -> datetime | None:
    """When what the answer reads last changed: the warm-up computes the latest first."""
    k = KINDS[name]
    if k.deps is None:
        return None
    st = _tables(db, _state(db))
    return max((w for t in k.deps(params) if (w := _dep(st, t)[1])), default=None)


def fresh_part(stamp_: str | None) -> str:
    return (stamp_ or "").split(POOL_SEP, 1)[0]


def pool_part(stamp_: str | None) -> str:
    head, sep, tail = (stamp_ or "").partition(POOL_SEP)
    return tail if sep else ""


def data_stamp(db: Session) -> str:
    """Moves with anything any page reads, here or anywhere: what a session's memo
    (a fixture's Report) must be read again after."""
    st = _state(db)
    return f"{st.glob}.{st.whole}"


def is_fresh(stored: str | None, current: str) -> bool:
    """Fresh while what the answer reads of its own Teams and Matches has not moved."""
    return stored is not None and POOL_SEP in stored and fresh_part(stored) == fresh_part(current)


def forget_stamps() -> None:
    """Read the stamps again at the next call (tests, and after a write here)."""
    with _states_lock:
        _states.clear()


# ----------------------------------------------------------------- serve ---
@dataclass
class Answer:
    data: dict
    state: str
    computed_at: datetime
    stamp: str
    computed: bool = False  # in this call, rather than read


def _unpack(payload: bytes) -> dict:
    return json.loads(gzip.decompress(payload))


def _writer(db: Session) -> Session:
    # Its own session, so a read never commits what the request has pending.
    return Session(bind=db.get_bind())


def serve(
    db: Session,
    name: str,
    params: dict,
    *,
    response=None,
    workspace_id: int | None = None,
    fresh: bool = False,
) -> dict:
    """The page's answer: stored (fresh or stale), else computed now and stored.

    ``workspace_id`` is the reader's, for the kind's ``live`` parts. ``fresh``
    never answers stale (a Briefing freezes what it was shown, so it must be
    current)."""
    answer = lookup(db, name, params, fresh=fresh)
    k = KINDS[name]
    data = k.live(db, params, answer.data, workspace_id) if k.live else answer.data
    mark(response, answer)
    return data


def mark(response, answer: Answer) -> None:
    """Say on the response whether the answer is current, and when it was computed."""
    if response is not None:
        response.headers["X-Answer"] = answer.state
        response.headers["X-Answer-At"] = answer.computed_at.isoformat() + "Z"


def worst(*found: Answer) -> Answer:
    """Of answers a page puts together, the one to say on the response: stale if
    any is, and the oldest."""
    stale = [a for a in found if a.state == STALE]
    return min(stale or list(found), key=lambda a: a.computed_at)


def lookup(db: Session, name: str, params: dict, *, fresh: bool = False) -> Answer:
    part = scope_part(db)
    key = key_of(name, params, part)
    digest = hash_of(key)
    current = stamp(db, name, params)
    row = db.execute(
        select(
            StoredAnswer.stamp,
            StoredAnswer.payload,
            StoredAnswer.computed_at,
            StoredAnswer.last_hit_at,
            StoredAnswer.wanted_at,
        ).where(StoredAnswer.key_hash == digest)
    ).first()
    if row is not None and (is_fresh(row.stamp, current) or not fresh):
        state = FRESH if is_fresh(row.stamp, current) else STALE
        try:
            data = _unpack(row.payload)
        except (OSError, ValueError):
            logger.warning("stored answer %s is unreadable; computing it", key)
        else:
            want = state == STALE and row.wanted_at is None
            seen = row.last_hit_at is not None and utcnow() - row.last_hit_at < HIT_EVERY
            if want or not seen:
                _hit(db, digest, wanted=want)
            return Answer(data, state, row.computed_at, row.stamp)
    data, at = compute_and_store(db, name, params, key=key, stamp=current)
    return Answer(data, FRESH, at, current, computed=True)


def compute_and_store(
    db: Session, name: str, params: dict, *, key: str, stamp: str
) -> tuple[dict, datetime]:
    """Compute one answer on ``db`` (its scope bound) and keep it under ``key``.

    ``stamp`` is read before computing: a parse that lands meanwhile leaves the
    answer stale rather than passing it off as current."""
    k = KINDS[name]
    spec = {"params": params, "scope": scope_spec(db)}
    started = time.perf_counter()
    data = k.compute(db, params)
    # Through JSON, so a computed answer and a stored one read the same.
    data = json.loads(json.dumps(data, default=str))
    ms = round((time.perf_counter() - started) * 1000)
    at = utcnow()
    store(db, key=key, kind=name, version=k.version, spec=spec, stamp=stamp, data=data, ms=ms)
    return data, at


def store(
    db: Session, *, key: str, kind: str, version: int, spec: dict, stamp: str, data: dict, ms: int
) -> None:
    """Keep an answer. One that came out as it was stored rewrites its stamp
    alone: the payload is the bulk of the row, and of the binary log."""
    raw = json.dumps(data, default=str, separators=(",", ":")).encode()
    digest = hashlib.sha1(raw).hexdigest()
    key_hash = hash_of(key)
    now = utcnow()
    with _writer(db) as w:
        same = w.scalar(
            select(StoredAnswer.id).where(
                StoredAnswer.key_hash == key_hash,
                StoredAnswer.digest == digest,
                StoredAnswer.version == version,
            )
        )
        if same is not None:
            w.execute(
                update(StoredAnswer)
                .where(StoredAnswer.id == same)
                .values(
                    stamp=stamp[:200], spec=spec, compute_ms=ms, computed_at=now, wanted_at=None
                )  # fmt: skip
            )
            w.commit()
            return
    payload = gzip.compress(raw, 6)
    values = {
        "key_hash": key_hash,
        "key": key[:512],
        "kind": kind,
        "version": version,
        "spec": spec,
        "stamp": stamp[:200],
        "payload": payload,
        "digest": digest,
        "size": len(raw),
        "compute_ms": ms,
        "computed_at": now,
        "hits": 0,
        "wanted_at": None,
    }
    changed = {c: values[c] for c in ("spec", "stamp", "payload", "digest", "size", "compute_ms")}
    changed |= {"computed_at": now, "wanted_at": None, "version": version}
    with _writer(db) as w:
        if w.get_bind().dialect.name == "mysql":
            stmt = mysql.insert(StoredAnswer).values(**values).on_duplicate_key_update(**changed)
        else:
            stmt = (
                sqlite.insert(StoredAnswer)
                .values(**values)
                .on_conflict_do_update(index_elements=["key_hash"], set_=changed)
            )
        w.execute(stmt)
        w.commit()


def _hit(db: Session, digest: str, *, wanted: bool) -> None:
    now = utcnow()
    values: dict = {"hits": StoredAnswer.hits + 1, "last_hit_at": now}
    if wanted:
        values["wanted_at"] = func.coalesce(StoredAnswer.wanted_at, now)
    try:
        with _writer(db) as w:
            w.execute(update(StoredAnswer).where(StoredAnswer.key_hash == digest).values(**values))
            w.commit()
    except Exception:  # counting a read must never fail the page
        logger.exception("could not count a read of %s", digest)
    if wanted:
        wake()


def wake() -> None:
    """Tell the worker's warm-up there is something to do now. Never raises."""
    try:
        cache = get_cache()
        cache.rpush(WAKE, "1")
        cache.ltrim(WAKE, -5, -1)
    except RedisError:
        logger.warning("could not wake the warm-up")


def replan() -> None:
    """A job ended: have the warm-up plan its round again (the job's fixture
    first) rather than finish the one it is on. Never raises."""
    try:
        get_cache().set(REPLAN, "1", ex=24 * 3600)
    except RedisError:
        logger.warning("could not ask the warm-up to plan again")
    wake()


def take_replan() -> bool:
    try:
        return bool(get_cache().delete(REPLAN))
    except RedisError:
        return False


# ---------------------------------------------------------------- upkeep ---
def prune(db: Session, keep: set[str] | None = None) -> int:
    """Drop answers no code can serve (another version, a kind gone) and, given
    the hashes the warm-up plans, those nobody has opened for :data:`FORGET_DAYS`."""
    gone = 0
    for name, version in db.execute(
        select(StoredAnswer.kind, StoredAnswer.version).distinct()
    ).all():
        k = KINDS.get(name)
        if k is None or k.version != version:
            gone += db.execute(
                delete(StoredAnswer).where(
                    StoredAnswer.kind == name, StoredAnswer.version == version
                )
            ).rowcount
    if keep is not None:
        cutoff = utcnow() - timedelta(days=FORGET_DAYS)
        old = db.scalars(
            select(StoredAnswer.key_hash).where(
                func.coalesce(StoredAnswer.last_hit_at, StoredAnswer.computed_at) < cutoff
            )
        ).all()
        drop = [h for h in old if h not in keep]
        for i in range(0, len(drop), 500):
            gone += db.execute(
                delete(StoredAnswer).where(StoredAnswer.key_hash.in_(drop[i : i + 500]))
            ).rowcount
    db.commit()
    return gone


def stored(db: Session, hashes: list[str]) -> dict[str, tuple[str, datetime]]:
    """Each stored hash's stamp and when it was computed, for the ones given."""
    out: dict[str, tuple[str, datetime]] = {}
    for i in range(0, len(hashes), 500):
        chunk = hashes[i : i + 500]
        for digest, stamp_, at in db.execute(
            select(StoredAnswer.key_hash, StoredAnswer.stamp, StoredAnswer.computed_at).where(
                StoredAnswer.key_hash.in_(chunk)
            )
        ):
            out[digest] = (stamp_, at)
    return out


def restamp(db: Session, digest: str, stamp_: str) -> None:
    """Give a stored answer a stamp without computing it (a legacy one adopted)."""
    db.execute(
        update(StoredAnswer).where(StoredAnswer.key_hash == digest).values(stamp=stamp_[:200])
    )


def stamps(db: Session, hashes: list[str]) -> dict[str, str]:
    """Each stored hash's stamp, for the ones given."""
    out: dict[str, str] = {}
    for i in range(0, len(hashes), 500):
        chunk = hashes[i : i + 500]
        out.update(
            db.execute(
                select(StoredAnswer.key_hash, StoredAnswer.stamp).where(
                    StoredAnswer.key_hash.in_(chunk)
                )
            ).all()
        )
    return out
