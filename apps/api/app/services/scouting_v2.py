"""The v2 scouting page's own numbers about an opponent (screen 07); the rest of
the page reads the Game Plan's Playbook for the Map.

What they played and where it went (per Map: their Match Maps and record, ours,
and the Forecast's model of what they would pick and ban, since no veto history
is read: DATA-3); on one Map, where their T Rounds put the bomb by their buy, and
when. Scrims never count (docs/adr/0010): the scope hides them.

Bind a session with ``dbctx.using``.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import select

from app.models import BuyType, MatchMap, Round, Team
from app.services import forecast, map_pool, mapstrategy, mn

BUYS = (BuyType.PISTOL, BuyType.ECO, BuyType.FORCE, BuyType.FULL)
BIN = 10  # seconds per bar of the plant clock
BINS = 12


def build(mine: Team, theirs: Team, map_name: str | None) -> dict:
    their_maps = mapstrategy.maps_in_window(theirs)
    my_maps = mapstrategy.maps_in_window(mine)
    counts: Counter = Counter()
    won: Counter = Counter()
    for m in their_maps:
        name = m.game_map.name if m.game_map else "?"
        counts[name] += 1
        won[name] += 1 if m.winner_id == theirs.id else 0
    ours = Counter(m.game_map.name for m in my_maps if m.game_map)
    pool = list(map_pool.active_duty())
    pick, ban = _policy(mine, theirs, pool)
    names = pool + sorted(set(counts) - set(pool), key=lambda n: -counts[n])
    rows = [
        {
            "map": n,
            "label": mn.game_map(n),
            "active": n in pool,
            "theirs": counts[n],
            "won": won[n],
            "ours": ours[n],
            "pick": round(100 * pick[n]) if n in pick else None,
            "ban": round(100 * ban[n]) if n in ban else None,
        }
        for n in names
    ]
    chosen = (
        map_name
        if map_name in counts
        else (max(counts, key=lambda n: counts[n]) if counts else None)
    )
    on_map = [m for m in their_maps if m.game_map and m.game_map.name == chosen]
    rounds = _rounds(theirs, on_map)
    h2h = sum(1 for m in their_maps if mine.id in (m.team1_id, m.team2_id))
    first = min((m.match.played_at for m in their_maps if m.match.played_at), default=None)
    return {
        "maps": rows,
        "map": chosen,
        "window": {
            "maps": len(their_maps),
            "matches": len({m.match_id for m in their_maps}),
            "h2h_maps": h2h,
            "since": first,
            "rounds": sum(len(_rounds(theirs, [m])) for m in their_maps) if their_maps else 0,
        },
        "sites": _sites(theirs, rounds),
        "timing": _timing(theirs, rounds, on_map),
        "t_rounds": sum(1 for r in rounds if r.t_team_id == theirs.id),
    }


def _policy(mine: Team, theirs: Team, pool: list[str]) -> tuple[dict, dict]:
    """The Forecast's model of their picks and bans: by how often they play each Map
    and our chance there (forecast._their_policy), not a veto they made."""
    built = forecast.build(mine, theirs)
    p = {r["map"]: r["p"] for r in built["maps"]}
    if not p or any(m not in p for m in pool):
        p = {m: 0.5 for m in pool}
    p = {m: min(0.99, max(0.01, v)) for m, v in p.items()}
    share = forecast.play_share(forecast.played(theirs.id), pool)
    return (
        forecast._their_policy(pool, "pick", p, share),
        forecast._their_policy(pool, "ban", p, share),
    )


def _rounds(team: Team, maps: list[MatchMap]) -> list[Round]:
    from app.services.dbctx import db

    ids = [m.id for m in maps]
    if not ids:
        return []
    return list(
        db().scalars(
            select(Round).where(
                Round.match_map_id.in_(ids),
                (Round.t_team_id == team.id) | (Round.ct_team_id == team.id),
            )
        )
    )


def _sites(team: Team, rounds: list[Round]) -> list[dict]:
    """Their T Rounds by their buy: the bomb down on A, on B, or not at all."""
    by: dict[str, Counter] = defaultdict(Counter)
    for r in rounds:
        if r.t_team_id != team.id or not r.t_buy:
            continue
        where = (
            r.bomb_site if r.bomb_plant_tick is not None and r.bomb_site in ("A", "B") else "none"
        )
        by[r.t_buy][where] += 1
        by[r.t_buy]["won_" + where] += 1 if r.winner_team_id == team.id else 0
    out = []
    for buy in BUYS:
        c = by.get(buy)
        if not c:
            continue
        n = c["A"] + c["B"] + c["none"]
        out.append(
            {
                "buy": str(buy),
                "n": n,
                "a": c["A"],
                "b": c["B"],
                "none": c["none"],
                "won_a": c["won_A"],
                "won_b": c["won_B"],
                "won_none": c["won_none"],
            }
        )
    return out


def _timing(team: Team, rounds: list[Round], maps: list[MatchMap]) -> list[dict]:
    """When their plants came, in seconds from the end of buy time."""
    rate = {m.id: m.tickrate or 64 for m in maps}
    bins = [0] * BINS
    for r in rounds:
        if r.t_team_id != team.id or r.bomb_plant_tick is None:
            continue
        t = (r.bomb_plant_tick - r.freeze_end_tick) / rate.get(r.match_map_id, 64)
        bins[min(BINS - 1, max(0, int(t // BIN)))] += 1
    return [{"from": i * BIN, "n": n} for i, n in enumerate(bins)]
