"""A my team's utility over a window (v2 screen 06).

* KPIs: utility damage per Round, flash assists per Match Map, enemies blinded
  per flash and the share of flashes that blinded a teammate (the Review's
  per-Player utility), how long an execute's smokes and fires take to land (the
  first to the last in the 15 s before a plant), and the Review's
  ``unused_utility`` Findings per 24 Rounds where the Loadout lets it see them;
* flash → fight: from each of our flashes popping to the first kill within 3 s
  that one of ours made or took, and how often it was ours;
* lineup accuracy: our throws of one kind from one spot (48 units) and aim (20°),
  five or more, and the share that landed within 128 units of their median
  landing (the lineup library's cells, ``lineups``);
* each Player's throws, damage, assists and flashes.

Read from ``grenade_throws``, ``kill_events``, ``player_map_utility`` and the
stored Reviews. Bind a session with ``dbctx.using``.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    GrenadeThrow,
    GrenadeType,
    KillEvent,
    MatchMap,
    Player,
    PlayerMapUtility,
    PlayerRound,
    Round,
    Team,
)
from app.services import review, team_numbers
from app.services.dbctx import db
from app.services.lineups import FROM_CELL, TO_CELL, YAW_SPLIT

FIGHT_WINDOW = 3.0  # seconds after a flash pops in which the fight it was for comes
EXECUTE_WINDOW = 15.0
SYNC_BINS = (0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5)
MIN_LINEUP = 5
LINEUPS = 6
SCATTER = 80


def build(session: Session, team: Team, maps: list[MatchMap], map_name: str | None) -> dict:
    ids = [m.id for m in maps]
    rate = {m.id: m.tickrate or 64 for m in maps}
    rounds = list(db().scalars(select(Round).where(Round.match_map_id.in_(ids or [0]))))
    by_id = {r.id: r for r in rounds}
    mine = {
        r.id: ("ct" if r.ct_team_id == team.id else "t" if r.t_team_id == team.id else None)
        for r in rounds
    }
    ours = {rid for rid, side in mine.items() if side}
    throws = [
        g
        for g in db().scalars(select(GrenadeThrow).where(GrenadeThrow.round_id.in_(ours or {0})))
        if g.thrower_side == mine.get(g.round_id)
    ]
    players = _players(session, team, maps, throws, ours)
    flashes = sum(p["flashes"] for p in players)
    blinded = sum(p["enemies_blinded"] for p in players)
    team_flashes = sum(p["team_flashes"] for p in players)
    rounds_played = sum(1 for _r in ours)
    util_damage = sum(p["utility_damage"] for p in players)
    assists = sum(p["flash_assists"] for p in players)
    unused = sum(p["unused"] for p in players)
    loadout_rounds = sum(p["loadout_rounds"] for p in players) / 5 if players else 0
    choices = Counter(
        m.game_map.name for m in maps if m.game_map
    )  # the lineup section's Maps, most played first
    chosen = (
        map_name if map_name in choices else (choices.most_common(1)[0][0] if choices else None)
    )
    return {
        "rounds": rounds_played,
        "maps": len(maps),
        "throws": len(throws),
        "kpis": {
            "damage_per_round": round(util_damage / rounds_played, 1) if rounds_played else None,
            "assists_per_map": round(assists / len(maps), 1) if maps else None,
            "blinded_per_flash": round(blinded / flashes, 2) if flashes else None,
            "team_flash_pct": round(100.0 * team_flashes / flashes, 1) if flashes else None,
            "execute_seconds": _execute(by_id, throws, rate),
            "unused_per24": round(24.0 * unused / loadout_rounds, 2) if loadout_rounds else None,
        },
        "sync": _sync(session, team, by_id, throws, rate),
        "map_choices": [{"map": m, "n": n} for m, n in choices.most_common()],
        "map": chosen,
        "lineups": _lineups(throws, by_id, maps, chosen),
        "players": players,
    }


def _players(session, team, maps, throws, ours) -> list[dict]:
    ids = [m.id for m in maps]
    rows: dict[int, dict] = {}
    counts: dict[int, Counter] = defaultdict(Counter)
    for g in throws:
        if g.thrower_id:
            counts[g.thrower_id][g.type] += 1
    played: Counter = Counter()
    for pid, _rid in session.execute(
        select(PlayerRound.player_id, PlayerRound.round_id).where(
            PlayerRound.round_id.in_(ours or {0}), PlayerRound.team_id == team.id
        )
    ):
        played[pid] += 1
    util = defaultdict(lambda: [0, 0])
    for u in db().scalars(
        select(PlayerMapUtility).where(
            PlayerMapUtility.match_map_id.in_(ids or [0]), PlayerMapUtility.team_id == team.id
        )
    ):
        util[u.player_id][0] += u.fire_damage + u.he_damage
        util[u.player_id][1] += u.flash_assists
    sids = dict(
        session.execute(
            select(Player.id, Player.steamid).where(Player.id.in_(list(played) or [0]))
        ).all()
    )
    names = dict(
        session.execute(
            select(Player.id, Player.name).where(Player.id.in_(list(played) or [0]))
        ).all()
    )
    by_sid = {str(s): pid for pid, s in sids.items()}
    reviewed: dict[int, Counter] = defaultdict(Counter)
    for m in maps:
        stored = review.ensure(session, m, stale_ok=True) if m.is_parsed else None
        if not stored:
            continue
        loadout = not stored.get("needs_loadout")
        for p in stored.get("players", []):
            pid = by_sid.get(p["sid"])
            if pid is None:
                continue
            for k, v in (p.get("utility") or {}).items():
                reviewed[pid][k] += v
            if loadout:
                reviewed[pid]["loadout_rounds"] += p.get("rounds", 0)
        for f in stored.get("findings", []):
            if f["code"] == "unused_utility" and f.get("sids"):
                pid = by_sid.get(f["sids"][0])
                if pid is not None:
                    reviewed[pid]["unused"] += 1
    for pid, n in played.items():
        c, r = counts[pid], reviewed[pid]
        flashes = int(r["flashes"])
        rows[pid] = {
            "steamid": str(sids.get(pid, "")),
            "name": names.get(pid, "?"),
            "rounds": n,
            "per_round": round(sum(c.values()) / n, 2) if n else None,
            "smokes": c[GrenadeType.SMOKE],
            "flashes_thrown": c[GrenadeType.FLASH],
            "molotovs": c[GrenadeType.INFERNO],
            "hes": c[GrenadeType.HE],
            "utility_damage": util[pid][0],
            "flash_assists": util[pid][1],
            "flashes": flashes,
            "enemies_blinded": int(r["enemies_blinded"]),
            "team_flashes": int(r["team_flashes"]),
            "team_flash_pct": round(100.0 * r["team_flashes"] / flashes, 1) if flashes else None,
            "unused": int(r["unused"]),
            "loadout_rounds": int(r["loadout_rounds"]),
        }
    out = [r for r in rows.values() if r["rounds"] >= 1]
    out.sort(key=lambda r: -(r["per_round"] or 0))
    return out


def _execute(by_id, throws, rate) -> float | None:
    """Median seconds from the first to the last smoke or fire landing in the 15 s
    before our plants, over plants with two or more."""
    spans = []
    landed = defaultdict(list)
    for g in throws:
        if (
            g.type in (GrenadeType.SMOKE, GrenadeType.INFERNO)
            and g.start_tick
            and g.thrower_side == "t"
        ):
            landed[g.round_id].append(g.start_tick)
    for rid, ticks in landed.items():
        r = by_id.get(rid)
        if r is None or r.bomb_plant_tick is None:
            continue
        hz = rate.get(r.match_map_id, 64)
        near = [t for t in ticks if 0 <= r.bomb_plant_tick - t <= EXECUTE_WINDOW * hz]
        if len(near) >= 2:
            spans.append((max(near) - min(near)) / hz)
    return round(statistics.median(spans), 1) if spans else None


def _sync(session, team, by_id, throws, rate) -> dict:
    """From each of our flashes popping to the first kill with one of ours in it
    inside FIGHT_WINDOW seconds: how long, and whether ours."""
    # A flash's pop is its throw_tick (the parse keeps it there, not in start_tick).
    pops = defaultdict(list)
    for g in throws:
        if g.type == GrenadeType.FLASH and g.throw_tick:
            pops[g.round_id].append(g.throw_tick)
    if not pops:
        return {"bins": [], "fights": 0, "won": 0, "flashes": 0}
    team_of = {
        (rid, pid): tid
        for rid, pid, tid in session.execute(
            select(PlayerRound.round_id, PlayerRound.player_id, PlayerRound.team_id).where(
                PlayerRound.round_id.in_(list(pops))
            )
        )
    }
    kills = defaultdict(list)
    for rid, tick, attacker, victim in session.execute(
        select(KillEvent.round_id, KillEvent.tick, KillEvent.attacker_id, KillEvent.victim_id)
        .where(KillEvent.round_id.in_(list(pops)))
        .order_by(KillEvent.tick)
    ):
        kills[rid].append((tick, attacker, victim))
    edges = [*SYNC_BINS, math.inf]
    bins = [[0, 0] for _ in edges]
    fights = won = flashes = 0
    for rid, ticks in pops.items():
        hz = rate.get(by_id[rid].match_map_id, 64)
        for pop in ticks:
            flashes += 1
            fight = next(
                (
                    (t, a, v)
                    for t, a, v in kills[rid]
                    if 0 <= t - pop <= FIGHT_WINDOW * hz
                    and team.id in (team_of.get((rid, a)), team_of.get((rid, v)))
                ),
                None,
            )
            if fight is None:
                continue
            dt = (fight[0] - pop) / hz
            ours = team_of.get((rid, fight[1])) == team.id
            i = next(i for i, e in enumerate(edges) if dt < e)
            bins[i][0] += 1
            bins[i][1] += 1 if ours else 0
            fights += 1
            won += 1 if ours else 0
    lows = [0.0, *SYNC_BINS]
    return {
        "bins": [
            {"from": lo, "to": None if hi == math.inf else hi, "n": n, "won": w}
            for lo, hi, (n, w) in zip(lows, edges, bins, strict=True)
        ],
        "fights": fights,
        "won": won,
        "flashes": flashes,
    }


def _lineups(throws, by_id, maps, map_name: str | None) -> list[dict]:
    """Our throws of one kind from one spot and aim, five or more, and the share
    that landed near where they usually land."""
    if map_name is None:
        return []
    on_map = {m.id for m in maps if m.game_map and m.game_map.name == map_name}
    groups: dict[tuple, list[GrenadeThrow]] = defaultdict(list)
    for g in throws:
        r = by_id.get(g.round_id)
        if r is None or r.match_map_id not in on_map:
            continue
        if None in (g.thrown_x, g.thrown_y, g.thrown_yaw, g.x, g.y):
            continue
        key = (g.type, g.thrower_side, int(g.thrown_x // FROM_CELL), int(g.thrown_y // FROM_CELL),
               int(((g.thrown_yaw + 180) % 360) // YAW_SPLIT))  # fmt: skip
        groups[key].append(g)
    out = []
    for (kind, side, *_cell), group in groups.items():
        if len(group) < MIN_LINEUP:
            continue
        mx = statistics.median(g.x for g in group)
        my = statistics.median(g.y for g in group)
        near = [g for g in group if math.hypot(g.x - mx, g.y - my) <= TO_CELL]
        place = Counter(g.place for g in group if g.place).most_common(1)
        start = Counter(g.thrown_place for g in group if g.thrown_place).most_common(1)
        out.append(
            {
                "type": kind,
                "side": side,
                "from_place": start[0][0] if start else "",
                "to_place": place[0][0] if place else "",
                "throws": len(group),
                "accuracy": round(100.0 * len(near) / len(group)),
                "radius": TO_CELL,
                "scatter": [[round(g.x - mx), round(g.y - my)] for g in group[:SCATTER]],
                "throwers": [
                    n
                    for n, _c in Counter(g.thrower.name for g in group if g.thrower).most_common(3)
                ],
            }
        )
    out.sort(key=lambda r: -r["throws"])
    return out[:LINEUPS]


def maps_for(team: Team, days: int | None, kind: str | None) -> list[MatchMap]:
    from datetime import UTC, datetime, timedelta

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days) if days else None
    return team_numbers.team_maps(team.id, since, kind=kind)
