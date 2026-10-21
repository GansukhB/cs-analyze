"""A Strat's Rounds and how it did (docs/plans/08 SB-4).

A Round of the Strat's Team on its Map and Side is found to be the Strat when
every grenade the Strat names (with a Callout) landed there, of its kind and,
when the Strat gives a second, within :data:`SPREAD` of it: the Set play rule.
A Strat with fewer than :data:`MIN_GRENADES` such grenades is too thin to find.
Found Rounds are kept as examples Staff have yet to confirm; a removed one is
kept as dismissed so it is not found again.

Its report counts every kept Round (official and Scrims alike, the Workspace's
own): played, won with an 80% range, by our buy, official against Scrim, and
when last.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select

from app.models import (
    GameMap,
    GrenadeThrow,
    Match,
    MatchKind,
    MatchMap,
    Round,
    Strat,
    StratExample,
    StratStatus,
)
from app.models.base import utcnow
from app.services import scope, stats
from app.services.dbctx import db

SPREAD = 5.0  # seconds
WINDOW = 60.0  # seconds after freeze end, for a grenade with no second given
MIN_GRENADES = 2
RECENT_DAYS = 30
Z80 = 1.2816


def _wanted(strat: Strat) -> list[tuple[str, str, float | None]]:
    return [
        (g["type"], g["place"], g.get("at"))
        for g in strat.grenades or []
        if g.get("place") and g.get("type") in ("smoke", "inferno", "flash", "he")
    ]


def find(strat: Strat) -> list[tuple[int, int]]:
    """``(match_map id, round number)`` of every Round that played the Strat."""
    wanted = _wanted(strat)
    if len(wanted) < MIN_GRENADES:
        return []
    session = db()
    scope.allow_scrims(session)
    team_side = Round.ct_team_id if strat.side == "ct" else Round.t_team_id
    rounds = session.execute(
        select(Round.id, Round.match_map_id, Round.number, Round.freeze_end_tick, MatchMap.tickrate)
        .join(MatchMap, MatchMap.id == Round.match_map_id)
        .join(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(GameMap.name == strat.map_name, team_side == strat.team_id)
    ).all()
    if not rounds:
        return []
    by_id = {r.id: r for r in rounds}
    landed: dict[int, list] = defaultdict(list)
    for rid, kind, place, start, pop in session.execute(
        select(GrenadeThrow.round_id, GrenadeThrow.type, GrenadeThrow.place,
               GrenadeThrow.start_tick, GrenadeThrow.throw_tick)
        .where(GrenadeThrow.round_id.in_(list(by_id)), GrenadeThrow.thrower_side == strat.side)
    ):  # fmt: skip
        r = by_id[rid]
        tick = start or pop
        if tick is not None:
            landed[rid].append((kind, place, (tick - r.freeze_end_tick) / (r.tickrate or 64)))
    out = []
    for rid, nades in landed.items():
        if all(
            any(
                kind == k and place == p
                and (abs(t - at) <= SPREAD if at is not None else 0 <= t <= WINDOW)
                for kind, place, t in nades
            )
            for k, p, at in wanted
        ):  # fmt: skip
            r = by_id[rid]
            out.append((r.match_map_id, r.number))
    return sorted(out)


def refresh(strat: Strat) -> int:
    """Keep the newly found Rounds as examples to confirm; the count added."""
    session = db()
    have = {
        (e.match_map_id, e.round)
        for e in session.scalars(select(StratExample).where(StratExample.strat_id == strat.id))
    }
    added = 0
    for mm, n in find(strat):
        if (mm, n) not in have:
            session.add(StratExample(strat_id=strat.id, match_map_id=mm, round=n, source="auto",
                                     confirmed=False))  # fmt: skip
            added += 1
    return added


def _range(k: int, n: int) -> tuple[float, float]:
    """An 80% range for k of n (Wilson)."""
    return stats.wilson(k, n, Z80)


def report(strat: Strat) -> dict:
    """How the Strat did over its kept Rounds."""
    session = db()
    scope.allow_scrims(session)
    rows = session.execute(
        select(Round.winner_team_id, Round.ct_team_id, Round.ct_buy, Round.t_buy,
               Match.kind, Match.played_at, StratExample.source, StratExample.confirmed)
        .join(StratExample, (StratExample.match_map_id == Round.match_map_id)
              & (StratExample.round == Round.number))
        .join(MatchMap, MatchMap.id == Round.match_map_id)
        .join(Match, Match.id == MatchMap.match_id)
        .where(StratExample.strat_id == strat.id, StratExample.source != "dismissed")
    ).all()  # fmt: skip
    if not rows:
        return {"played": 0}
    won = [r.winner_team_id == strat.team_id for r in rows]
    buys: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    kinds: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r, w in zip(rows, won, strict=True):
        buy = (r.ct_buy if r.ct_team_id == strat.team_id else r.t_buy) or "?"
        buys[buy][0] += 1
        buys[buy][1] += int(w)
        kinds[str(r.kind)][0] += 1
        kinds[str(r.kind)][1] += int(w)
    low, high = _range(sum(won), len(won))
    last = max((r.played_at for r in rows if r.played_at), default=None)
    return {
        "played": len(rows),
        "won": sum(won),
        "low": round(100 * low),
        "high": round(100 * high),
        "pending": sum(1 for r in rows if not r.confirmed),
        "by_buy": {k: {"played": v[0], "won": v[1]} for k, v in sorted(buys.items())},
        "official": {"played": kinds[MatchKind.OFFICIAL][0], "won": kinds[MatchKind.OFFICIAL][1]},
        "scrim": {"played": kinds[MatchKind.SCRIM][0], "won": kinds[MatchKind.SCRIM][1]},
        "last": last.date().isoformat() if last else None,
    }


def coverage(workspace_id: int, team_id: int) -> dict[str, dict]:
    """Per Map: the Team's active Strats, and how many were played in the last
    :data:`RECENT_DAYS` (the veto lab's readiness, GP-10)."""
    session = db()
    scope.allow_scrims(session)
    strats = session.scalars(
        select(Strat).where(
            Strat.workspace_id == workspace_id,
            Strat.team_id == team_id,
            Strat.status == StratStatus.ACTIVE,
        )
    ).all()
    since = utcnow() - timedelta(days=RECENT_DAYS)
    recent = set(
        session.scalars(
            select(StratExample.strat_id)
            .join(MatchMap, MatchMap.id == StratExample.match_map_id)
            .join(Match, Match.id == MatchMap.match_id)
            .where(
                StratExample.strat_id.in_([s.id for s in strats]),
                StratExample.source != "dismissed",
                Match.played_at >= since,
            )
        )
    )
    out: dict[str, dict] = defaultdict(lambda: {"active": 0, "recent": 0})
    for s in strats:
        out[s.map_name]["active"] += 1
        out[s.map_name]["recent"] += int(s.id in recent)
    return dict(out)
