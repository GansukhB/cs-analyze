"""The Game Plan's time window (docs/plans/05 TM-3): a Fixture read since a day.

Bound per request like the Lineups (``lineup.using``): when a caller of
:func:`app.services.mapstrategy.maps_in_window` gives no window of its own, the
bound one applies, so every section that reads a Team's Maps (the profile, the
players, the roles, the linchpins, the map board and plans) follows it and the
cache key carries it (:func:`cache_part`). The Pool never does: it is every Team
over everything, and its computations bind no window (``none``).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

_since: ContextVar[datetime | None] = ContextVar("gameplan_since", default=None)


def parse(text: str) -> datetime | None:
    """``YYYY-MM-DD`` (the route checks the shape), or None for no window."""
    return datetime.strptime(text, "%Y-%m-%d") if text else None


@contextmanager
def using(since: datetime | None) -> Iterator[None]:
    token = _since.set(since)
    try:
        yield
    finally:
        _since.reset(token)


def none():
    """No window, whatever the request bound: for the Pool's computations."""
    return using(None)


def since() -> datetime | None:
    return _since.get()


def cache_part() -> str:
    value = _since.get()
    return f":S{value:%Y-%m-%d}" if value else ""
