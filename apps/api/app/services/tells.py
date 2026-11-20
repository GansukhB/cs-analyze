"""Tells (CONTEXT.md): the choices a Team makes the same way so often, on one
Side of a Map, that the other Team can prepare for them.

Four decision points per Side, read from the Rounds the Playbook reads (the
current five's era, the Game Plan's window and view):

* ``setup``: on CT, the Setup's lean (how many hold A, mid and B 20 s in), over
  the Rounds with four or more placed, pistols apart;
* ``attack``: on T, where and how fast the bomb went down (a plant inside
  ``mapstrategy.RUSH_PLANT_SEC`` is a rush), over the Rounds with a plant;
* ``pistol``: the pistol Round's Setup on CT, its plant site (or none) on T;
* ``after_pistol``: what the Team bought in the Round after a pistol it lost,
  over all its Maps (a buy rule is the Team's, not the Map's, as the Playbook's
  economy reads it), judged against the Pool over all Maps.

A point is a Tell when its most frequent option holds half the Rounds or more,
over ``MIN_ROUNDS`` (``MIN_PISTOLS`` for the two pistol points: one a half), and
its share is at least the Pool's 75th percentile at that point on the Map: a
lean every Team has (Map design) is no Tell. Where fewer than three Teams have
enough Rounds there, two in three Rounds stand in for the Pool's bar. The
Pool's bars are computed once per parse (``pool_cache``). The Veto's Tells are
:mod:`veto_history`'s.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from sqlalchemy import select

from app.models import GameMap, MatchMap, Round, RoundSnapshot, SnapshotMoment
from app.services import mapstrategy, playbook, pool_cache, scope
from app.services.analysis_store import PISTOL_ROUNDS
from app.services.dbctx import db

TELLS_SCHEMA = 1
MIN_ROUNDS = 10
MIN_PISTOLS = 6
SHARE = 0.5
# Where the Pool has too few Teams at a point to set a bar, a fixed one stands in.
NO_POOL_SHARE = 2 / 3
POOL_MIN_TEAMS = 3
MIN_PLACED = 4
MIX = 3

POINTS = ("setup", "attack", "pistol", "after_pistol")
SIDES = {"setup": ("ct",), "attack": ("t",), "pistol": ("ct", "t"), "after_pistol": ("ct", "t")}


def _least(point: str) -> int:
    return MIN_PISTOLS if point in ("pistol", "after_pistol") else MIN_ROUNDS


def _pattern(spots: list, side: str, sites) -> tuple | None:
    leans = [playbook.lean((x, y, z), sites) for _p, s, _place, x, y, z in spots if s == side]
    if len(leans) < MIN_PLACED:
        return None
    count = Counter(leans)
    return tuple(count.get(k, 0) for k in playbook.LEANS)


def choices(team_id: int, rounds: list, setups: dict, sites) -> dict[tuple, list]:
    """``{(point, side): [(option, round)]}`` over the Team's Rounds. ``setups`` is
    ``{round_id: [(player, side, place, x, y, z)]}`` at the Setup moment."""
    by_key = {(r.match_map_id, r.number): r for r in rounds}
    known = "A" in sites and "B" in sites
    out: dict[tuple, list] = defaultdict(list)
    for r in rounds:
        side = r.side_of(team_id)
        if not side:
            continue
        pistol = r.number in PISTOL_ROUNDS
        if side == "ct":
            pattern = _pattern(setups.get(r.id, ()), "ct", sites) if known else None
            if pattern is not None:
                out[("pistol" if pistol else "setup", "ct")].append((pattern, r))
        elif pistol:
            out[("pistol", "t")].append(((r.site or "?") if r.plant is not None else "none", r))
        elif r.plant is not None:
            tempo = "rush" if r.secs(r.plant) <= mapstrategy.RUSH_PLANT_SEC else "default"
            out[("attack", "t")].append(((r.site or "?", tempo), r))
        if pistol and r.winner is not None and r.winner != team_id:
            nxt = by_key.get((r.match_map_id, r.number + 1))
            if nxt is not None and nxt.buy(team_id):
                out[("after_pistol", side)].append((nxt.buy(team_id), nxt))
    return out


def _top_share(options: list) -> tuple[object, float, int]:
    counts = Counter(o for o, _r in options)
    top, k = counts.most_common(1)[0]
    return top, k / len(options), len(options)


# ---------------------------------------------------------------- the Pool ---
def _pool_rounds(map_name: str | None) -> tuple[list, dict]:
    """Every Round on the Map the session sees (on every Map with none), as the
    Playbook's rounds, and their Setup snapshots (only for one Map)."""
    rows = db().execute(
        select(Round.id, Round.match_map_id, Round.number, Round.freeze_end_tick, Round.end_tick,
               Round.bomb_plant_tick, Round.bomb_site, Round.winner_team_id, Round.ct_team_id,
               Round.t_team_id, Round.ct_buy, Round.t_buy, MatchMap.match_id, MatchMap.map_number,
               MatchMap.tickrate)
        .join(MatchMap, MatchMap.id == Round.match_map_id)
        .join(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(GameMap.name == map_name if map_name else GameMap.name.is_not(None))
        .order_by(Round.match_map_id, Round.number)
    ).all()  # fmt: skip
    rounds = [
        playbook._Round(
            id=r.id, match_map_id=r.match_map_id, match_id=r.match_id, map_number=r.map_number,
            number=r.number, tickrate=r.tickrate or 64, freeze_end=r.freeze_end_tick,
            end=r.end_tick, plant=r.bomb_plant_tick, site=r.bomb_site, winner=r.winner_team_id,
            ct_team=r.ct_team_id, t_team=r.t_team_id, ct_buy=r.ct_buy, t_buy=r.t_buy, h2h=False,
        )
        for r in rows
    ]  # fmt: skip
    setups: dict[int, list] = defaultdict(list)
    ids = [r.id for r in rounds] if map_name else []
    for i in range(0, len(ids), 5000):
        for s in db().execute(
            select(RoundSnapshot.round_id, RoundSnapshot.player_id, RoundSnapshot.side,
                   RoundSnapshot.place, RoundSnapshot.x, RoundSnapshot.y, RoundSnapshot.z)
            .where(RoundSnapshot.round_id.in_(ids[i : i + 5000]),
                   RoundSnapshot.moment == SnapshotMoment.SETUP)
        ):  # fmt: skip
            setups[s.round_id].append((s.player_id, s.side, s.place, s.x, s.y, s.z))
    return rounds, setups


def _bars(map_name: str | None) -> dict[str, float]:
    """``{"point:side": p75}`` of every Team's top share on the Map (on every Map
    with none), where three Teams or more have enough Rounds at that point."""
    rounds, setups = _pool_rounds(map_name)
    sites = playbook.site_centroids(map_name) if map_name else {}
    by_team: dict[int, list] = defaultdict(list)
    for r in rounds:
        for team in (r.ct_team, r.t_team):
            if team is not None:
                by_team[team].append(r)
    shares: dict[str, list] = defaultdict(list)
    for team, theirs in by_team.items():
        for (point, side), options in choices(team, theirs, setups, sites).items():
            if len(options) >= _least(point):
                shares[f"{point}:{side}"].append(_top_share(options)[1])
    out = {}
    for key, values in shares.items():
        if len(values) >= POOL_MIN_TEAMS:
            values.sort()
            out[key] = values[int(0.75 * (len(values) - 1))]
    return out


def pool_bars(map_name: str | None) -> dict[str, float]:
    """The Pool's bars on one Map, or over every Map with ``None``, cut again at
    most every few hours (`pool_cache.epoch_stamp`, docs/adr/0015): a Team's own
    choices are read from its Rounds on every call."""
    stamp = f"{pool_cache.epoch_stamp()}{scope.cache_part(db())}"
    key = f"tells:v{TELLS_SCHEMA}:{map_name or '*'}:{stamp}"
    return pool_cache.remember(key, lambda: _bars(map_name))


# ------------------------------------------------------------ one Team -------
def _option(point: str, side: str, option) -> dict:
    if point in ("setup",) or (point == "pistol" and side == "ct"):
        return {"setup": dict(zip(playbook.LEANS, option, strict=True))}
    if point == "attack":
        return {"site": option[0], "tempo": option[1]}
    if point == "pistol":
        return {"site": option}
    return {"buy": str(option)}


def for_team(
    team_id: int, rounds: list, setups: dict, sites, map_name: str, every_map: list | None = None
) -> list[dict]:
    """The Team's decision points on the Map, Tell or not, CT first: each with its
    top option, its share against the Pool's bar, how it went, and its Rounds.
    ``every_map`` (the Team's Rounds on all its Maps) is where the buy after a lost
    pistol is read, against the Pool over all Maps."""
    bars = pool_bars(map_name) if map_name else {}
    found = choices(team_id, rounds, setups, sites)
    if every_map is not None:
        overall = choices(team_id, every_map, {}, {})
        everywhere = pool_bars(None)
        for side in ("ct", "t"):
            found[("after_pistol", side)] = overall.get(("after_pistol", side)) or []
            if (bar := everywhere.get(f"after_pistol:{side}")) is not None:
                bars[f"after_pistol:{side}"] = bar
            else:
                bars.pop(f"after_pistol:{side}", None)
    out = []
    for side in ("ct", "t"):
        for point in POINTS:
            if side not in SIDES[point]:
                continue
            options = found.get((point, side)) or []
            if not options:
                continue
            top, share, n = _top_share(options)
            counts = Counter(o for o, _r in options)
            entropy = -sum(c / n * math.log(c / n) for c in counts.values())
            top_rounds = [r for o, r in options if o == top]
            bar = bars.get(f"{point}:{side}")
            out.append(
                {
                    "point": point,
                    "side": side,
                    "top": _option(point, side, top),
                    "n": len(top_rounds),
                    "of": n,
                    "share": round(share, 3),
                    "options": round(math.exp(entropy), 1),
                    "pool_p75": round(bar, 3) if bar is not None else None,
                    "tell": n >= _least(point)
                    and share >= SHARE
                    and share >= (NO_POOL_SHARE if bar is None else bar),
                    "won": sum(1 for r in top_rounds if r.winner == team_id),
                    "all_maps": every_map is not None and point == "after_pistol",
                    "mix": [
                        {**_option(point, side, o), "n": c} for o, c in counts.most_common(MIX)
                    ],
                    "evidence": playbook._evidence(top_rounds, n),
                }
            )
    return out
