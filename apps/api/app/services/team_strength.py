"""A Team against the strength of who it played (docs/plans/05 TM-2, TM-10).

Its Rating, where that ranks among the Teams still playing, how it moved, and
its stored Match Maps split by the opponent's tier, each against what the two
Ratings expected before that day: "do we only beat the weak ones" in numbers.
"""

from __future__ import annotations

import math

from app.models import Team
from app.services import forecast, rating

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
    }
