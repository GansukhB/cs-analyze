"""Movement: the paths a team actually walks, and how often each one.

The same grid the heatmaps use -- map x team x player x side -- answering a
different question. A heatmap says *where* a player ends up; this says *how he
got there*, and what share of his rounds went that way.

* **Routes are stored per match, and a habit is not.** ``PlayerMapRoute`` holds
  one row per ``MatchMap``, so rows are grouped by ``(player, side, route_key)``
  across every parsed map of that name: the same map in several matches
  combines, *different* maps never do.
* **A share needs a denominator, and the honest one is narrow**: out of the
  rounds this player has a traced route for, reported alongside the number.

Ported from cstat's ``hltv/services/movement.py``. cstat drew a still picture
per selection with matplotlib and animated over a plate it rendered; here the
browser draws everything, over the same overview the round replay uses
(:func:`radar.plate`), and the walked tracks come from the walks cut from the
Tick Data at ingest (:func:`app.services.tickdata.walks`). Nothing is drawn or
kept on the server.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import undefer

from app.models import (
    GameMap,
    MatchMap,
    Player,
    PlayerMapPosition,
    PlayerMapRoute,
    PositionKind,
    Team,
)
from app.services import mn, radar, scouting, tickdata
from app.services.dbctx import db, total
from app.services.heatmap_groups import (
    ALL_LEVELS,
    ALL_PLAYERS,
    SIDES,
    key,
    level_axis,
    map_geometry,
)

logger = logging.getLogger(__name__)

# A path walked once is an accident, not a route.
MIN_ROUTE_ROUNDS = 2
MIN_INDEX_ROUNDS = 4

# How many paths to draw: one player can carry his whole repertoire, the
# all-players view gets each man's top few or the picture stops being readable.
MAX_ROUTES_ONE = 6
MAX_ROUTES_EACH = 2
MAX_ROUTES_TOTAL = 12
# Floors for the pooled view only: 25% of eight traced rounds is two rounds
# wearing a percentage.
MIN_SHARE_POOLED = 0.15
MIN_TRACED_POOLED = 10

KINDS = [{"key": "routes", "label": "Явдаг зам"}]

# --- does this path suit this player -----------------------------------------
# A route's raw K-D is a property of the ground as much as the man, so it is set
# against what *other* players get on the same (map, side, route_key). The bars
# are one standard deviation of that delta over cstat's 612 comparable pairs.
FIT_SUITS = 0.34
FIT_MISFITS = -0.34
FIT_MIN_ROUNDS = 4
FIT_MIN_POOL_ROUNDS = 10
PRIOR_ROUNDS = 3

MAX_PLACES = 9

# One colour per player, picked for separation on the dark floor (cstat's set).
PLAYER_COLOURS = ["#6e8ef3", "#e8b93a", "#4fb286", "#e0685f", "#b98ae0", "#57c4d8", "#d98cc0",
                  "#8fb339"]  # fmt: skip

# A callout counts as being on a floor at this share of its own ticks (Nuke:
# Vents 8%, Ramp 27%, Secret 43% downstairs; every other room under 3%).
PLACE_FLOOR_SHARE = 0.15
# The pooled share bar on a floor view is scaled by how much of the map that
# floor holds, floored so an empty floor cannot drop it to zero.
MIN_FLOOR_WEIGHT = 0.02


def _maps(team: Team, map_name: str) -> list[MatchMap]:
    return [m for m in scouting.maps_for_team(team) if m.game_map and m.game_map.name == map_name]


def build_index(my_team: Team, opponent: Team) -> dict:
    """Count every combination without drawing any of it (one aggregate query)."""
    teams = [my_team, opponent]
    maps = {m.id: m for t in teams for m in scouting.maps_for_team(t)}
    if not maps:
        return _empty_index()
    map_names = {mid: m.game_map.name for mid, m in maps.items() if m.game_map}
    wanted = {t.id for t in teams}
    session = db()

    counts: dict[str, int] = {}
    rosters: dict[int, set] = {t.id: set() for t in teams}
    R = PlayerMapRoute
    for map_id, team_id, player_id, side, n in session.execute(
        select(R.match_map_id, R.team_id, R.player_id, R.side, total(R.rounds))
        .where(R.match_map_id.in_(list(maps)), R.team_id.in_(wanted))
        .group_by(R.match_map_id, R.team_id, R.player_id, R.side)
    ):
        map_name = map_names.get(map_id)
        n = int(n or 0)
        if not map_name or not n:
            continue
        rosters[team_id].add(player_id)
        side = (side or "").lower()
        for who in (player_id, ALL_PLAYERS):
            for s in {side, "all"} if side in ("ct", "t") else {"all"}:
                k = key(map_name, team_id, who, s, "routes")
                counts[k] = counts.get(k, 0) + n

    counts = {k: n for k, n in counts.items() if n >= MIN_INDEX_ROUNDS}
    if not counts:
        return _empty_index()
    names = dict(
        session.execute(
            select(Player.id, Player.name).where(
                Player.id.in_({p for players in rosters.values() for p in players})
            )
        ).all()
    )
    present_maps = sorted({k.split("|")[0] for k in counts})
    return {
        "maps": present_maps,
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
        "kinds": KINDS,
        "available": counts,
        "combinations": len(counts),
    }


def _empty_index() -> dict:
    return {
        "maps": [],
        "levels": {},
        "teams": [],
        "sides": SIDES,
        "kinds": KINDS,
        "available": {},
        "combinations": 0,
    }


def routes(
    map_name: str,
    team: Team,
    player_id: str,
    side: str,
    *,
    keep=None,
    min_share: float | None = None,
) -> list[dict]:
    """This selection's paths, combined across matches and scored by share.

    ``share`` is of every round traced for that player under the same filter.
    ``keep`` narrows eligibility **before** the per-player cap, so a floor view
    is not the leftovers of an upstairs ranking.
    """
    maps = _maps(team, map_name)
    if not maps:
        return []
    query = select(PlayerMapRoute, Player.name).join(Player, Player.id == PlayerMapRoute.player_id)
    query = query.where(
        PlayerMapRoute.match_map_id.in_([m.id for m in maps]), PlayerMapRoute.team_id == team.id
    )
    if side in ("ct", "t"):
        query = query.where(PlayerMapRoute.side == side)
    if str(player_id) != ALL_PLAYERS:
        try:
            query = query.where(PlayerMapRoute.player_id == int(player_id))
        except ValueError:
            return []

    grouped: dict[tuple, dict] = {}
    played: dict[int, int] = {}
    for row, player_name in db().execute(query.order_by(PlayerMapRoute.id)):
        rounds = int(row.rounds or 0)
        if not rounds:
            continue
        played[row.player_id] = played.get(row.player_id, 0) + rounds
        # Side stays in the key: the same callouts from opposite spawns are two
        # different journeys.
        gkey = (row.player_id, row.side, row.route_key)
        entry = grouped.get(gkey)
        if entry is None:
            entry = grouped[gkey] = {
                "player_id": row.player_id,
                "player": player_name,
                "side": row.side,
                "route_key": row.route_key,
                "places": list(row.places or []),
                "rounds": 0,
                "kills": 0,
                "deaths": 0,
                "rounds_won": 0,
                "_paths": [],
            }
        entry["rounds"] += rounds
        entry["kills"] += int(row.kills or 0)
        entry["deaths"] += int(row.deaths or 0)
        entry["rounds_won"] += int(row.rounds_won or 0)
        entry["_paths"].append((rounds, row.path or []))

    out = []
    for entry in grouped.values():
        if entry["rounds"] < MIN_ROUTE_ROUNDS:
            continue
        path = _mean_path(entry.pop("_paths"))
        if len(path) < 2:
            continue
        traced = played.get(entry["player_id"]) or entry["rounds"]
        entry["path"] = path
        entry["traced_rounds"] = traced
        entry["share"] = entry["rounds"] / traced
        entry["net_per_round"] = _shrunk_net(entry["kills"], entry["deaths"], entry["rounds"])
        out.append(entry)

    if keep is not None:
        out = [r for r in out if keep(r)]
    pooled = str(player_id) == ALL_PLAYERS
    if pooled:
        bar = MIN_SHARE_POOLED if min_share is None else min_share
        out = [r for r in out if r["share"] >= bar and r["traced_rounds"] >= MIN_TRACED_POOLED]

    out.sort(key=lambda r: (-r["rounds"], r["player"]))
    cap = MAX_ROUTES_EACH if pooled else MAX_ROUTES_ONE
    kept: dict[int, int] = {}
    picked = []
    for route in out:
        seen = kept.get(route["player_id"], 0)
        if seen >= cap or (pooled and len(picked) >= MAX_ROUTES_TOTAL):
            continue
        kept[route["player_id"]] = seen + 1
        picked.append(route)
    return picked


def _mean_path(weighted) -> list[dict]:
    """One path from the same route seen in several matches, weighted by rounds."""
    usable = [(w, p) for w, p in weighted if p]
    if not usable:
        return []
    length = min(len(p) for _, p in usable)
    if length < 2:
        return []
    weight = sum(w for w, _ in usable)
    return [
        {
            "place": usable[0][1][i].get("place", ""),
            "x": sum(w * float(p[i].get("x") or 0.0) for w, p in usable) / weight,
            "y": sum(w * float(p[i].get("y") or 0.0) for w, p in usable) / weight,
        }
        for i in range(length)
    ]


def route_fit(map_name: str, drawn: list[dict]) -> None:
    """Attach to each route what the same ground yields for everybody else.

    The pool is every parsed row on the same (map, side, route_key), the player
    himself excluded. A route nobody else has walked enough is ``"unknown"``.
    """
    if not drawn:
        return
    wanted = {(r["side"], r["route_key"]) for r in drawn}
    R = PlayerMapRoute
    pool: dict[tuple, dict[int, list[int]]] = {}
    for side, route_key, pid, rounds, kills, deaths, won in db().execute(
        select(R.side, R.route_key, R.player_id, R.rounds, R.kills, R.deaths, R.rounds_won)
        .join(MatchMap, MatchMap.id == R.match_map_id)
        .join(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(GameMap.name == map_name, R.route_key.in_({k for _, k in wanted}))
    ):
        gkey = (side, route_key)
        if gkey not in wanted:
            continue
        acc = pool.setdefault(gkey, {}).setdefault(pid, [0, 0, 0, 0])
        acc[0] += rounds or 0
        acc[1] += kills or 0
        acc[2] += deaths or 0
        acc[3] += won or 0

    for route in drawn:
        mine_net = _shrunk_net(route["kills"], route["deaths"], route["rounds"])
        win_rate = (route["rounds_won"] / route["rounds"]) if route["rounds"] else None
        fit = {
            "net": mine_net,
            "win_rate": win_rate,
            "pool_rounds": 0,
            "pool_players": 0,
            "pool_net": None,
            "pool_win_rate": None,
            "delta": None,
            "win_delta": None,
            "verdict": "unknown",
        }
        others = {
            pid: v
            for pid, v in pool.get((route["side"], route["route_key"]), {}).items()
            if pid != route["player_id"]
        }
        rounds = sum(v[0] for v in others.values())
        if rounds >= FIT_MIN_POOL_ROUNDS and route["rounds"] >= FIT_MIN_ROUNDS:
            fit["pool_rounds"] = rounds
            fit["pool_players"] = len(others)
            fit["pool_net"] = _shrunk_net(
                sum(v[1] for v in others.values()), sum(v[2] for v in others.values()), rounds
            )
            fit["pool_win_rate"] = sum(v[3] for v in others.values()) / rounds
            fit["delta"] = round(mine_net - fit["pool_net"], 3)
            if win_rate is not None:
                fit["win_delta"] = round(win_rate - fit["pool_win_rate"], 3)
            fit["verdict"] = (
                "suits"
                if fit["delta"] >= FIT_SUITS
                else "misfits"
                if fit["delta"] <= FIT_MISFITS
                else "even"
            )
        route["fit"] = fit


def _shrunk_net(kills: int, deaths: int, rounds: int) -> float:
    return round((kills - deaths) / (rounds + PRIOR_ROUNDS), 3)


def _player_filter(column, player_id):
    if str(player_id) == ALL_PLAYERS:
        return None
    return column == int(player_id)


def place_traffic(map_name: str, team: Team, player_id: str, side: str, keep=None) -> list[dict]:
    """Which callouts this selection moves through, and what happens there.

    Passes are counted per round, not per visit. Kills and deaths come from
    ``PlayerMapPosition``, the same rows the breakdown reads.
    """
    maps = _maps(team, map_name)
    if not maps:
        return []
    map_ids = [m.id for m in maps]
    try:
        r_who = _player_filter(PlayerMapRoute.player_id, player_id)
        p_who = _player_filter(PlayerMapPosition.player_id, player_id)
    except ValueError:
        return []
    session = db()

    route_q = select(PlayerMapRoute.places, PlayerMapRoute.rounds).where(
        PlayerMapRoute.match_map_id.in_(map_ids), PlayerMapRoute.team_id == team.id
    )
    pos_q = select(PlayerMapPosition.kind, PlayerMapPosition.place, total(PlayerMapPosition.count))
    pos_q = pos_q.where(
        PlayerMapPosition.match_map_id.in_(map_ids), PlayerMapPosition.team_id == team.id
    )
    if side in ("ct", "t"):
        route_q = route_q.where(PlayerMapRoute.side == side)
        pos_q = pos_q.where(PlayerMapPosition.side == side)
    if r_who is not None:
        route_q = route_q.where(r_who)
        pos_q = pos_q.where(p_who)

    passes: dict[str, int] = {}
    for places, rounds in session.execute(route_q):
        rounds = int(rounds or 0)
        if not rounds:
            continue
        for place in {p for p in (places or []) if p}:
            passes[place] = passes.get(place, 0) + rounds
    if not passes:
        return []

    kills: dict[str, int] = {}
    deaths: dict[str, int] = {}
    for kind, place, n in session.execute(
        pos_q.group_by(PlayerMapPosition.kind, PlayerMapPosition.place)
    ):
        if kind == PositionKind.KILL_FROM:
            kills[place] = kills.get(place, 0) + int(n or 0)
        elif kind == PositionKind.DEATH_AT:
            deaths[place] = deaths.get(place, 0) + int(n or 0)

    if keep is not None:
        passes = {place: n for place, n in passes.items() if place in keep}
        if not passes:
            return []
    out = []
    for place, n in sorted(passes.items(), key=lambda kv: -kv[1])[:MAX_PLACES]:
        k, d = kills.get(place, 0), deaths.get(place, 0)
        out.append(
            {
                "place": place,
                "passes": n,
                "kills": k,
                "deaths": d,
                "kills_per10": round(10 * k / n, 2),
                "deaths_per10": round(10 * d / n, 2),
                "net_per10": round(10 * (k - d) / n, 2),
            }
        )
    return out


def _place_events(maps, team: Team, side: str) -> dict[tuple, list[int]]:
    """``{(player_id, place): [kills, deaths]}`` -- per player, for the animation."""
    P = PlayerMapPosition
    query = select(P.player_id, P.kind, P.place, total(P.count)).where(
        P.match_map_id.in_([m.id for m in maps]), P.team_id == team.id
    )
    if side in ("ct", "t"):
        query = query.where(P.side == side)
    out: dict[tuple, list[int]] = {}
    for pid, kind, place, n in db().execute(query.group_by(P.player_id, P.kind, P.place)):
        acc = out.setdefault((pid, place), [0, 0])
        if kind == PositionKind.KILL_FROM:
            acc[0] += int(n or 0)
        elif kind == PositionKind.DEATH_AT:
            acc[1] += int(n or 0)
    return out


def plate(map_name: str, geometry: dict, paths: list[dict]) -> dict | None:
    """The overview the browser animates over, with callouts and per-floor images.

    A map with no shipped overview still animates, on a dark floor whose
    rectangle comes from the calibration, or failing that from the routes.
    """
    base = radar.plate(map_name)
    if base is None:
        xs = [s["x"] for r in paths for s in r["path"]]
        ys = [s["y"] for r in paths for s in r["path"]]
        if not xs:
            return None
        pad = max(max(xs) - min(xs), max(ys) - min(ys), 1.0) * 0.08
        span = max(max(xs) - min(xs), max(ys) - min(ys)) + 2 * pad
        x0, y0 = min(xs) - pad, min(ys) - pad
        base = {"url": None, "width": 1024, "height": 1024,
                "extent": [x0, x0 + span, y0, y0 + span]}  # fmt: skip
    levels = []
    for level in radar.levels(map_name):
        url = radar.image_url(level["image"])
        if url:
            labels = (geometry.get("level_labels") or {}).get(level["key"]) or []
            levels.append({"key": level["key"], "url": url, "labels": labels})
    return {
        **base,
        "labels": geometry.get("labels") or [],
        "levels": levels if len(levels) > 1 else [],
    }


def scene(
    map_name: str,
    team: Team,
    player_id: str,
    side: str,
    paths: list[dict],
    level: str | None = None,
    geometry=None,
) -> dict | None:
    """Everything the browser needs to animate the walk, in world coordinates.

    Each callout on a route carries this player's kills and deaths *at that
    callout* over every round he played on this map and side -- "walking this way
    takes him through ground where he is 6-1", never "on this route he went 6-1".
    """
    maps = _maps(team, map_name)
    if not maps or not paths:
        return None
    if geometry is None:
        geometry = map_geometry(maps)
    backdrop = plate(map_name, geometry, paths)
    if backdrop is None:
        return None
    floor = next((lv for lv in backdrop["levels"] if lv["key"] == level), None)
    if floor is not None:
        backdrop = {**backdrop, "url": floor["url"], "labels": floor["labels"]}

    events = _place_events(maps, team, side)
    pooled = len({r["player_id"] for r in paths}) > 1
    out = []
    for i, route in enumerate(sorted(paths, key=lambda r: -r["share"])):
        steps, seen = [], set()
        for step in route["path"]:
            place = step.get("place", "")
            kills, deaths = events.get((route["player_id"], place), (0, 0))
            # The tally belongs to the callout, not the visit: only the first
            # arrival carries it.
            steps.append(
                {
                    "place": place,
                    "x": step["x"],
                    "y": step["y"],
                    "kills": kills,
                    "deaths": deaths,
                    "counted": place not in seen,
                }
            )
            seen.add(place)
        if len(steps) < 2:
            continue
        fit = route.get("fit") or {}
        out.append(
            {
                "route_key": route["route_key"],
                "side": route["side"],
                "player": route["player"],
                "share": round(route["share"], 4),
                "rounds": route["rounds"],
                "traced": route["traced_rounds"],
                "kills": route["kills"],
                "deaths": route["deaths"],
                "verdict": fit.get("verdict", "unknown"),
                "delta": fit.get("delta"),
                "colour": PLAYER_COLOURS[i % len(PLAYER_COLOURS)],
                "steps": steps,
            }
        )
    if not out:
        return None
    if pooled:
        by_player: dict[str, str] = {}
        for route in out:
            by_player.setdefault(
                route["player"], PLAYER_COLOURS[len(by_player) % len(PLAYER_COLOURS)]
            )
        for route in out:
            route["colour"] = by_player[route["player"]]
    return {
        "plate": backdrop,
        "routes": out,
        "labels": backdrop.get("labels") or [],
        "pooled": pooled,
    }


def floor_places(geometry: dict | None, level: str | None) -> set | None:
    """The callouts on ``level``, or None when that cannot be decided (show all)."""
    place_levels = (geometry or {}).get("place_levels") or {}
    if not level or not place_levels:
        return None
    return {
        place for place, shares in place_levels.items() if shares.get(level, 0) >= PLACE_FLOOR_SHARE
    }


def _floor_bar(geometry: dict | None, level: str | None) -> float | None:
    share = ((geometry or {}).get("level_share") or {}).get(level) if level else None
    if share is None:
        return None
    return MIN_SHARE_POOLED * max(float(share), MIN_FLOOR_WEIGHT)


def selection(
    map_name: str, team: Team, player_id: str, side: str, level: str | None = None
) -> dict:
    """Which routes this cell draws, and what the floor filter decided.

    One definition for the renderer and the tracks endpoint, so the animation
    never upgrades a set of routes the picture does not contain.
    """
    maps = _maps(team, map_name)
    if not maps:
        return {"maps": [], "geometry": None, "places": None, "paths": []}
    geometry = map_geometry(maps) if level else None
    places = floor_places(geometry, level)
    paths = routes(
        map_name,
        team,
        str(player_id),
        side,
        keep=None if places is None else (lambda r: any(p in places for p in r["places"])),
        min_share=_floor_bar(geometry, level),
    )
    return {"maps": maps, "geometry": geometry, "places": places, "paths": paths}


def tracks(map_name: str, team: Team, player_id: str, side: str,
           paths: list[dict] | None = None, level: str | None = None) -> dict | None:  # fmt: skip
    """Real trajectories for the drawn routes, one representative round each.

    The walks were cut from each map's Tick Data at ingest; this merges them
    across the team's maps of that name, picks the most typical walk of each
    route (its medoid, never an average) and marks where the callout changes,
    which is where the animation pops a tally -- the doorway he came through.
    """
    from app.models import TickDataset

    maps = _maps(team, map_name)
    if not maps:
        return None
    if paths is None:
        paths = selection(map_name, team, player_id, side, level)["paths"]
    drawn = paths
    if not drawn:
        return None
    by_id = {
        d.match_map_id: d
        for d in db().scalars(
            select(TickDataset)
            .options(undefer(TickDataset.walks))
            .where(TickDataset.match_map_id.in_([m.id for m in maps]))
        )
    }
    walks = tickdata.load_walks(by_id[m.id] for m in maps if m.id in by_id)
    out = []
    for route in drawn:
        found = walks.get(f"{route['player_id']}|{route['side']}|{route['route_key']}")
        if not found:
            continue
        pick = found[tickdata.medoid([w["shape"] for w in found])]
        steps, seen = [], None
        for i, place in enumerate(pick["places"]):
            if place != seen:
                steps.append({"i": i, "place": place})
                seen = place
        walked = {
            "route_key": route["route_key"],
            "player": route["player"],
            "side": route["side"],
            "rounds_seen": len(found),
            "points": pick["points"],
            "steps": steps,
        }
        if "lvl" in pick:
            walked["lvl"] = pick["lvl"]
        out.append(walked)
    return {"tracks": out} if out else None


def render(*, map_name: str, team_id: int, player_id: str, side: str, kind: str = "routes",
           level: str = ALL_LEVELS) -> dict | None:  # fmt: skip
    """One cell of the movement grid: the scene to animate and the tables under it.

    ``level`` narrows every part of the cell to one floor at once -- the routes,
    the callouts in the table, and the plate. None when there is nothing worth
    drawing, so the page can say so.
    """
    if kind != "routes":
        return None
    team = db().get(Team, team_id)
    if team is None:
        return None
    if level not in (radar.UPPER, radar.LOWER) or radar.split_altitude(map_name) is None:
        level = ALL_LEVELS
    floor = None if level == ALL_LEVELS else level
    who = str(player_id)

    chosen = selection(map_name, team, who, side, floor)
    maps, geometry = chosen["maps"], chosen["geometry"]
    keep_places, paths = chosen["places"], chosen["paths"]
    if not paths:
        return None
    walked = tracks(map_name, team, who, side, paths, floor)
    route_fit(map_name, paths)
    places = place_traffic(map_name, team, who, side, keep=keep_places)

    words = mn.MOVEMENT
    label = f"{team.name} — {words['all_players']}" if who == ALL_PLAYERS else paths[0]["player"]
    # Each man's share is out of his own traced rounds, so the pooled denominator
    # is the sum over the men drawn.
    traced = sum({r["player_id"]: r["traced_rounds"] for r in paths}.values())
    subtitle = words["subtitle"].format(
        map=map_name,
        side=words["sides"].get(side, words["sides"]["all"]),
        routes=len(paths),
        traced=traced,
    )
    if floor is not None:
        subtitle += words["floor_suffix"].format(floor=words["floors"][floor])
    if who == ALL_PLAYERS:
        subtitle += words["players_suffix"].format(n=len({r["player_id"] for r in paths}))

    geometry = geometry or map_geometry(maps)
    animation = scene(map_name, team, who, side, paths, floor, geometry=geometry)
    if animation is None:
        return None
    if walked:
        animation["tracks"] = walked["tracks"]
    return {
        "title": words["title"].format(who=label),
        "subtitle": subtitle,
        "routes": len(paths),
        "renderer": "movement-map" if animation["plate"].get("url") else "density",
        "tables": [t for t in (_fit_table(paths, words), _places_table(places, words)) if t],
        "scene": animation,
    }


# -- the numbers under the picture -------------------------------------------
def _pct(value) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _signed(value, nd: int = 2) -> str:
    return "—" if value is None else f"{value:+.{nd}f}"


def _cell(text, tone=None) -> dict:
    return {"v": text, "tone": tone}


def _fit_table(paths: list[dict], words: dict) -> dict | None:
    """One row per drawn route: how often, what it yields, and whether it fits."""
    if not paths:
        return None
    pooled = len({r["player_id"] for r in paths}) > 1
    rows = []
    for r in paths:
        fit = r.get("fit") or {}
        verdict = fit.get("verdict", "unknown")
        tone = {"suits": "good", "misfits": "crit"}.get(verdict)
        pool_net, pool_rounds = fit.get("pool_net"), fit.get("pool_rounds")
        cells = [
            _cell(words[verdict], tone),
            _cell(_signed(fit.get("delta")), tone),
            _cell(_pct(r["share"])),
            _cell(f"{r['rounds']}/{r['traced_rounds']}"),
            _cell(f"{r['kills']}–{r['deaths']}"),
            _cell(_signed(fit.get("net"))),
            _cell("—" if pool_net is None else f"{pool_net:+.2f} ({pool_rounds}р)"),
            _cell(f"{_pct(fit.get('win_rate'))} ({_pct(fit.get('pool_win_rate'))})"),
            _cell(" → ".join(r["places"])),
        ]
        if pooled:
            cells.insert(0, _cell(r["player"]))
        rows.append(cells)
    columns = [
        {"label": words["col_verdict"]},
        {"label": words["col_delta"], "num": True},
        {"label": words["col_share"], "num": True},
        {"label": words["col_rounds"], "num": True},
        {"label": words["col_kd"], "num": True},
        {"label": words["col_net"], "num": True},
        {"label": words["col_pool"], "num": True},
        {"label": words["col_win"], "num": True},
        {"label": words["col_route"]},
    ]
    if pooled:
        columns.insert(0, {"label": words["col_player"]})
    compared = [r for r in paths if (r.get("fit") or {}).get("delta") is not None]
    note = (
        words["fit_note"].format(good=f"+{FIT_SUITS:.2f}", bad=f"{FIT_MISFITS:.2f}")
        if compared
        else words["fit_thin"]
    )
    return {"title": words["fit_title"], "note": note, "columns": columns, "rows": rows}


def _places_table(places: list[dict], words: dict) -> dict | None:
    """Where the selection actually spends its rounds, and what happens there."""
    if not places:
        return None
    rows = []
    for p in places:
        tone = "good" if p["net_per10"] >= 1.0 else "crit" if p["net_per10"] <= -1.0 else None
        rows.append(
            [
                _cell(p["place"]),
                _cell(str(p["passes"])),
                _cell(f"{p['kills_per10']:.1f}"),
                _cell(f"{p['deaths_per10']:.1f}"),
                _cell(_signed(p["net_per10"], 1), tone),
            ]
        )
    return {
        "title": words["places_title"],
        "note": words["places_note"],
        "columns": [
            {"label": words["col_place"]},
            {"label": words["col_passes"], "num": True},
            {"label": words["col_kills_10"], "num": True},
            {"label": words["col_deaths_10"], "num": True},
            {"label": words["col_place_net"], "num": True},
        ],
        "rows": rows,
    }
