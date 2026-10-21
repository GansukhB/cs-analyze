"""The lineup library (docs/plans/08 SB-3): grenades thrown the same way again.

Each grenade's throw (schema 14: where the thrower stood and aimed as it left
the hand) is grouped with the others of its kind thrown from the same spot
(:data:`FROM_CELL`) to the same landing (:data:`TO_CELL`) on a Map. A group of
:data:`MIN_THROWS` or more is a lineup: its spot and aim as medians, where it
lands, how long it flies, who throws it, and the practice-server command that
puts you there (``setpos`` the feet, ``setang`` pitch and yaw).

Read off ``grenade_throws``, computed once per parse and Map (:mod:`pool_cache`).
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict

from sqlalchemy import select

from app.models import GameMap, GrenadeThrow, Match, MatchMap, Player, Round, Team
from app.services import pool_cache
from app.services.dbctx import db

LINEUPS_SCHEMA = 1
FROM_CELL = 48.0  # units: where the thrower stood
TO_CELL = 128.0  # units: where it landed
YAW_SPLIT = 20.0  # degrees: two aims this far apart from one spot are two lineups
MIN_THROWS = 3
MAX_REFS = 6


def _cell(v: float, size: float) -> int:
    return int(v // size)


def _rows(map_name: str) -> list:
    return list(
        db().execute(
            select(
                GrenadeThrow.type, GrenadeThrow.thrower_side, GrenadeThrow.thrown_tick,
                GrenadeThrow.start_tick, GrenadeThrow.throw_tick, GrenadeThrow.thrown_x,
                GrenadeThrow.thrown_y, GrenadeThrow.thrown_z, GrenadeThrow.thrown_pitch,
                GrenadeThrow.thrown_yaw, GrenadeThrow.thrown_place, GrenadeThrow.x,
                GrenadeThrow.y, GrenadeThrow.place, Round.number, MatchMap.match_id,
                MatchMap.map_number, MatchMap.tickrate, Player.name, Team.name,
            )
            .join(Round, Round.id == GrenadeThrow.round_id)
            .join(MatchMap, MatchMap.id == Round.match_map_id)
            .join(GameMap, GameMap.id == MatchMap.game_map_id)
            .join(Match, Match.id == MatchMap.match_id)
            .outerjoin(Player, Player.id == GrenadeThrow.thrower_id)
            .outerjoin(
                Team,
                Team.id == ((Round.ct_team_id * (GrenadeThrow.thrower_side == "ct"))
                            + (Round.t_team_id * (GrenadeThrow.thrower_side == "t"))),
            )
            .where(
                GameMap.name == map_name,
                GrenadeThrow.thrown_tick.is_not(None),
                GrenadeThrow.thrown_x.is_not(None),
                GrenadeThrow.x.is_not(None),
            )
        )
    )  # fmt: skip


def _build(map_name: str) -> list[dict]:
    groups: dict[tuple, list] = defaultdict(list)
    for r in _rows(map_name):
        key = (
            r.type, r.thrower_side,
            _cell(r.thrown_x, FROM_CELL), _cell(r.thrown_y, FROM_CELL),
            _cell(r.x, TO_CELL), _cell(r.y, TO_CELL),
            _cell((r.thrown_yaw or 0.0) % 360, YAW_SPLIT),
        )  # fmt: skip
        groups[key].append(r)
    out = []
    for (kind, side, *cells), rows in groups.items():
        if len(rows) < MIN_THROWS:
            continue
        landed = [r.start_tick or r.throw_tick for r in rows]
        flight = [
            (land - r.thrown_tick) / (r.tickrate or 64)
            for r, land in zip(rows, landed, strict=True)
            if land and land >= r.thrown_tick
        ]
        pitch = [r.thrown_pitch for r in rows if r.thrown_pitch is not None]
        x, y, z = (statistics.median(getattr(r, f"thrown_{a}") for r in rows) for a in "xyz")
        yaw = statistics.median(r.thrown_yaw for r in rows if r.thrown_yaw is not None)
        aim = statistics.median(pitch) if pitch else 0.0
        teams = Counter(r[19] for r in rows if r[19])
        players = Counter(r[18] for r in rows if r[18])
        out.append(
            {
                # Stable while the same throws group the same way: a Strat's grenade keeps it.
                "key": f"{kind}.{side}." + ".".join(str(c) for c in cells),
                "type": kind,
                "side": side,
                "throws": len(rows),
                "from": Counter(r.thrown_place for r in rows if r.thrown_place).most_common(1)[0][0]
                if any(r.thrown_place for r in rows) else "",
                "to": Counter(r.place for r in rows if r.place).most_common(1)[0][0]
                if any(r.place for r in rows) else "",
                "x": round(x, 1), "y": round(y, 1), "z": round(z, 1),
                "pitch": round(aim, 2), "yaw": round(yaw, 2),
                "land": [round(statistics.median(r.x for r in rows)),
                         round(statistics.median(r.y for r in rows))],
                "flight": round(statistics.median(flight), 1) if flight else None,
                "teams": teams.most_common(3),
                "players": players.most_common(3),
                "setpos": f"setpos {x:.1f} {y:.1f} {z:.1f};setang {aim:.2f} {yaw:.2f} 0",
                "refs": [{"match": r.match_id, "map": r.map_number, "round": r.number}
                         for r in rows[:MAX_REFS]],
            }
        )  # fmt: skip
    out.sort(key=lambda lu: (-lu["throws"], lu["type"]))
    return out


def library(map_name: str) -> list[dict]:
    """Every lineup on the Map, the most thrown first."""
    key = f"lineups:v{LINEUPS_SCHEMA}:{map_name}:{pool_cache.parse_stamp()}"
    return pool_cache.remember(key, lambda: _build(map_name))
