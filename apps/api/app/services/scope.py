"""What a session may see of the private Matches (docs/adr/0010, 0011; DATA-1, WS-2).

HLTV's Matches are everyone's. A Match a Workspace uploaded is seen only inside
that Workspace, where an official one counts like an HLTV Match; a Scrim is seen
only where a page asks for it (its own Review and Replay), never in Own form,
habits, Set plays, Ratings or the Pool.

One filter does it for every query: a session carries its :class:`Scope` in
``session.info`` and :func:`_filter` adds the criteria to every ORM SELECT that
touches ``Match`` or ``MatchMap`` (rows below a Match Map, such as Rounds or
kills, are reached through the Match Maps those queries pick). A request binds
the signed-in User's Workspace (``deps.get_current_user``). A session with no
scope (the worker's ingest and Review rebuilds, the CLI) sees every row; the
worker binds :data:`PUBLIC` where it computes a Pool other processes will read.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from sqlalchemy import and_, event, exists, false, or_, select, true
from sqlalchemy.orm import Session, with_loader_criteria

from app.models import Match, MatchKind, MatchMap

KEY = "cs_scope"
_matches = Match.__table__  # Core, so the criteria never filter their own subquery


@dataclass(frozen=True)
class Scope:
    workspace_id: int | None  # None: only what everyone sees
    scrims: bool = False


PUBLIC = Scope(None)


def bind(session: Session, workspace_id: int | None, *, scrims: bool = False) -> None:
    session.info[KEY] = Scope(workspace_id, scrims)


def allow_scrims(session: Session) -> None:
    """Let this session's pages show the Workspace's Scrims (a Review, a Replay)."""
    found = current(session)
    if found is not None:
        session.info[KEY] = replace(found, scrims=True)


def current(session: Session) -> Scope | None:
    return session.info.get(KEY)


def _hidden(s: Scope):
    """Which Match rows this scope must not see, as a Core condition on ``matches``."""
    others = _matches.c.workspace_id.is_not(None)
    if s.workspace_id is not None:
        others = and_(others, _matches.c.workspace_id != s.workspace_id)
    scrim = false() if s.scrims else _matches.c.kind == MatchKind.SCRIM
    return or_(others, scrim)


def _visible_match(s: Scope):
    mine = Match.workspace_id.is_(None)
    if s.workspace_id is not None:
        mine = or_(mine, Match.workspace_id == s.workspace_id)
    kind = true() if s.scrims else Match.kind != MatchKind.SCRIM
    return and_(mine, kind)


@event.listens_for(Session, "do_orm_execute")
def _filter(state) -> None:
    s = state.session.info.get(KEY)
    if (
        s is None
        or not state.is_select
        or state.is_column_load
        or state.is_relationship_load
        or state.execution_options.get("all_matches", False)
    ):
        return
    hidden = select(_matches.c.id).where(_hidden(s))
    state.statement = state.statement.options(
        with_loader_criteria(Match, _visible_match(s), include_aliases=True),
        with_loader_criteria(MatchMap, MatchMap.match_id.not_in(hidden), include_aliases=True),
    )


def cache_part(session: Session) -> str:
    """What a cache key adds for this scope: nothing while it sees only what
    everyone sees, so Workspaces with no official uploads share one cache."""
    s = current(session)
    if s is None:
        return ""
    # A page that shows Scrims never shares a cache with one that must not.
    suffix = ":scrims" if s.scrims else ""
    if s.workspace_id is None:
        return suffix
    own = session.execute(
        select(
            exists().where(
                _matches.c.workspace_id == s.workspace_id,
                _matches.c.kind != MatchKind.SCRIM,
            )
        )
    ).scalar()
    return (f":ws{s.workspace_id}" if own else "") + suffix
