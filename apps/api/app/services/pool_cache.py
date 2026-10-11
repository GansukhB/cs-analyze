"""The Pool's numbers, computed once per parse and shared by every process.

A Game Plan judges both Teams against the Pool (CONTEXT.md): every Player's role
signals (`roles.pool_signals`, which the role baseline and cohorts are cut from)
and every Team's metrics (`gameplan.metric_pool`). Neither depends on the
fixture, yet each tab of each Game Plan computed them again: over 355 Match Maps
the role signals alone took most of a minute, and the heavier tabs ran past
Cloudflare's 100 s.

So each is kept in Redis (DB 2) under a key naming what it was computed from. A
process that finds it missing computes it under a lock while the others wait for
that result instead of racing it, and the worker warms both after every Match a
Scout parses (`gameplan.warm_pool`). A request never answers from an older Pool:
when the data moved, it waits for the new one.
"""

import json
import logging
import time
from collections.abc import Callable

from redis.exceptions import RedisError
from sqlalchemy import func, select

from app.cache import get_cache
from app.models import MatchMap
from app.services.dbctx import db

logger = logging.getLogger(__name__)

TTL = 7 * 24 * 3600
# How long one computation may hold the lock, and so how long the others wait for
# it. Past that the holder is presumed dead and a waiter computes it itself.
LOCK_SECONDS = 3 * 60
POLL_SECONDS = 0.5


def parse_stamp() -> str:
    """Moves whenever a Match Map is parsed or parsed again."""
    count, latest = (
        db()
        .execute(
            select(func.count(MatchMap.id), func.max(MatchMap.parsed_at)).where(
                MatchMap.parsed_at.is_not(None)
            )
        )
        .one()
    )
    return f"{count}-{int(latest.timestamp()) if latest else 0}"


def remember(key: str, compute: Callable[[], object]) -> object:
    """``compute()``'s result as JSON gives it back, made once across processes.

    The value always comes back through JSON, computed here or read from Redis, so
    the caller sees one shape either way. Without Redis it is simply computed.
    """
    lock = f"{key}:lock"
    owned = False
    try:
        cache = get_cache()
        raw = cache.get(key)
        deadline = time.monotonic() + LOCK_SECONDS
        while raw is None:
            if cache.set(lock, "1", nx=True, ex=LOCK_SECONDS):
                owned = True
                # The last holder may have finished between our read and our claim.
                raw = cache.get(key)
                break
            if time.monotonic() > deadline:
                logger.warning("%s: the lock outlived its holder; computing it here", key)
                break
            time.sleep(POLL_SECONDS)
            raw = cache.get(key)
    except RedisError:
        logger.warning("Pool cache unavailable; computing %s", key)
        return json.loads(json.dumps(compute()))

    try:
        if raw is None:
            raw = json.dumps(compute())
            try:
                cache.set(key, raw, ex=TTL)
            except RedisError:
                logger.warning("could not cache %s", key)
    finally:
        if owned:
            try:
                cache.delete(lock)
            except RedisError:
                logger.warning("could not release %s", lock)
    return json.loads(raw)
