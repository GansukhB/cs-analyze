"""One heavy job at a time on the host (docs/plans/11-platform.md OPS-6).

Parsing a Demo (awpy, then the ingest) takes gigabytes; the host is shared and
small, and two at once would bring the OOM killer. Scouts, uploads and stale
re-parses run on different queues, so the worker may run them side by side:
downloading needs only the network, but the parse step takes the one permit
here first, a Redis key every process sees.

The permit expires after :data:`TTL_SECONDS` in case its holder dies, and the
worker clears it on start (``tasks._recover``), the one moment nothing can hold
it. With Redis unreachable it lets the work go ahead, like the rate limits.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from redis.exceptions import RedisError

from app.cache import get_cache

logger = logging.getLogger(__name__)

KEY = "heavy:permit"
TTL_SECONDS = 60 * 60
POLL_SECONDS = 2.0


class Cancelled(Exception):
    """The work was stopped while it waited for the permit."""


@contextmanager
def permit(
    owner: str,
    *,
    on_wait: Callable[[str], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    poll: float = POLL_SECONDS,
) -> Iterator[None]:
    """Hold the host's one heavy permit while the block runs.

    ``on_wait(holder)`` is called once if someone else holds it; ``cancelled()``
    is asked between polls, and a True raises :class:`Cancelled`."""
    token = f"{owner}|{uuid.uuid4().hex}"
    held = False
    told = False
    while True:
        try:
            cache = get_cache()
            if cache.set(KEY, token, nx=True, ex=TTL_SECONDS):
                held = True
                break
            holder = cache.get(KEY)
        except RedisError:
            logger.warning("heavy permit unavailable: going ahead without it")
            break
        if not told and on_wait is not None:
            on_wait(_owner(holder))
            told = True
        if cancelled is not None and cancelled():
            raise Cancelled
        time.sleep(poll)
    try:
        yield
    finally:
        if held:
            _release(token)


def _owner(value) -> str:
    if isinstance(value, bytes):
        value = value.decode()
    return (value or "").split("|", 1)[0]


def _release(token: str) -> None:
    try:
        cache = get_cache()
        current = cache.get(KEY)
        if isinstance(current, bytes):
            current = current.decode()
        if current == token:
            cache.delete(KEY)
    except RedisError:
        logger.warning("could not release the heavy permit; it expires on its own")


def holder() -> str | None:
    """Who holds the permit now, or None."""
    try:
        value = get_cache().get(KEY)
    except RedisError:
        return None
    return _owner(value) or None


def clear() -> None:
    """Drop the permit: only on worker start, when nothing can be holding it."""
    try:
        get_cache().delete(KEY)
    except RedisError:
        logger.warning("could not clear the heavy permit")
