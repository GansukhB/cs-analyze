"""The session the analysis services read through.

cstat's analysis modules (mapstrategy, roles, scouting, gameplan, ...) query
through Django's implicit, global connection, so their functions take teams and
maps and never a session. Ported here, they keep those signatures: the caller
binds a session for the duration of a request with :func:`using`, and the
modules fetch it with :func:`db`. It is a context variable, so concurrent
requests (and the threads FastAPI runs sync endpoints in) each see their own.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import case, func
from sqlalchemy.orm import Session

_current: ContextVar[Session | None] = ContextVar("analysis_session", default=None)


def db() -> Session:
    session = _current.get()
    if session is None:
        raise RuntimeError("no analysis session bound; wrap the call in dbctx.using(session)")
    return session


@contextmanager
def using(session: Session) -> Iterator[Session]:
    token = _current.set(session)
    try:
        yield session
    finally:
        _current.reset(token)


def memo(key, compute):
    """``compute()`` once per bound session and ``key``.

    cstat's modules ask for the same thing many times in one report (a team's
    maps in the window are fetched by the metrics, the players, the map plans
    and the map matrix alike). Cached on the session, a request pays once, and
    the next request starts clean.
    """
    store = db().info.setdefault("analysis_memo", {})
    if key not in store:
        store[key] = compute()
    return store[key]


def count_if(condition):
    """``COUNT(*) FILTER (WHERE ...)`` for MySQL, which has no FILTER clause."""
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def total(column):
    """``SUM(column)``, as 0 rather than NULL over no rows, and as an int (MySQL says DECIMAL)."""
    return func.coalesce(func.sum(column), 0)
