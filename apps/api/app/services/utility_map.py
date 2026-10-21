"""A Team's utility on a Map and Side, where it lands and from where (docs/plans/09 VIZ-10).

Every smoke, molotov (``inferno``), flash and HE the Team threw there (schema 14 keeps where
the throw left the hand): where each landed and when, in seconds after freeze
end. Throws from the same spot to the same landing (the lineup library's cells,
SB-3) make the Team's lineups, :data:`MIN_THROWS` or more, with the median second
and the practice-server command that puts you on the spot.
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from sqlalchemy import select

from app.models import GameMap, GrenadeThrow, MatchMap, Round
from app.services import heatmap_groups, lineups
from app.services.dbctx import db

TYPES = ("smoke", "inferno", "flash", "he")  # GrenadeType values
MIN_THROWS = 2
MAX_LINEUPS = 12
MAX_REFS = 6


def _rows(team_id: int, map_name: str, side: str) -> list:
    team_col = Round.ct_team_id if side == "ct" else Round.t_team_id
    return list(
        db().execute(
            select(
                GrenadeThrow.type, GrenadeThrow.x, GrenadeThrow.y, GrenadeThrow.place,
                GrenadeThrow.thrown_x, GrenadeThrow.thrown_y, GrenadeThrow.thrown_z,
                GrenadeThrow.thrown_pitch, GrenadeThrow.thrown_yaw, GrenadeThrow.thrown_place,
                GrenadeThrow.start_tick, GrenadeThrow.throw_tick, Round.freeze_end_tick,
                Round.number, MatchMap.id, MatchMap.match_id, MatchMap.map_number,
                MatchMap.tickrate,
            )
            .join(Round, Round.id == GrenadeThrow.round_id)
            .join(MatchMap, MatchMap.id == Round.match_map_id)
            .join(GameMap, GameMap.id == MatchMap.game_map_id)
            .where(
                GameMap.name == map_name, team_col == team_id, GrenadeThrow.thrower_side == side,
                GrenadeThrow.type.in_(TYPES), GrenadeThrow.x.is_not(None),
            )
        )
    )  # fmt: skip


def _second(r) -> float | None:
    landed = r.start_tick or r.throw_tick
    if landed is None or landed < r.freeze_end_tick:
        return None
    return round((landed - r.freeze_end_tick) / (r.tickrate or 64), 1)


def build(team_id: int, map_name: str, side: str) -> dict:
    rows = _rows(team_id, map_name, side)
    throws = []
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        t = _second(r)
        has_from = r.thrown_x is not None and r.thrown_y is not None
        throws.append({
            "type": r.type, "land": [round(r.x, 1), round(r.y, 1)],
            "from": [round(r.thrown_x, 1), round(r.thrown_y, 1)] if has_from else None, "t": t,
        })  # fmt: skip
        if has_from:
            key = (
                r.type, lineups._cell(r.thrown_x, lineups.FROM_CELL),
                lineups._cell(r.thrown_y, lineups.FROM_CELL), lineups._cell(r.x, lineups.TO_CELL),
                lineups._cell(r.y, lineups.TO_CELL),
                lineups._cell((r.thrown_yaw or 0.0) % 360, lineups.YAW_SPLIT),
            )  # fmt: skip
            groups[key].append((r, t))
    found = []
    for (kind, *_cells), members in groups.items():
        if len(members) < MIN_THROWS:
            continue
        rs = [r for r, _t in members]
        seconds = [t for _r, t in members if t is not None]
        x, y, z = (statistics.median(getattr(r, f"thrown_{a}") for r in rs) for a in "xyz")
        pitches = [r.thrown_pitch for r in rs if r.thrown_pitch is not None]
        yaws = [r.thrown_yaw for r in rs if r.thrown_yaw is not None]
        aim = statistics.median(pitches) if pitches else 0.0
        yaw = statistics.median(yaws) if yaws else 0.0
        found.append({
            "type": kind, "throws": len(rs), "maps": len({r.id for r in rs}),
            "from": [round(x, 1), round(y, 1)],
            "land": [round(statistics.median(r.x for r in rs), 1),
                     round(statistics.median(r.y for r in rs), 1)],
            "from_place": _most(r.thrown_place for r in rs), "to_place": _most(r.place for r in rs),
            "t": round(statistics.median(seconds), 1) if seconds else None,
            "setpos": f"setpos {x:.1f} {y:.1f} {z:.1f};setang {aim:.2f} {yaw:.2f} 0",
            "refs": [{"match": r.match_id, "map": r.map_number, "round": r.number}
                     for r in rs[:MAX_REFS]],
        })  # fmt: skip
    found.sort(key=lambda lu: (-lu["throws"], lu["type"]))
    maps = list(
        db().scalars(select(MatchMap).where(MatchMap.id.in_({r.id for r in rows})))
    ) if rows else []  # fmt: skip
    return {
        "map": map_name,
        "side": side,
        "throws": throws,
        "lineups": found[:MAX_LINEUPS],
        "plate": heatmap_groups.plate(map_name),
        "labels": heatmap_groups.map_geometry(maps).get("labels") or [],
    }


def _most(values) -> str:
    seen = [v for v in values if v]
    return max(set(seen), key=seen.count) if seen else ""
