"""A Team against the strength of who it played (docs/plans/05 TM-2, TM-10).

Its Rating, where that ranks among the Teams still playing, how it moved, and
its stored Match Maps split by the opponent's tier, each against what the two
Ratings expected before that day: "do we only beat the weak ones" in numbers.
And Round by Round on each Side: the Map's expected win turned into a Round's
(the Round chance that wins a regulation Map that often) and moved by how the
Map favours that Side across the Pool, against the Rounds it actually won.
"""

from __future__ import annotations

import math

from sqlalchemy import case, func, or_, select

from app.models import GameMap, Match, MatchMap, Round, Team
from app.services import forecast, rating
from app.services.dbctx import db, memo

ACTIVE_DAYS = 180  # a Team ranks while it has played a series this recently
TIERS = ((20, "Top 20"), (60, "21–60"), (None, "Бусад"))
TREND_POINTS = 48


def _tier(rank: int | None) -> str:
    for top, label in TIERS:
        if top is None or (rank is not None and rank <= top):
            return label
    return TIERS[-1][1]


def ranks() -> dict[str, int]:
    """Every Team still playing, ranked by its Rating (keyed as ``rating._key``)."""
    snap = rating.current()
    as_of = snap.as_of
    active = sorted(
        (
            (t.rating, key)
            for key, t in snap.teams.items()
            if t.last and as_of and (as_of - t.last).days <= ACTIVE_DAYS
            and t.series >= forecast.COLD_SERIES
        ),
        reverse=True,
    )  # fmt: skip
    return {key: i + 1 for i, (_r, key) in enumerate(active)}


def map_chance(p: float) -> float:
    """The chance a Round chance ``p`` wins a regulation Map (12-12 a coin flip)."""
    won = sum(math.comb(24, k) * p**k * (1 - p) ** (24 - k) for k in range(13, 25))
    return won + 0.5 * math.comb(24, 12) * p**12 * (1 - p) ** 12


def round_chance(p_map: float) -> float:
    """The Round chance that wins a Map ``p_map`` of the time (inverse of :func:`map_chance`)."""
    lo, hi = 0.01, 0.99
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if map_chance(mid) < p_map else (lo, mid)
    return (lo + hi) / 2


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def ct_bias() -> dict[str, float]:
    """Each Map's CT Round win rate across every stored Round, as a log-odds shift."""

    def compute():
        rows = db().execute(
            select(GameMap.name, func.count(Round.id),
                   func.sum(case((Round.winner_side == "ct", 1), else_=0)))
            .join(MatchMap, MatchMap.game_map_id == GameMap.id)
            .join(Round, Round.match_map_id == MatchMap.id)
            .where(Round.winner_side.in_(("ct", "t")))
            .group_by(GameMap.name)
        ).all()  # fmt: skip
        return {m: _logit((int(ct) + 1) / (n + 2)) for m, n, ct in rows if n}

    return memo(("ct_bias",), compute)


def _rounds(team: Team, expected_map) -> list[dict]:
    """TM-2: Rounds won on each Side against what the opponent's Rating and the
    Map's Side expected, Round by Round."""
    bias = ct_bias()
    sides = {s: {"side": s, "rounds": 0, "won": 0, "expected": 0.0} for s in ("ct", "t")}
    rows = db().execute(
        select(MatchMap.id, Match.played_at, GameMap.name, Round.ct_team_id, Round.t_team_id,
               Round.winner_team_id)
        .join(Round, Round.match_map_id == MatchMap.id)
        .join(Match, Match.id == MatchMap.match_id)
        .join(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(or_(Round.ct_team_id == team.id, Round.t_team_id == team.id),
               Round.ct_team_id.is_not(None), Round.t_team_id.is_not(None),
               Match.played_at.is_not(None))
    ).all()  # fmt: skip
    per_map: dict[int, float | None] = {}
    for mm, played, map_name, ct, t, winner in rows:
        other = t if ct == team.id else ct
        if mm not in per_map:
            p_map = expected_map(played.date(), other)
            per_map[mm] = None if p_map is None else _logit(round_chance(p_map))
        base = per_map[mm]
        if base is None:
            continue
        side = "ct" if ct == team.id else "t"
        shift = bias.get(map_name, 0.0) * (1 if side == "ct" else -1)
        row = sides[side]
        row["rounds"] += 1
        row["won"] += int(winner == team.id)
        row["expected"] += 1 / (1 + math.exp(-(base + shift)))
    out = []
    for row in sides.values():
        if not row["rounds"]:
            continue
        residual = row["won"] - row["expected"]
        out.append({**row, "expected": round(row["expected"], 1), "residual": round(residual, 1),
                    "per24": round(24 * residual / row["rounds"], 2)})  # fmt: skip
    return out


def expected_results(team: Team, rows: list[tuple]) -> dict[int, float]:
    """TM-10: each Match's chance for ``team`` from the two Ratings the day before,
    ``rows`` being ``(match id, played_at, opponent id, Maps played)``; a Match of
    two or three Maps read as a Bo3, of four or five as a Bo5."""
    me = forecast.standing(team)
    if me is None:
        return {}
    snap = rating.current()
    names = forecast._team_names()
    slope = forecast.map_slope() * math.log(10) / rating.SCALE
    between = forecast._region_gap(snap)
    out = {}
    for match_id, played, other_id, maps in rows:
        other = names.get(other_id)
        if played is None or other is None:
            continue
        day = played.date() if hasattr(played, "date") else played
        mine, theirs = snap.before(me.name, day), snap.before(other, day)
        if mine is None or theirs is None:
            continue
        p = 1 / (1 + math.exp(-(slope * (mine - theirs) + between(me.name, other))))
        best_of = 1 if maps <= 1 else 3 if maps <= 3 else 5
        out[match_id] = round(forecast.series_chance([p] * best_of, best_of), 3)
    return out


def tier_of(name: str, rank_of: dict[str, int]) -> str:
    return _tier(rank_of.get(rating._key(name)))


def build(team: Team) -> dict | None:
    me = forecast.standing(team)
    if me is None:
        return None
    snap = rating.current()
    rank_of = ranks()
    history = snap.history.get(rating._key(me.name)) or []
    step = max(1, math.ceil(len(history) / TREND_POINTS))
    trend = history[::step]
    if history and (not trend or trend[-1] != history[-1]):
        trend.append(history[-1])

    names = forecast._team_names()
    slope = forecast.map_slope() * math.log(10) / rating.SCALE
    between = forecast._region_gap(snap)
    tiers: dict[str, dict] = {label: {"tier": label, "maps": 0, "won": 0, "expected": 0.0}
                              for _top, label in TIERS}  # fmt: skip
    for played, _map, t1, t2, winner, *_ in forecast._stored_maps():
        if team.id not in (t1, t2):
            continue
        other = names.get(t2 if t1 == team.id else t1)
        mine, theirs = snap.before(me.name, played), snap.before(other, played) if other else None
        if mine is None or theirs is None:
            continue
        row = tiers[_tier(rank_of.get(rating._key(other)))]
        row["maps"] += 1
        row["won"] += int(winner == team.id)
        row["expected"] += 1 / (1 + math.exp(-(slope * (mine - theirs) + between(me.name, other))))

    def expected_map(played, other_id) -> float | None:
        other = names.get(other_id)
        mine, theirs = snap.before(me.name, played), snap.before(other, played) if other else None
        if mine is None or theirs is None:
            return None
        return 1 / (1 + math.exp(-(slope * (mine - theirs) + between(me.name, other))))

    out_tiers = []
    for row in tiers.values():
        if not row["maps"]:
            continue
        out_tiers.append(
            {
                **row,
                "expected": round(row["expected"], 1),
                "residual": round(row["won"] - row["expected"], 1),
            }
        )
    return {
        **forecast._standing_json(me),
        "rank": rank_of.get(rating._key(me.name)),
        "ranked": len(rank_of),
        "trend": [{"date": d, "rating": r} for d, r in trend],
        "tiers": out_tiers,
        "rounds": _rounds(team, expected_map),
    }
