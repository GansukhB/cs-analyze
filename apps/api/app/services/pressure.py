"""How steady a Player is, and how they do when a Round matters most
(docs/plans/04 PL-10).

From the stored Reviews (``review_pool.data()``): each Player's Swing per Round
on each Match Map, and Round by Round. Consistency is the spread of their per-Map
Swing per Round (fewer than :data:`MIN_MAPS` Maps says nothing), placed among
every reviewed Player's. Pressure Rounds are the pistols, a match point in
regulation (either Team on 12), and a close finish (Round 19 on, the Teams within
one); a Player's Swing per Round in each is set beside every Player's.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from sqlalchemy import select

from app.models import Round
from app.services import review_pool
from app.services.analysis_store import PISTOL_ROUNDS
from app.services.dbctx import db

MIN_MAPS = 5
REGULATION = 24
WIN_AT = 13
CLOSE_FROM = 19
KINDS = {
    "pistol": "Pistol раунд",
    "match_point": "Match point",
    "close": "Ойр төгсгөл (19+, ±1)",
    "other": "Бусад раунд",
}
_CACHE: dict[str, dict] = {}


def _kind(n: int, mine: int, theirs: int) -> str:
    if n in PISTOL_ROUNDS:
        return "pistol"
    if n <= REGULATION and WIN_AT - 1 in (mine, theirs):
        return "match_point"
    if n >= CLOSE_FROM and abs(mine - theirs) <= 1:
        return "close"
    return "other"


def _scores(mm_ids: set[int]) -> dict[tuple[int, int], dict[int, tuple[int, int]]]:
    """``{(Match Map, Round): {team: (its Rounds, the other's) before it}}``."""
    rows = db().execute(
        select(Round.match_map_id, Round.number, Round.winner_team_id, Round.ct_team_id,
               Round.t_team_id)
        .where(Round.match_map_id.in_(mm_ids))
        .order_by(Round.match_map_id, Round.number)
    ).all()  # fmt: skip
    out: dict[tuple[int, int], dict[int, tuple[int, int]]] = {}
    won: dict[int, dict[int, int]] = defaultdict(dict)
    for mm, n, winner, ct, t in rows:
        tally = won[mm]
        out[(mm, n)] = {
            team: (tally.get(team, 0), tally.get(other, 0))
            for team, other in ((ct, t), (t, ct))
            if team
        }  # fmt: skip
        if winner:
            tally[winner] = tally.get(winner, 0) + 1
    return out


def _everyone() -> dict:
    """Per Player: Swing by kind of Round and per Map; and the Pool's per kind.
    Cut once per Review stamp."""
    data = review_pool.data()
    if data.stamp in _CACHE:
        return _CACHE[data.stamp]
    scores = _scores({t.mm for t in data.tallies})
    by_kind: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    by_map: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for t in data.tallies:
        for sid, rows in t.players.items():
            for n, swing in rows:
                mine, theirs = scores.get((t.mm, n), {}).get(t.team, (0, 0))
                by_kind[sid][_kind(n, mine, theirs)].append(swing)
                by_map[sid][t.mm].append(swing)
    pool = {}
    for kind in KINDS:
        values = [s for p in by_kind.values() for s in p.get(kind, [])]
        pool[kind] = sum(values) / len(values) if values else None
    spreads = {}
    for sid, maps in by_map.items():
        means = [sum(v) / len(v) for v in maps.values() if v]
        if len(means) >= MIN_MAPS:
            spreads[sid] = statistics.pstdev(means)
    found = {"by_kind": by_kind, "pool": pool, "spreads": spreads, "by_map": by_map}
    _CACHE.clear()
    _CACHE[data.stamp] = found
    return found


def player(steamid: int) -> dict:
    sid = str(steamid)
    found = _everyone()
    mine = found["by_kind"].get(sid) or {}
    rows = []
    for kind, label in KINDS.items():
        values = mine.get(kind) or []
        rows.append({
            "key": kind, "label": label, "rounds": len(values),
            "per_round": round(sum(values) / len(values), 4) if values else None,
            "pool_per_round": round(found["pool"][kind], 4) if found["pool"][kind] is not None
            else None,
        })  # fmt: skip
    spread = found["spreads"].get(sid)
    consistency = None
    if spread is not None:
        others = list(found["spreads"].values())
        below = sum(1 for o in others if o < spread)
        consistency = {
            "maps": len(found["by_map"][sid]),
            "sd": round(spread, 4),
            # High: their Maps differ more than most Players'.
            "pct": round(100 * below / len(others)),
            "players": len(others),
        }
    return {"pressure": rows, "consistency": consistency}
