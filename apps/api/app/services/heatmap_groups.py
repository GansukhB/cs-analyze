"""Heatmaps as a filterable grid, drawn in the browser one selection at a time.

The positional data crosses four axes -- map, team, player, side -- and the
product is several hundred pictures, almost none of which are ever looked at.
So the *index* says which combinations hold any positions and how many, and a
selection's points are sent when somebody asks for them; the page draws the
heat over the map's overview itself.

Ported from cstat's ``hltv/services/heatmap_groups.py``, where the server drew
each picture with matplotlib and cached the PNG. Here nothing is drawn or kept
on the server (docs/adr/0002-tick-data-in-mysql.md): the points come from
``kill_events`` and the callout labels from the Tick Data's ``geometry``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy import and_, func, or_, select

from app.models import (
    GameMap,
    KillEvent,
    MapRoster,
    MatchMap,
    Player,
    Round,
    RoundSnapshot,
    SnapshotMoment,
    Team,
    TickDataset,
)
from app.services import radar, scouting
from app.services.dbctx import db

logger = logging.getLogger(__name__)

# Below this the page draws only the dots: a density fitted to a handful of
# points is normalised to its peak, so it glows as hot as one fitted to a hundred.
HEAT_MIN_POINTS = 5

SIDES = [{"key": "all", "label": "Both"}, {"key": "ct", "label": "CT"}, {"key": "t", "label": "T"}]
KINDS = [
    {
        "key": "kills",
        "label": "Kills from",
        "cmap": "inferno",
        "fields": ("attacker_x", "attacker_y", "attacker_z"),
    },
    {
        "key": "deaths",
        "label": "Dies at",
        "cmap": "viridis",
        "fields": ("victim_x", "victim_y", "victim_z"),
    },
    # VIZ-9: where they stand, not where they fight: every living Player 20 s
    # after freeze end (the Round's Setup snapshot).
    {"key": "positions", "label": "Stands at 20 s", "cmap": "inferno", "fields": ("x", "y", "z")},
]
_KIND = {k["key"]: k for k in KINDS}

ALL_PLAYERS = "all"
ALL_LEVELS = "all"


def key(map_name: str, team_id, player_id, side: str, kind: str) -> str:
    """The index key, shared verbatim with the page's grid."""
    return f"{map_name}|{team_id}|{player_id}|{side}|{kind}"


def level_axis(map_names: Iterable[str]) -> dict[str, list]:
    """``{map: ["upper", "lower"]}`` for the maps in a grid that have floors.

    Deliberately not part of :func:`key`: it is a render-time filter, so a floor
    with nothing in it comes back as an honest "nothing to draw".
    """
    return {
        name: [level["key"] for level in radar.levels(name)]
        for name in map_names
        if radar.levels(name)
    }


def build_index(my_team: Team, opponent: Team) -> dict:
    """Count every combination without drawing any of it.

    Two aggregate queries -- one per kind -- cover the whole grid, because a kill
    row carries both players and both sides at once.
    """
    teams = [my_team, opponent]
    session = db()
    map_ids = {m.id for t in teams for m in scouting.maps_for_team(t)}
    if not map_ids:
        return _empty_index()

    map_names = {
        m.id: m.game_map.name for t in teams for m in scouting.maps_for_team(t) if m.game_map
    }
    # A player can change club between maps, so the roster is read per map.
    team_of = {
        (map_id, pid): tid
        for map_id, pid, tid in session.execute(
            select(MapRoster.match_map_id, MapRoster.player_id, MapRoster.team_id).where(
                MapRoster.match_map_id.in_(map_ids)
            )
        )
    }
    names = dict(
        session.execute(
            select(Player.id, Player.name).where(Player.id.in_({pid for _, pid in team_of}))
        ).all()
    )

    counts: dict[str, int] = {}
    rosters: dict[int, set] = {t.id: set() for t in teams}
    wanted = {t.id for t in teams}
    for kind, actor, side_col, x_col in (
        ("kills", KillEvent.attacker_id, KillEvent.attacker_side, KillEvent.attacker_x),
        ("deaths", KillEvent.victim_id, KillEvent.victim_side, KillEvent.victim_x),
        ("positions", RoundSnapshot.player_id, RoundSnapshot.side, RoundSnapshot.x),
    ):
        source = RoundSnapshot if kind == "positions" else KillEvent
        query = (
            select(Round.match_map_id, actor, side_col, func.count(source.id))
            .join(Round, Round.id == source.round_id)
            .where(Round.match_map_id.in_(map_ids), actor.is_not(None), x_col.is_not(None))
            .group_by(Round.match_map_id, actor, side_col)
        )
        if kind == "positions":
            query = query.where(RoundSnapshot.moment == SnapshotMoment.SETUP)
        for map_id, player_id, side, n in session.execute(query):
            team_id = team_of.get((map_id, player_id))
            map_name = map_names.get(map_id)
            if team_id not in wanted or not map_name:
                continue
            rosters[team_id].add(player_id)
            side = (side or "").lower()
            for who in (player_id, ALL_PLAYERS):
                for s in {side, "all"} if side in ("ct", "t") else {"all"}:
                    k = key(map_name, team_id, who, s, kind)
                    counts[k] = counts.get(k, 0) + n

    if not counts:
        return _empty_index()
    present_maps = {k.split("|")[0] for k in counts}
    return {
        "maps": sorted(present_maps),
        "levels": level_axis(present_maps),
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "players": sorted(
                    ({"id": p, "name": names.get(p, str(p))} for p in rosters[t.id]),
                    key=lambda p: p["name"].lower(),
                ),
            }
            for t in teams
            if rosters[t.id]
        ],
        "sides": SIDES,
        "kinds": [{"key": k["key"], "label": k["label"]} for k in KINDS],
        "available": counts,
        "combinations": len(counts),
    }


def _empty_index() -> dict:
    return {
        "maps": [],
        "levels": {},
        "teams": [],
        "sides": SIDES,
        "kinds": [{"key": k["key"], "label": k["label"]} for k in KINDS],
        "available": {},
        "combinations": 0,
    }


def map_geometry(maps: Iterable[MatchMap]) -> dict:
    """The first of these maps' stored geometry (newest first), or an empty one."""
    maps = list(maps)
    found = dict(
        db()
        .execute(
            select(TickDataset.match_map_id, TickDataset.geometry).where(
                TickDataset.match_map_id.in_([m.id for m in maps])
            )
        )
        .all()
    )
    return next((found[m.id] for m in maps if (found.get(m.id) or {}).get("labels")), {})


def plate(map_name: str) -> dict | None:
    """What the page needs to composite the overview: both floors' images and
    the world rectangle the 1024 px images span. None for an uncalibrated map."""
    base = radar.plate(map_name)
    if base is None:
        return None
    spec = radar.calibration(map_name) or {}
    lower = radar.image_url(f"{radar.normalise(map_name)}_lower") if spec.get("lower") else None
    return {**base, "lower": lower}


# VIZ-9: when in the Round (seconds after freeze end, or after the plant) and
# on what the actor's Team had bought.
PHASES = {"0-15": (0, 15), "15-30": (15, 30), "30-60": (30, 60), "60+": (60, None)}
BUYS = {"full": ("full",), "light": ("eco", "force", "pistol")}
POOL_SAMPLE = 4000


def _narrow(query, actor_side, phase: str, buy: str, joined: bool = False):
    """``query`` on KillEvent/Round, kept to a phase of the Round and a buy;
    ``joined`` when it already joins MatchMap."""
    if phase == "post":
        query = query.where(
            Round.bomb_plant_tick.is_not(None), KillEvent.tick >= Round.bomb_plant_tick
        )
    elif phase in PHASES:
        lo, hi = PHASES[phase]
        rate = func.coalesce(MatchMap.tickrate, 64)
        if not joined:
            query = query.join(MatchMap, MatchMap.id == Round.match_map_id)
        # Added to the freeze end, never subtracted from the kill: both are
        # UNSIGNED on MySQL, and a kill in the freeze time would underflow.
        query = query.where(KillEvent.tick >= Round.freeze_end_tick + lo * rate)
        if hi is not None:
            query = query.where(KillEvent.tick < Round.freeze_end_tick + hi * rate)
    if buy in BUYS:
        bought = BUYS[buy]
        query = query.where(
            or_(
                and_(actor_side == "ct", Round.ct_buy.in_(bought)),
                and_(actor_side == "t", Round.t_buy.in_(bought)),
            )
        )
    return query


def points(*, map_name: str, team_id: int, player_id: str, side: str, kind: str,
           level: str = ALL_LEVELS, phase: str = "all", buy: str = "all",
           compare: bool = False) -> dict | None:  # fmt: skip
    """One cell of the grid: the positions to draw and what to draw them over.

    None when the selection has no usable positions -- the page says "nothing
    to draw" rather than showing an empty map. ``level`` narrows it to one floor
    of a two-floor map: a kill has one altitude, so it is a plain comparison.
    """
    spec = _KIND.get(kind)
    if spec is None:
        return None
    session = db()
    team = session.get(Team, team_id)
    if team is None:
        return None
    maps = [m for m in scouting.maps_for_team(team) if m.game_map and m.game_map.name == map_name]
    if not maps:
        return None

    split = radar.split_altitude(map_name)
    if level not in (radar.UPPER, radar.LOWER) or split is None:
        level = ALL_LEVELS
    who = str(player_id)

    standing = kind == "positions"
    source = RoundSnapshot if standing else KillEvent
    if standing:
        actor_id, actor_side = RoundSnapshot.player_id, RoundSnapshot.side
        phase = "all"  # the snapshot is one moment, 20 s in
    else:
        actor_id = KillEvent.attacker_id if kind == "kills" else KillEvent.victim_id
        actor_side = KillEvent.attacker_side if kind == "kills" else KillEvent.victim_side
    fx, fy, fz = (getattr(source, f) for f in spec["fields"])
    map_ids = [m.id for m in maps]
    query = (
        select(fx, fy, fz)
        .join(Round, Round.id == source.round_id)
        .where(Round.match_map_id.in_(map_ids), fx.is_not(None), fy.is_not(None))
        .order_by(source.id)
    )
    if standing:
        query = query.where(RoundSnapshot.moment == SnapshotMoment.SETUP)
    if who == ALL_PLAYERS:
        roster = select(MapRoster.player_id).where(
            MapRoster.match_map_id.in_(map_ids), MapRoster.team_id == team.id
        )
        query = query.where(actor_id.in_(roster))
        label = f"{team.name} — all players"
    else:
        try:
            player = session.get(Player, int(who))
        except ValueError:
            return None
        if player is None:
            return None
        query = query.where(actor_id == player.id)
        label = player.name
    if side in ("ct", "t"):
        query = query.where(actor_side == side)
    query = _narrow(query, actor_side, phase, buy)

    rows = session.execute(query).all()
    if level != ALL_LEVELS:
        # A kill with no altitude is dropped from a floor view: a point on a floor
        # picture is a claim about which floor it was on.
        rows = [r for r in rows if r[2] is not None and radar.level_at(split, r[2]) == level]
    if not rows:
        return None

    geometry = map_geometry(maps)
    labels = (
        geometry.get("labels")
        if level == ALL_LEVELS
        else (geometry.get("level_labels") or {}).get(level)
    ) or []
    verb = {"kills": "where they get their kills", "deaths": "where they die",
            "positions": "where they stand 20 s in"}[kind]  # fmt: skip
    side_label = {"ct": "CT side", "t": "T side"}.get(side, "both sides")
    floor_label = "" if level == ALL_LEVELS else f" · {level} floor"
    count = f"{len(rows)} position{'' if len(rows) == 1 else 's'}"
    heat = len(rows) >= HEAT_MIN_POINTS
    backdrop = plate(map_name)
    pool = None
    if compare:
        # Every other Team's on this Map, the same way: what is usual here (VIZ-9).
        others = (
            select(fx, fy)
            .join(Round, Round.id == source.round_id)
            .join(MatchMap, MatchMap.id == Round.match_map_id)
            .join(GameMap, GameMap.id == MatchMap.game_map_id)
            .where(GameMap.name == map_name, fx.is_not(None), fy.is_not(None))
            .where(actor_id.not_in(select(MapRoster.player_id).where(MapRoster.team_id == team.id)))
            .order_by(func.rand() if session.bind.dialect.name == "mysql" else func.random())
            .limit(POOL_SAMPLE)
        )  # fmt: skip
        if side in ("ct", "t"):
            others = others.where(actor_side == side)
        if standing:
            others = others.where(RoundSnapshot.moment == SnapshotMoment.SETUP)
        others = _narrow(others, actor_side, phase, buy, joined=True)
        pool = [[round(x, 1), round(y, 1)] for x, y in session.execute(others).all()]
    return {
        "pool": pool,
        "kind": kind,
        "cmap": spec["cmap"],
        "title": f"{label} — {verb}",
        "subtitle": f"{map_name} · {side_label}{floor_label} · {count}"
        + ("" if heat else " · too few for a heat layer"),
        "points": [[round(x, 1), round(y, 1)] for x, y, _z in rows],
        "heat": heat,
        "labels": labels,
        "level": "" if level == ALL_LEVELS else level,
        "plate": backdrop,
        "renderer": "map-background" if backdrop and backdrop.get("url") else "density",
    }
