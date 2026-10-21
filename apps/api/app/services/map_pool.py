"""A Team's map pool: how strong it is on each Map and how deep (docs/plans/05 TM-6).

The Active Duty Maps are Valve's on the day, as ``app/data/patches.json`` has
them (DATA-7). Only when the file names fewer than :data:`ACTIVE_SIZE` are they
read from the data: the Maps played most in the :data:`ACTIVE_WINDOW_DAYS`
before the latest Match, each at least :data:`ACTIVE_MIN_MAPS` times, topped up
from the file's. Each Map's strength is the Team's share of Rounds
won there, pulled toward its own share over every Map by :data:`PRIOR_ROUNDS`
(one Map's worth), so two lucky Maps don't read as a pocket pick. The pool's
depth is how many Active Maps it has played at least :data:`MIN_MAPS` times
without falling more than :data:`DEPTH_GAP` points under its own share.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from sqlalchemy import func, select

from app.models import GameMap, Match, MatchKind, MatchMap, Team
from app.services import mapstrategy, mn, patches
from app.services.dbctx import db, memo

ACTIVE_SIZE = 7
ACTIVE_WINDOW_DAYS = 90
ACTIVE_MIN_MAPS = 3
PRIOR_ROUNDS = 24.0
DEPTH_GAP = 5.0  # points
MIN_MAPS = 2
RECENT_DAYS = 90


def active_duty() -> tuple[str, ...]:
    """The Maps in the competitive pool now."""
    configured = patches.pool_on()
    if len(configured) >= ACTIVE_SIZE:
        return configured

    def compute():
        latest = db().scalar(
            select(func.max(Match.played_at)).where(
                Match.kind == MatchKind.OFFICIAL, Match.played_at.is_not(None)
            )
        )
        counts: Counter = Counter()
        if latest is not None:
            since = latest - timedelta(days=ACTIVE_WINDOW_DAYS)
            for name, n in db().execute(
                select(GameMap.name, func.count(MatchMap.id))
                .join(MatchMap, MatchMap.game_map_id == GameMap.id)
                .join(Match, Match.id == MatchMap.match_id)
                .where(Match.kind == MatchKind.OFFICIAL, Match.played_at >= since)
                .group_by(GameMap.name)
            ):
                counts[name] = n
        found = [name for name, n in counts.most_common() if n >= ACTIVE_MIN_MAPS][:ACTIVE_SIZE]
        for name in configured:
            if len(found) >= ACTIVE_SIZE:
                break
            if name not in found:
                found.append(name)
        return tuple(sorted(found))

    return memo("active_duty", compute)


def team_pool(team: Team) -> dict:
    """Each Active Map (and any other played) with the Team's strength there."""
    profiles = {p["map"]: p for p in mapstrategy.map_profiles(team)}
    played = mapstrategy.maps_in_window(team)
    last: dict[str, object] = {}
    recent: Counter = Counter()
    latest = max((m.match.played_at for m in played if m.match.played_at), default=None)
    for m in played:
        name = m.game_map.name if m.game_map else "?"
        when = m.match.played_at
        if when and (last.get(name) is None or when > last[name]):
            last[name] = when
        if when and latest and (latest - when).days <= RECENT_DAYS:
            recent[name] += 1
    rounds = sum(p["rounds"] for p in profiles.values())
    won = sum(p["rounds_for"] for p in profiles.values())
    mean = 100.0 * won / rounds if rounds else 50.0
    active = active_duty()
    rows, depth = [], 0
    for name in sorted(set(active) | set(profiles)):
        p = profiles.get(name)
        n = p["maps"] if p else 0
        share = shrunk = None
        if p and p["rounds"]:
            share = round(100.0 * p["rounds_for"] / p["rounds"], 1)
            pulled = p["rounds_for"] + PRIOR_ROUNDS * mean / 100.0
            shrunk = round(100.0 * pulled / (p["rounds"] + PRIOR_ROUNDS), 1)
        if n == 0:
            status = "untested"
        elif n < MIN_MAPS:
            status = "thin"
        elif shrunk is not None and shrunk >= mean - DEPTH_GAP:
            status = "deep"
        else:
            status = "weak"
        if name in active and status == "deep":
            depth += 1
        rows.append(
            {
                "map": name,
                "label": mn.game_map(name),
                "active": name in active,
                "maps": n,
                "won": p["won"] if p else 0,
                "rounds": p["rounds"] if p else 0,
                "share": share,
                "shrunk": shrunk,
                "recent": recent[name],
                "last": last[name].date().isoformat() if last.get(name) else None,
                "status": status,
            }
        )
    rows.sort(key=lambda r: (not r["active"], -(r["shrunk"] or 0), r["map"]))
    return {"mean": round(mean, 1), "depth": depth, "active": list(active), "rows": rows}
