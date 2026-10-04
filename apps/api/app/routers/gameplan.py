"""The game plan: pick two teams, then one panel per URL.

Ported from cstat's ``gameplan_pick``, ``gameplan`` and the three grid views.
The page asks for its header once and then one panel at a time, so a tab only
pays for what it shows (see :class:`app.services.gameplan.Report`). A computed
panel is kept in Redis under the parse stamp: the first visit computes, every
later one -- and every tab the page prefetched on hover -- is a cache read, and
a new parse makes all of them recompute.

Each side's Lineup (CONTEXT.md) rides along as a query parameter of Steam ids,
so a picked plan is a link like any other; it joins the cache key, and a side
left out keeps the five from the Team's most recent parsed Match.
"""

import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from redis.exceptions import RedisError

from app.cache import get_cache
from app.deps import CurrentUser, DbSession
from app.models import Player, Team
from app.schemas import (
    GameplanHeader,
    GameplanLineup,
    GameplanLineups,
    GameplanPanel,
    GameplanPick,
    LineupMember,
    LineupPlayer,
    LineupPlayers,
    TeamRef,
)
from app.services import (
    dbctx,
    gameplan,
    gameplan_view,
    heatmap_groups,
    lineup,
    movement,
    playbook_view,
    radar,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gameplan", tags=["gameplan"])

CACHE_TTL = 7 * 24 * 3600
LEVELS = {heatmap_groups.ALL_LEVELS, radar.UPPER, radar.LOWER}
SIDES = {"all", "ct", "t"}


def _cache_get(key: str) -> dict | None:
    try:
        raw = get_cache().get(key)
    except RedisError:
        logger.warning("game plan cache unavailable; computing %s", key)
        return None
    return json.loads(raw) if raw else None


def _cache_set(key: str, value: dict) -> None:
    try:
        get_cache().set(key, json.dumps(value, default=str), ex=CACHE_TTL)
    except RedisError:
        logger.warning("could not cache %s", key)


def _fixture(db, mine: int, theirs: int) -> tuple[Team, Team]:
    my_team, opponent = db.get(Team, mine), db.get(Team, theirs)
    if my_team is None or opponent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team")
    if my_team.id == opponent.id:
        # The whole plan is the difference between the two sides.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick two different teams")
    return my_team, opponent


def _lineup_query():
    # One Query per parameter: FastAPI keeps the alias on it, so a shared one
    # would read the same parameter twice.
    return Query(
        "",
        pattern=r"^(\d{1,20}(,\d{1,20}){0,4})?$",
        description="Up to five Steam ids, comma-separated; empty for the most recent five.",
    )


def _lineups(db, my_team: Team, opponent: Team, mine: str, theirs: str):
    """The two picked Lineups as Players, checked: five at most, known, on one side only."""
    sides = []
    for raw in (mine, theirs):
        ids = [int(s) for s in raw.split(",") if s]
        if len(set(ids)) != len(ids):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A player is picked twice")
        try:
            with dbctx.using(db):
                sides.append(lineup.resolve(ids))
        except KeyError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown player {exc}") from None
    if {p.id for p in sides[0]} & {p.id for p in sides[1]}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A player cannot be on both sides")
    return sides[0], sides[1]


def _lineup_out(team: Team) -> GameplanLineup:
    picked = lineup.chosen(team)
    newcomers = {p.id for p in lineup.newcomers(team)}

    def member(p: Player) -> LineupMember:
        found = lineup.elsewhere(p) if p.id in newcomers else None
        return LineupMember(
            steamid=str(p.steamid), name=p.name, elsewhere=found[0].name if found else ""
        )

    players = picked if picked is not None else lineup.latest_five(team)
    return GameplanLineup(picked=picked is not None, players=[member(p) for p in players])


@router.get("/teams")
def pick(db: DbSession, _: CurrentUser) -> GameplanPick:
    """Every team with parsed maps, and how many: the picker's list."""
    with dbctx.using(db):
        return GameplanPick(**gameplan_view.pick())


@router.get("/teams/{team_id}/players")
def team_players(team_id: int, db: DbSession, _: CurrentUser) -> LineupPlayers:
    """Who has played for this team, most recent first: a Lineup's candidates."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team")
    with dbctx.using(db):
        return LineupPlayers(players=[LineupPlayer(**p) for p in lineup.candidates(team)])


@router.get("/players")
def search_players(
    db: DbSession, _: CurrentUser, q: str = Query(min_length=2, max_length=64)
) -> LineupPlayers:
    """Any player by a name they played under: a stand-in or a new signing."""
    with dbctx.using(db):
        return LineupPlayers(players=[LineupPlayer(**p) for p in lineup.search(q)])


@router.get("/{mine}/vs/{theirs}")
def header(
    mine: int,
    theirs: int,
    db: DbSession,
    _: CurrentUser,
    my_lineup: str = _lineup_query(),
    their_lineup: str = _lineup_query(),
) -> GameplanHeader:
    """The page header, the tab list and both Lineups, on every tab."""
    my_team, opponent = _fixture(db, mine, theirs)
    my_five, their_five = _lineups(db, my_team, opponent, my_lineup, their_lineup)
    picked = {my_team.id: my_five, opponent.id: their_five}
    with dbctx.using(db), lineup.using(picked):
        stamp = gameplan_view.stamp()
        part = lineup.cache_part(my_five, their_five)
        key = f"gp:v5:{my_team.id}:{opponent.id}{part}:header:{stamp}"
        cached = _cache_get(key)
        if cached is None:
            report = gameplan.build(my_team, opponent)
            cached = {
                "lede": report["lede"],
                "tabs": gameplan_view.tabs(
                    heatmap_groups.build_index(my_team, opponent),
                    movement.build_index(my_team, opponent),
                ),
            }
            _cache_set(key, cached)
        lineups = GameplanLineups(mine=_lineup_out(my_team), theirs=_lineup_out(opponent))
    return GameplanHeader(
        my_team=TeamRef(id=my_team.id, name=my_team.name),
        opponent=TeamRef(id=opponent.id, name=opponent.name),
        lede=cached["lede"],
        tabs=cached["tabs"],
        default_tab=gameplan_view.DEFAULT_TAB,
        stamp=stamp,
        lineups=lineups,
    )


@router.get("/{mine}/vs/{theirs}/s/{tab}")
def panel(
    mine: int,
    theirs: int,
    tab: str,
    db: DbSession,
    _: CurrentUser,
    my_lineup: str = _lineup_query(),
    their_lineup: str = _lineup_query(),
) -> GameplanPanel:
    """One panel's data, computed once per parse stamp and pair of Lineups."""
    if tab not in gameplan_view.TAB_KEYS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such section: {tab}")
    my_team, opponent = _fixture(db, mine, theirs)
    my_five, their_five = _lineups(db, my_team, opponent, my_lineup, their_lineup)
    started = time.perf_counter()
    with dbctx.using(db), lineup.using({my_team.id: my_five, opponent.id: their_five}):
        stamp = gameplan_view.stamp()
        part = lineup.cache_part(my_five, their_five)
        key = f"gp:v5:{my_team.id}:{opponent.id}{part}:{tab}:{stamp}"
        data = _cache_get(key)
        hit = data is not None
        if data is None:
            report = gameplan.build(my_team, opponent)
            grids = {}
            if tab == "heatmaps":
                grids["heatmaps"] = heatmap_groups.build_index(my_team, opponent)
            elif tab == "movement":
                grids["movement"] = movement.build_index(my_team, opponent)
            data = gameplan_view.panel(tab, report, my_team, opponent, **grids)
            data = json.loads(json.dumps(data, default=str))
            _cache_set(key, data)
    return GameplanPanel(
        tab=tab,
        stamp=stamp,
        cached=hit,
        ms=round((time.perf_counter() - started) * 1000, 1),
        data=data,
    )


@router.get("/{mine}/vs/{theirs}/playbook/{map_name}")
def playbook(
    mine: int,
    theirs: int,
    map_name: str,
    db: DbSession,
    _: CurrentUser,
    my_lineup: str = _lineup_query(),
    their_lineup: str = _lineup_query(),
) -> GameplanPanel:
    """One Map's Playbook for the «Юу хийх» tab, computed once per parse stamp."""
    if not re.fullmatch(r"de_[a-z0-9_]{2,30}", map_name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such map: {map_name}")
    my_team, opponent = _fixture(db, mine, theirs)
    my_five, their_five = _lineups(db, my_team, opponent, my_lineup, their_lineup)
    started = time.perf_counter()
    with dbctx.using(db), lineup.using({my_team.id: my_five, opponent.id: their_five}):
        stamp = gameplan_view.stamp()
        part = lineup.cache_part(my_five, their_five)
        key = f"gp:v5:{my_team.id}:{opponent.id}{part}:playbook:{map_name}:{stamp}"
        data = _cache_get(key)
        hit = data is not None
        if data is None:
            data = playbook_view.panel(my_team, opponent, map_name)
            data = json.loads(json.dumps(data, default=str))
            _cache_set(key, data)
    return GameplanPanel(
        tab="todo",
        stamp=stamp,
        cached=hit,
        ms=round((time.perf_counter() - started) * 1000, 1),
        data=data,
    )


def _grid_team(mine: int, theirs: int, team: int, side: str, level: str) -> None:
    # The fixture is in the URL because that is the page the grid is on, and it
    # is what says the team belongs here: another fixture's team is a 404.
    if team not in (mine, theirs):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team is not in this fixture")
    if side not in SIDES or level not in LEVELS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad selection")


@router.get("/{mine}/vs/{theirs}/heatmap")
def heatmap(
    mine: int,
    theirs: int,
    db: DbSession,
    _: CurrentUser,
    team: int,
    map: str = Query(""),
    player: str = heatmap_groups.ALL_PLAYERS,
    side: str = "all",
    kind: str = "kills",
    level: str = heatmap_groups.ALL_LEVELS,
) -> dict[str, Any]:
    """One heatmap cell for a fixture: the positions and the map they go on (the page draws it)."""
    _grid_team(mine, theirs, team, side, level)
    if kind not in {"kills", "deaths"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad selection")
    try:
        with dbctx.using(db):
            result = heatmap_groups.points(
                map_name=map, team_id=team, player_id=player, side=side, kind=kind, level=level
            )
    except Exception:  # a heatmap must never take the page down with it
        logger.exception("heatmap failed for %s vs %s", mine, theirs)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Heatmap failed") from None
    return result or {"empty": True}


@router.get("/{mine}/vs/{theirs}/movement")
def movement_map(
    mine: int,
    theirs: int,
    db: DbSession,
    _: CurrentUser,
    team: int,
    map: str = Query(""),
    player: str = heatmap_groups.ALL_PLAYERS,
    side: str = "all",
    kind: str = "routes",
    level: str = heatmap_groups.ALL_LEVELS,
) -> dict[str, Any]:
    """One movement cell for a fixture: the scene to animate and its tables."""
    _grid_team(mine, theirs, team, side, level)
    try:
        with dbctx.using(db):
            result = movement.render(
                map_name=map, team_id=team, player_id=player, side=side, kind=kind, level=level
            )
    except Exception:  # a render must never take the page down with it
        logger.exception("movement render failed for %s vs %s", mine, theirs)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Render failed") from None
    return result or {"empty": True}


@router.get("/{mine}/vs/{theirs}/tracks")
def tracks(
    mine: int,
    theirs: int,
    db: DbSession,
    _: CurrentUser,
    team: int,
    map: str = Query(""),
    player: str = heatmap_groups.ALL_PLAYERS,
    side: str = "all",
    level: str = heatmap_groups.ALL_LEVELS,
) -> dict[str, Any]:
    """The real walked positions behind a movement selection (also sent with the
    movement cell; kept as its own request for the page's upgrade path)."""
    _grid_team(mine, theirs, team, side, level)
    selected = db.get(Team, team)
    if selected is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team")
    try:
        with dbctx.using(db):
            result = movement.tracks(
                map,
                selected,
                player,
                side,
                level=None if level == heatmap_groups.ALL_LEVELS else level,
            )
    except Exception:  # the centroid animation must survive this failing
        logger.exception("tracks failed for %s vs %s", mine, theirs)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Tracks failed") from None
    return result or {"tracks": []}
