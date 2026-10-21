"""Staff's drawn Review notes on a Map, for a Briefing (docs/plans/09 VIZ-8).

A note drawn on the Replay of a Match Map the Team played is scouting material:
the Briefing for a Fixture on that Map can carry it, frozen with the rest, so the
Players see the arrow on the radar beside the line it explains.
"""

from __future__ import annotations

from sqlalchemy import or_, select

from app.models import GameMap, Match, MatchMap, NoteKind, ReviewNote, Team
from app.services import scope
from app.services.dbctx import db

LISTED = 12
PER_MAP = 6


def _row(note: ReviewNote, mm: MatchMap, match: Match, names: dict[int, str]) -> dict:
    teams = " vs ".join(names.get(t, "?") for t in (match.team1_id, match.team2_id) if t)
    return {
        "id": note.id,
        "text": note.text,
        "round": note.round,
        "t": note.t,
        "match_id": mm.match_id,
        "map_number": mm.map_number,
        "played_at": match.played_at.date().isoformat() if match.played_at else None,
        "teams": teams,
        "shapes": list(note.drawing or []),
    }


def _query(workspace_id: int, map_name: str):
    return (
        select(ReviewNote, MatchMap, Match)
        .join(MatchMap, MatchMap.id == ReviewNote.match_map_id)
        .join(Match, Match.id == MatchMap.match_id)
        .join(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(ReviewNote.workspace_id == workspace_id, ReviewNote.kind == NoteKind.NOTE,
               GameMap.name == map_name)
        .order_by(Match.played_at.desc(), ReviewNote.id.desc())
    )  # fmt: skip


def _names(rows) -> dict[int, str]:
    ids = {t for _n, _mm, m in rows for t in (m.team1_id, m.team2_id) if t}
    return dict(db().execute(select(Team.id, Team.name).where(Team.id.in_(ids))).all())


def on_map(workspace_id: int, team_id: int, map_name: str) -> list[dict]:
    """The Workspace's drawn notes on Match Maps of ``map_name`` that ``team_id``
    played, newest first."""
    session = db()
    scope.allow_scrims(session)
    query = _query(workspace_id, map_name).where(
        or_(Match.team1_id == team_id, Match.team2_id == team_id)
    )
    # A JSON column keeps an empty drawing as JSON null, which IS NOT NULL misses.
    rows = [r for r in session.execute(query).all() if r[0].drawing][:LISTED]
    names = _names(rows)
    return [_row(n, mm, m, names) for n, mm, m in rows]


def freeze(workspace_id: int, map_name: str, ids: list[int]) -> list[dict]:
    """The picked drawn notes as the Briefing keeps them; ValueError for one that
    is not this Workspace's, not on this Map, or has no drawing."""
    if not ids:
        return []
    session = db()
    scope.allow_scrims(session)
    wanted = list(dict.fromkeys(ids))[:PER_MAP]
    rows = session.execute(_query(workspace_id, map_name).where(ReviewNote.id.in_(wanted))).all()
    found = {n.id: (n, mm, m) for n, mm, m in rows if n.drawing}
    missing = [i for i in wanted if i not in found]
    if missing:
        raise ValueError(f"Note {missing[0]} is not a drawing on this Map")
    names = _names(list(found.values()))
    return [_row(*found[i], names) for i in wanted]
