"""The veto lab (docs/plans/06 GP-10): a Fixture's veto played step by step.

Each Map's chance starts where the Forecast puts it. The Forecast keeps every
Map at the Rating's chance (map offsets made its walk-forward check worse), so
the lab shows what Staff can judge by: each side's strength on the Map (its
share of Rounds won, pulled toward its own), how often it played it, and our
Scrims there (docs/adr/0010: our own development, read for us only), and lets
Staff move a Map's chance by hand. The veto is then played from where it
stands (:func:`forecast.veto_from`): our chance now, every option at the next
step valued, and the line from there.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from app.models import GameMap, Match, MatchKind, MatchMap, Round, Team
from app.services import forecast, map_pool
from app.services.dbctx import db

MAX_ADJUST = 25.0  # points either way


def scrim_shares(team_id: int, workspace_id: int) -> dict[str, dict]:
    """Our Rounds won in our Scrims, Map by Map (the caller allows Scrims)."""
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    maps_seen: dict[str, set] = defaultdict(set)
    for name, mm, winner in db().execute(
        select(GameMap.name, MatchMap.id, Round.winner_team_id)
        .join(MatchMap, MatchMap.id == Round.match_map_id)
        .join(Match, Match.id == MatchMap.match_id)
        .join(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(
            Match.kind == MatchKind.SCRIM,
            Match.workspace_id == workspace_id,
            (Round.ct_team_id == team_id) | (Round.t_team_id == team_id),
        )
    ):
        tally[name][0] += 1
        tally[name][1] += int(winner == team_id)
        maps_seen[name].add(mm)
    return {
        name: {"maps": len(maps_seen[name]), "rounds": n, "share": round(100 * won / n, 1)}
        for name, (n, won) in tally.items()
        if n
    }


def lab(
    my_team: Team,
    opponent: Team,
    workspace_id: int,
    fmt: str,
    we_start: bool,
    done: list[str],
    adjust: dict[str, float],
) -> dict:
    built = forecast.build(my_team, opponent)
    pool = list(map_pool.active_duty())
    mine = {r["map"]: r for r in map_pool.team_pool(my_team)["rows"]}
    theirs = {r["map"]: r for r in map_pool.team_pool(opponent)["rows"]}
    scrims = scrim_shares(my_team.id, workspace_id)
    base = {m["map"]: m["p"] for m in built["maps"]}
    rows, p = [], {}
    for m in pool:
        start = base.get(m)
        moved = max(-MAX_ADJUST, min(MAX_ADJUST, float(adjust.get(m, 0.0))))
        if start is not None:
            p[m] = min(0.97, max(0.03, start + moved / 100.0))
        rows.append(
            {
                "map": m,
                "base": start,
                "adjust": moved,
                "p": round(p[m], 4) if m in p else None,
                "mine": _side(mine.get(m)),
                "theirs": _side(theirs.get(m)),
                "scrims": scrims.get(m),
            }
        )
    out = {"maps": rows, "limits": built["limits"], "veto": None}
    if len(p) == len(pool) and fmt in forecast.FORMATS:
        share = forecast.play_share(forecast.played(opponent.id), pool)
        out["veto"] = forecast.veto_from(p, share, fmt, we_start, done)
    return out


def _side(row: dict | None) -> dict | None:
    if not row:
        return None
    return {k: row[k] for k in ("maps", "won", "shrunk", "recent", "status")}
