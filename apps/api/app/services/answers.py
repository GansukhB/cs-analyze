"""Stored answers: every analytic page answers at once (docs/adr/0014).

A page that computes from the parsed data (a Game Plan tab, a Map's Playbook,
the overview, the team page, ...) registers its computation here as a *kind*
and asks :func:`serve` for its answer. The answer is kept in `stored_answers`
under the page's key, with no expiry, beside the data stamp it was computed at:

* the stamp still current: the stored answer, fresh;
* the stamp moved (a parse, a Review rebuilt, a new result): the stored answer
  all the same, marked stale and *wanted*, so the worker computes it before
  anything else (`app/services/warmer.py`), and the page fetches it again;
* nothing stored yet: computed here, inside the request, once.

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
from app.models import Match, MatchVeto, StoredAnswer
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


KINDS: dict[str, Kind] = {}


def kind(
    name: str,
    version: int,
    *,
    live: Callable[[Session, dict, dict, int | None], dict] | None = None,
    daily: bool = False,
):
    """Register ``compute(db, params) -> dict`` as the kind ``name``.

    Bump ``version`` whenever what the page says, or its shape, changes: an
    answer of another version is never served, stale or not."""

    def register(compute: Callable[[Session, dict], dict]):
        KINDS[name] = Kind(name, version, compute, live, daily)
        return compute

    return register


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
# Reading the stamp costs a handful of counts (the Ratings' over every series):
# each process keeps it this long per scope, so a page's read is one row's lookup.
# A parse is seen a few seconds late, which a page cannot tell.
STAMP_SECONDS = 5.0
_stamps: dict[object, tuple[float, str]] = {}
_stamps_lock = threading.Lock()


def data_stamp(db: Session) -> str:
    """Moves with anything an analytic page reads: a parse, a Review rebuilt,
    a result or a standing, Staff's declared roles (the Game Plan's stamp), a
    Match stored, a Veto read. Read under the session's scope."""
    from app.services import gameplan_view

    where = scope.current(db)
    now = time.monotonic()
    with _stamps_lock:
        hit = _stamps.get(where)
    if hit is not None and now - hit[0] < STAMP_SECONDS:
        return hit[1]
    with dbctx.using(db):
        base = gameplan_view.stamp()
    n, last = db.execute(select(func.count(Match.id), func.max(Match.id))).one()
    vetoes = db.scalar(select(func.count(MatchVeto.id)))
    found = f"{base}-m{n}.{last or 0}.{vetoes}"
    with _stamps_lock:
        _stamps[where] = (now, found)
    return found


def stamp_for(k: Kind, base: str) -> str:
    return f"{base}-d{datetime.now(UTC):%Y%m%d}" if k.daily else base


# ----------------------------------------------------------------- serve ---
@dataclass
class Answer:
    data: dict
    state: str
    computed_at: datetime
    stamp: str
    computed: bool = False  # in this call, rather than read


def _pack(data: dict) -> tuple[bytes, int]:
    raw = json.dumps(data, default=str, separators=(",", ":")).encode()
    return gzip.compress(raw, 6), len(raw)


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


def lookup(db: Session, name: str, params: dict, *, fresh: bool = False) -> Answer:
    k = KINDS[name]
    part = scope_part(db)
    key = key_of(name, params, part)
    digest = hash_of(key)
    current = stamp_for(k, data_stamp(db))
    row = db.execute(
        select(
            StoredAnswer.stamp,
            StoredAnswer.payload,
            StoredAnswer.computed_at,
            StoredAnswer.last_hit_at,
            StoredAnswer.wanted_at,
        ).where(StoredAnswer.key_hash == digest)
    ).first()
    if row is not None and (row.stamp == current or not fresh):
        state = FRESH if row.stamp == current else STALE
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
    """Compute one answer on ``db`` (its scope bound) and keep it under ``key``."""
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
    payload, size = _pack(data)
    values = {
        "key_hash": hash_of(key),
        "key": key[:512],
        "kind": kind,
        "version": version,
        "spec": spec,
        "stamp": stamp[:200],
        "payload": payload,
        "size": size,
        "compute_ms": ms,
        "computed_at": utcnow(),
        "hits": 0,
        "wanted_at": None,
    }
    changed = {c: values[c] for c in ("spec", "stamp", "payload", "size", "compute_ms")}
    changed |= {"computed_at": values["computed_at"], "wanted_at": None, "version": version}
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
