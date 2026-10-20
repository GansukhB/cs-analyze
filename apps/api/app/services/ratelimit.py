"""Counters that slow down guessing, kept in Redis (DB 2, beside the app cache).

Only failures are counted, so a User who signs in correctly never meets the
limit. Redis being down opens the gate rather than locking everyone out: nginx
has its own per-IP limit in front (ansible/templates/nginx.conf.j2).
"""

import logging

from redis.exceptions import RedisError

from app.cache import get_cache

logger = logging.getLogger(__name__)


def count(key: str) -> int:
    try:
        return int(get_cache().get(key) or 0)
    except RedisError:
        logger.warning("rate limit unavailable; letting %s through", key)
        return 0


def record(key: str, window_seconds: int) -> None:
    """One more failure under ``key``; the window starts at the first."""
    try:
        cache = get_cache()
        if cache.incr(key) == 1:
            cache.expire(key, window_seconds)
    except RedisError:
        logger.warning("rate limit unavailable; %s not counted", key)


def clear(key: str) -> None:
    try:
        get_cache().delete(key)
    except RedisError:
        pass
