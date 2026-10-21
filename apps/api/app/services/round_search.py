"""The Round search (docs/plans/09 VIZ-7): "find me Rounds like this".

Each stored Replay Round carries, second by second, how many of each Side's
living Players stood in each Callout (``replay_rounds.tokens``, ggViz's state
tokens). A search names a Map, the Side the conditions are about and,
optionally, its Team and its buy; each condition is a Callout, a fewest (and
a most) number of that Side's Players there, and a window of seconds after
freeze end. A Round matches when every condition holds at some second of its
window, give or take :data:`SLACK` (a token jumps at a Callout's border).
"""

from __future__ import annotations

import gzip
import json

from sqlalchemy import select

from app.models import GameMap, Match, MatchMap, ReplayRound, Round, Team
from app.services import scope
from app.services.dbctx import db

SLACK = 2  # seconds either side of a window
MAX_RESULTS = 60


def places(map_name: str) -> list[str]:
    """The Callouts the Map's Rounds have tokens for, the most used first."""
    seen: dict[str, int] = {}
    for blob in _blobs(map_name, limit=40):
        t = json.loads(gzip.decompress(blob))
        for side in ("ct", "t"):
            for _s, idx, n in t[side]:
                name = t["places"][idx]
                seen[name] = seen.get(name, 0) + n
    return [name for name, _n in sorted(seen.items(), key=lambda kv: -kv[1])]


def _blobs(map_name: str, limit: int | None = None):
    query = (
        select(ReplayRound.tokens)
        .join(MatchMap, MatchMap.id == ReplayRound.match_map_id)
        .join(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(GameMap.name == map_name, ReplayRound.tokens.is_not(None))
    )
    if limit:
        query = query.limit(limit)
    return db().scalars(query)


def _holds(t: dict, side: str, cond: dict) -> bool:
    name, fewest, most = cond["place"], cond.get("min", 1), cond.get("max")
    lo, hi = int(cond.get("start", 0)) - SLACK, int(cond.get("end", 180)) + SLACK
    try:
        idx = t["places"].index(name)
    except ValueError:
        return fewest <= 0
    counts: dict[int, int] = {}
    for s, i, n in t[side]:
        if i == idx and lo <= s <= hi:
            counts[s] = n
    for s in range(max(0, lo), hi + 1):
        n = counts.get(s, 0)
        if n >= fewest and (most is None or n <= most):
            return True
    return False


def search(
    map_name: str,
    side: str,
    conditions: list[dict],
    team_id: int | None = None,
    buy: str | None = None,
) -> dict:
    """Every Round matching all ``conditions`` for ``side``, newest first."""
    session = db()
    scope.allow_scrims(session)
    team_col = Round.ct_team_id if side == "ct" else Round.t_team_id
    buy_col = Round.ct_buy if side == "ct" else Round.t_buy
    query = (
        select(ReplayRound.tokens, Round, MatchMap.match_id, MatchMap.map_number, Match.played_at)
        .join(MatchMap, MatchMap.id == ReplayRound.match_map_id)
        .join(GameMap, GameMap.id == MatchMap.game_map_id)
        .join(Match, Match.id == MatchMap.match_id)
        .join(
            Round,
            (Round.match_map_id == ReplayRound.match_map_id) & (Round.number == ReplayRound.number),
        )
        .where(GameMap.name == map_name, ReplayRound.tokens.is_not(None))
    )
    if team_id:
        query = query.where(team_col == team_id)
    if buy == "full":
        query = query.where(buy_col == "full")
    elif buy == "light":
        query = query.where(buy_col.in_(("eco", "force", "pistol")))
    looked = 0
    found = []
    for blob, rnd, match_id, map_number, played in session.execute(query):
        looked += 1
        t = json.loads(gzip.decompress(blob))
        if all(_holds(t, side, c) for c in conditions):
            found.append((played, rnd, match_id, map_number))
    found.sort(key=lambda f: f[0] or 0, reverse=True)
    names = dict(session.execute(select(Team.id, Team.name)).all())
    rows = []
    for played, rnd, match_id, map_number in found[:MAX_RESULTS]:
        team = rnd.ct_team_id if side == "ct" else rnd.t_team_id
        rows.append(
            {
                "match": match_id,
                "map": map_number,
                "round": rnd.number,
                "team": names.get(team, ""),
                "won": rnd.winner_team_id == team if team else None,
                "buy": (rnd.ct_buy if side == "ct" else rnd.t_buy) or "",
                "played_at": played.date().isoformat() if played else None,
            }
        )
    won = sum(1 for r in found if r[1].winner_team_id == (r[1].ct_team_id if side == "ct"
                                                           else r[1].t_team_id))  # fmt: skip
    return {"looked": looked, "found": len(found), "won": won, "rounds": rows}
