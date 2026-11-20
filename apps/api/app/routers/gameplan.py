"""The game plan: pick two teams, then one panel per URL.

Ported from cstat's ``gameplan_pick``, ``gameplan`` and the three grid views.
The page asks for its header once and then one panel at a time, so a tab only
pays for what it shows (see :class:`app.services.gameplan.Report`). Every
answer is a stored answer (`app/services/answers.py`, docs/adr/0014): the
worker computes each my team's Game Plan against every Team ahead of time, a
page reads it at once, and after a parse it still reads the last one while the
worker computes the new one.

Each side's Lineup (CONTEXT.md) rides along as a query parameter of Steam ids,
so a picked plan is a link like any other; it joins the cache key, and a side
left out keeps the five from the Team's most recent parsed Match.
"""

import logging
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.deps import DbSession, StaffUser
from app.models import Player, Team
from app.schemas import (
    Between,
    FixtureStyle,
    GameplanHeader,
    GameplanLineup,
    GameplanLineups,
    GameplanPanel,
    GameplanPick,
    LineupMember,
    LineupPlayer,
    LineupPlayers,
    TeamRef,
    TimeoutCard,
    VetoLab,
    VetoLabAsk,
)
from app.services import (
    answers,
    audit,
    between,
    dbctx,
    gameplan,
    gameplan_view,
    heatmap_groups,
    lineup,
    movement,
    playbook_view,
    radar,
    review_pool,
    scope,
    timeout_card,
    utility_map,
    veto_lab,
    window,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gameplan", tags=["gameplan"])

# Stored answers outlive a deploy: the stamp moves on a parse or a Review rebuilt,
# not when the code that words a panel changes. Bump with any such change.
CACHE_VERSION = 35

LEVELS = {heatmap_groups.ALL_LEVELS, radar.UPPER, radar.LOWER}
SIDES = {"all", "ct", "t"}
MAP_NAME = re.compile(r"de_[a-z0-9_]{2,30}")


def _map_name(map_name: str) -> None:
    if not MAP_NAME.fullmatch(map_name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such map: {map_name}")


def _report(my_team: Team, opponent: Team) -> gameplan.Report:
    """The fixture's lazy Report, built once per session: the warm-up computes a
    fixture's tabs on one session, so they share it (a request has its own)."""
    part = lineup.cache_part(lineup.chosen(my_team) or [], lineup.chosen(opponent) or [])
    key = ("gp.report", my_team.id, opponent.id, part, window.cache_part())
    return dbctx.memo(key, lambda: gameplan.build(my_team, opponent))


def _indexes(my_team: Team, opponent: Team) -> tuple[dict, dict]:
    def build():
        return (
            heatmap_groups.build_index(my_team, opponent),
            movement.build_index(my_team, opponent),
        )

    return dbctx.memo(("gp.indexes", my_team.id, opponent.id), build)


def _fixture_params(
    mine: int, theirs: int, my_lineup: str = "", their_lineup: str = "", since: str = ""
):
    return {"mine": mine, "theirs": theirs, "my_lineup": my_lineup,
            "their_lineup": their_lineup, "since": since}  # fmt: skip


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


def _since_query():
    return Query(
        "",
        pattern=r"^(|\d{4}-\d{2}-\d{2})$",
        description="TM-3: read the Teams' Maps from this day on (the Pool stays whole).",
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
def pick(db: DbSession, _: StaffUser) -> GameplanPick:
    """Every team with parsed maps, and how many: the picker's list."""
    with dbctx.using(db):
        return GameplanPick(**gameplan_view.pick())


@router.get("/teams/{team_id}/players")
def team_players(team_id: int, db: DbSession, _: StaffUser) -> LineupPlayers:
    """Who has played for this team, most recent first: a Lineup's candidates."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team")
    with dbctx.using(db):
        return LineupPlayers(players=[LineupPlayer(**p) for p in lineup.candidates(team)])


@router.get("/players")
def search_players(
    db: DbSession, _: StaffUser, q: str = Query(min_length=2, max_length=64)
) -> LineupPlayers:
    """Any player by a name they played under: a stand-in or a new signing."""
    with dbctx.using(db):
        return LineupPlayers(players=[LineupPlayer(**p) for p in lineup.search(q)])


# A fixture's answers read its two Teams (docs/adr/0015).
FIXTURE = answers.teams("mine", "theirs")
TEAM = answers.teams("team")


def fixture_stamp(db, mine: int, theirs: int) -> str:
    """Where the fixture's two Teams stood: the Game Plan's ``stamp``, which a
    Briefing sends back and is refused (409) once it moved."""
    return answers.fresh_part(answers.stamp(db, "gp.header", {"mine": mine, "theirs": theirs}))


@router.get("/{mine}/vs/{theirs}")
def header(
    mine: int,
    theirs: int,
    db: DbSession,
    _: StaffUser,
    response: Response,
    my_lineup: str = _lineup_query(),
    their_lineup: str = _lineup_query(),
    since: str = _since_query(),
) -> GameplanHeader:
    """The page header, the tab list and both Lineups, on every tab."""
    my_team, opponent = _fixture(db, mine, theirs)
    _lineups(db, my_team, opponent, my_lineup, their_lineup)
    with dbctx.using(db):
        # Opening a Game Plan is when stale Reviews matter: have the worker
        # rebuild them (docs/adr/0008). A no-op while one rebuild is running.
        review_pool.request_refresh()
    params = _fixture_params(mine, theirs, my_lineup, their_lineup, since)
    return GameplanHeader(**answers.serve(db, "gp.header", params, response=response))


@answers.kind("gp.header", CACHE_VERSION, deps=FIXTURE)
def _header(db, p: dict) -> dict:
    my_team, opponent = _fixture(db, p["mine"], p["theirs"])
    my_five, their_five = _lineups(db, my_team, opponent, p["my_lineup"], p["their_lineup"])
    picked = {my_team.id: my_five, opponent.id: their_five}
    stamp = fixture_stamp(db, my_team.id, opponent.id)
    with dbctx.using(db), lineup.using(picked), window.using(window.parse(p["since"])):
        report = _report(my_team, opponent)
        out = GameplanHeader(
            my_team=TeamRef(id=my_team.id, name=my_team.name),
            opponent=TeamRef(id=opponent.id, name=opponent.name),
            lede=report["lede"],
            tabs=gameplan_view.tabs(*_indexes(my_team, opponent)),
            default_tab=gameplan_view.DEFAULT_TAB,
            stamp=stamp,
            lineups=GameplanLineups(mine=_lineup_out(my_team), theirs=_lineup_out(opponent)),
        )
    return out.model_dump(mode="json")


@router.get("/{mine}/vs/{theirs}/s/{tab}")
def panel(
    mine: int,
    theirs: int,
    tab: str,
    db: DbSession,
    _: StaffUser,
    response: Response,
    my_lineup: str = _lineup_query(),
    their_lineup: str = _lineup_query(),
    since: str = _since_query(),
) -> GameplanPanel:
    """One panel's data, computed ahead of time per pair of Lineups and window."""
    if tab not in gameplan_view.TAB_KEYS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such section: {tab}")
    my_team, opponent = _fixture(db, mine, theirs)
    _lineups(db, my_team, opponent, my_lineup, their_lineup)
    started = time.perf_counter()
    params = {**_fixture_params(mine, theirs, my_lineup, their_lineup, since), "tab": tab}
    found = answers.lookup(db, "gp.panel", params)
    answers.mark(response, found)
    return GameplanPanel(
        tab=tab,
        stamp=found.data["stamp"],
        cached=not found.computed,
        ms=round((time.perf_counter() - started) * 1000, 1),
        data=found.data["data"],
    )


@answers.kind("gp.panel", CACHE_VERSION, deps=FIXTURE)
def _panel(db, p: dict) -> dict:
    my_team, opponent = _fixture(db, p["mine"], p["theirs"])
    my_five, their_five = _lineups(db, my_team, opponent, p["my_lineup"], p["their_lineup"])
    picked = {my_team.id: my_five, opponent.id: their_five}
    tab = p["tab"]
    stamp = fixture_stamp(db, my_team.id, opponent.id)
    with dbctx.using(db), lineup.using(picked), window.using(window.parse(p["since"])):
        report = _report(my_team, opponent)
        grids = {}
        if tab == "heatmaps":
            grids["heatmaps"] = _indexes(my_team, opponent)[0]
        elif tab == "movement":
            grids["movement"] = _indexes(my_team, opponent)[1]
        data = gameplan_view.panel(tab, report, my_team, opponent, **grids)
    return {"stamp": stamp, "data": data}


@router.post("/{mine}/vs/{theirs}/veto")
def veto_lab_step(
    mine: int, theirs: int, body: VetoLabAsk, db: DbSession, user: StaffUser, response: Response
) -> VetoLab:
    """The veto from where it stands, with each Map's chance as Staff set it (GP-10)."""
    _fixture(db, mine, theirs)
    params = {"mine": mine, "theirs": theirs, "workspace_id": user.workspace_id,
              **body.model_dump(mode="json")}  # fmt: skip
    try:
        return VetoLab(**answers.serve(db, "gp.veto", params, response=response))
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None


@answers.kind("gp.veto", CACHE_VERSION, deps=FIXTURE)
def _veto(db, p: dict) -> dict:
    my_team, opponent = _fixture(db, p["mine"], p["theirs"])
    # Our own Scrims, for our readiness only: the Workspace's, whoever computes it.
    scope.bind(db, p["workspace_id"], scrims=True)
    with dbctx.using(db):
        out = veto_lab.lab(
            my_team, opponent, p["workspace_id"], p["format"], p["we_start"], p["done"],
            p["adjust"],
        )  # fmt: skip
    return VetoLab(**out).model_dump(mode="json")


@router.get("/{mine}/vs/{theirs}/timeout/{map_name}")
def fixture_timeout(
    mine: int, theirs: int, map_name: str, db: DbSession, _: StaffUser, response: Response
) -> TimeoutCard:
    """What the opponent changes when this Map goes against them, and our answer;
    with the Pool's next Round after a run of losses, with and without a timeout (GP-4)."""
    _map_name(map_name)
    _fixture(db, mine, theirs)
    params = {"mine": mine, "theirs": theirs, "map": map_name}
    return TimeoutCard(**answers.serve(db, "gp.timeout", params, response=response))


@answers.kind("gp.timeout", CACHE_VERSION, deps=FIXTURE)
def _timeout(db, p: dict) -> dict:
    my_team, opponent = _fixture(db, p["mine"], p["theirs"])
    with dbctx.using(db):
        card = timeout_card.card(opponent, my_team, p["map"])
        return TimeoutCard(**card, pool=audit.pool()).model_dump(mode="json")


@router.get("/{mine}/vs/{theirs}/between")
def fixture_between(
    mine: int,
    theirs: int,
    db: DbSession,
    _: StaffUser,
    response: Response,
    played: int | None = None,
) -> Between:
    """What the opponent did differently on a Map they just played (default their
    newest reviewed), against their other Maps: for the break before the next (GP-4)."""
    _fixture(db, mine, theirs)
    params = {"mine": mine, "theirs": theirs, "played": played}
    return Between(**answers.serve(db, "gp.between", params, response=response))


@answers.kind("gp.between", CACHE_VERSION, deps=FIXTURE)
def _between(db, p: dict) -> dict:
    _my_team, opponent = _fixture(db, p["mine"], p["theirs"])
    with dbctx.using(db):
        return Between(**between.changes(opponent, p.get("played"))).model_dump(mode="json")


@router.get("/{mine}/vs/{theirs}/style/{map_name}")
def fixture_style(
    mine: int, theirs: int, map_name: str, db: DbSession, _: StaffUser, response: Response
) -> FixtureStyle:
    """Both Teams' style on one Map, each against every Team's (TM-5): each Team's
    own stored answer, which every fixture it is in shares."""
    _map_name(map_name)
    _fixture(db, mine, theirs)
    ours = answers.lookup(db, "team.style", {"team": mine, "map": map_name})
    their = answers.lookup(db, "team.style", {"team": theirs, "map": map_name})
    answers.mark(response, answers.worst(ours, their))
    return FixtureStyle(mine=ours.data["style"], theirs=their.data["style"])


@router.get("/{mine}/vs/{theirs}/utility/{map_name}")
def utility(
    mine: int,
    theirs: int,
    map_name: str,
    db: DbSession,
    _: StaffUser,
    response: Response,
    side: str = Query("t", pattern="^(t|ct)$"),
    whose: str = Query("theirs", pattern="^(mine|theirs)$"),
) -> dict[str, Any]:
    """VIZ-10: where a Team's utility lands on a Map and Side, from where, when,
    and the lineups it repeats; drawn by the page over the overview. The Team's
    own stored answer: ours is the same against every opponent."""
    _map_name(map_name)
    _fixture(db, mine, theirs)
    params = {"team": theirs if whose == "theirs" else mine, "map": map_name, "side": side}
    return answers.serve(db, "team.utility", params, response=response)


@answers.kind("team.utility", 1, deps=TEAM)
def _utility(db, p: dict) -> dict:
    team = db.get(Team, p["team"])
    with dbctx.using(db):
        return {"team": team.name, **utility_map.build(team.id, p["map"], p["side"])}


@router.get("/{mine}/vs/{theirs}/playbook/{map_name}")
def playbook(
    mine: int,
    theirs: int,
    map_name: str,
    db: DbSession,
    _: StaffUser,
    response: Response,
    my_lineup: str = _lineup_query(),
    their_lineup: str = _lineup_query(),
    buy: str = Query("", pattern="^(|full|light)$"),
    days: int = Query(0, ge=0, le=3650),
    since: str = Query("", pattern=r"^(|\d{4}-\d{2}-\d{2})$"),
    score: str = Query("", pattern="^(|ahead|close|behind)$"),
) -> GameplanPanel:
    """One Map's Playbook for the «Юу хийх» tab, computed ahead of time.
    ``buy``, ``days`` and ``since`` (a patch's day, DATA-7) read the habits over
    those Rounds only (GP-9)."""
    _map_name(map_name)
    my_team, opponent = _fixture(db, mine, theirs)
    _lineups(db, my_team, opponent, my_lineup, their_lineup)
    view = {
        k: v for k, v in (("buy", buy), ("days", days), ("since", since), ("score", score)) if v
    }
    started = time.perf_counter()
    params = {"mine": mine, "theirs": theirs, "map": map_name, "my_lineup": my_lineup,
              "their_lineup": their_lineup, "view": view or None}  # fmt: skip
    found = answers.lookup(db, "gp.playbook", params)
    answers.mark(response, found)
    return GameplanPanel(
        tab="todo",
        stamp=found.data["stamp"],
        cached=not found.computed,
        ms=round((time.perf_counter() - started) * 1000, 1),
        data=found.data["data"],
    )


@answers.kind("gp.playbook", CACHE_VERSION, deps=FIXTURE)
def _playbook(db, p: dict) -> dict:
    my_team, opponent = _fixture(db, p["mine"], p["theirs"])
    my_five, their_five = _lineups(db, my_team, opponent, p["my_lineup"], p["their_lineup"])
    stamp = fixture_stamp(db, my_team.id, opponent.id)
    with dbctx.using(db), lineup.using({my_team.id: my_five, opponent.id: their_five}):
        data = playbook_view.panel(my_team, opponent, p["map"], p.get("view"))
    return {"stamp": stamp, "data": data}


def _steamids(players) -> str:
    return ",".join(str(p.steamid) for p in players)


def playbook_data(
    db, my_team, opponent, my_five, their_five, map_name: str, stamp: str, view: dict | None = None
):
    """One Map's Playbook panel as it reads now, and whether it was stored. A
    Briefing freezes its lines from it, so it is never a stale one. ``view`` reads
    the habits over some Rounds only (GP-9)."""
    params = {"mine": my_team.id, "theirs": opponent.id, "map": map_name,
              "my_lineup": _steamids(my_five), "their_lineup": _steamids(their_five),
              "view": view or None}  # fmt: skip
    found = answers.lookup(db, "gp.playbook", params, fresh=True)
    return found.data["data"], not found.computed


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
    _: StaffUser,
    response: Response,
    team: int,
    map: str = Query(""),
    player: str = heatmap_groups.ALL_PLAYERS,
    side: str = "all",
    kind: str = "kills",
    level: str = heatmap_groups.ALL_LEVELS,
    phase: str = Query("all", pattern=r"^(all|0-15|15-30|30-60|60\+|post)$"),
    buy: str = Query("all", pattern="^(all|full|light)$"),
    compare: bool = False,
    place: str = Query("", max_length=24),
) -> dict[str, Any]:
    """One heatmap cell for a fixture: the positions and the map they go on (the page
    draws it); by phase of the Round and buy, against every other Team's, and kept
    to one game Callout (VIZ-9). The Team's own stored answer, whichever fixture
    asks (docs/adr/0015)."""
    _grid_team(mine, theirs, team, side, level)
    if kind not in {"kills", "deaths", "positions"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad selection")
    params = {"team": team, "map": map, "player": player, "side": side, "kind": kind,
              "level": level, "phase": phase, "buy": buy, "compare": compare,
              "place": place}  # fmt: skip
    try:
        return answers.serve(db, "gp.heatmap", params, response=response)
    except Exception:  # a heatmap must never take the page down with it
        logger.exception("heatmap failed for %s vs %s", mine, theirs)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Heatmap failed") from None


@answers.kind("gp.heatmap", 1, deps=TEAM)
def _heatmap(db, p: dict) -> dict:
    with dbctx.using(db):
        result = heatmap_groups.points(
            map_name=p["map"], team_id=p["team"], player_id=p["player"], side=p["side"],
            kind=p["kind"], level=p["level"], phase=p["phase"], buy=p["buy"],
            compare=p["compare"], place=p["place"],
        )  # fmt: skip
    return result or {"empty": True}


@router.get("/{mine}/vs/{theirs}/movement")
def movement_map(
    mine: int,
    theirs: int,
    db: DbSession,
    _: StaffUser,
    response: Response,
    team: int,
    map: str = Query(""),
    player: str = heatmap_groups.ALL_PLAYERS,
    side: str = "all",
    kind: str = "routes",
    level: str = heatmap_groups.ALL_LEVELS,
) -> dict[str, Any]:
    """One movement cell for a fixture: the scene to animate and its tables, the
    Team's own stored answer."""
    _grid_team(mine, theirs, team, side, level)
    params = {"team": team, "map": map, "player": player, "side": side, "kind": kind,
              "level": level}  # fmt: skip
    try:
        return answers.serve(db, "gp.movement", params, response=response)
    except Exception:  # a render must never take the page down with it
        logger.exception("movement render failed for %s vs %s", mine, theirs)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Render failed") from None


@answers.kind("gp.movement", 1, deps=TEAM)
def _movement(db, p: dict) -> dict:
    with dbctx.using(db):
        result = movement.render(
            map_name=p["map"], team_id=p["team"], player_id=p["player"], side=p["side"],
            kind=p["kind"], level=p["level"],
        )  # fmt: skip
    return result or {"empty": True}


@router.get("/{mine}/vs/{theirs}/tracks")
def tracks(
    mine: int,
    theirs: int,
    db: DbSession,
    _: StaffUser,
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
