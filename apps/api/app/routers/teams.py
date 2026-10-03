"""Teams: the list and one team's page, ported from cstat's views.

Every number here is read from what was stored, never from HLTV: a match row
exists because a fetch saw it, a map row because a demo was parsed. The two are
shown side by side, since a team with twenty results and two parsed maps is a
team the rest of the app can say little about.
"""

from collections import defaultdict

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.deps import CurrentUser, DbSession
from app.models import MapRoster, Match, MatchMap, Player, Round, Team
from app.schemas import (
    DemoState,
    MapRecordRow,
    MatchRecord,
    TeamDetail,
    TeamList,
    TeamPlayer,
    TeamRef,
    TeamResult,
    TeamResultMap,
    TeamRow,
)

router = APIRouter(prefix="/teams", tags=["teams"])


def map_label(game_map) -> str:
    if not game_map:
        return "?"
    return game_map.display_name or game_map.name.replace("de_", "").title()


def parsed_maps_by_team(db: Session) -> dict[int, set[int]]:
    """``{team_id: {match_map_id, ...}}`` over every parsed map, in two queries.

    A team counts as having played a map if it held a side on a parsed round.
    """
    by_team: dict[int, set[int]] = defaultdict(set)
    for column in (Round.ct_team_id, Round.t_team_id):
        pairs = db.execute(
            select(column, Round.match_map_id)
            .join(MatchMap, MatchMap.id == Round.match_map_id)
            .where(MatchMap.parsed_at.is_not(None), column.is_not(None))
            .distinct()
        )
        for team_id, map_id in pairs:
            by_team[team_id].add(map_id)
    return by_team


def _row(team: Team, matches: int, maps: int, last) -> TeamRow:
    return TeamRow(
        id=team.id,
        name=team.name,
        hltv_id=team.hltv_id,
        hltv_url=f"https://www.hltv.org{team.url}" if team.url else "",
        identified=team.identified,
        matches=matches,
        maps=maps,
        last=last,
    )


@router.get("")
def list_teams(db: DbSession, _: CurrentUser) -> TeamList:
    """Every team, sorted by parsed maps: the name is what a reader scans for, but
    the sample size says whether the page behind it has anything on it."""
    parsed = parsed_maps_by_team(db)
    played: dict[int, list] = defaultdict(lambda: [0, None])
    for column in (Match.team1_id, Match.team2_id):
        for team_id, n, last in db.execute(
            select(column, func.count(), func.max(Match.played_at))
            .where(column.is_not(None))
            .group_by(column)
        ):
            entry = played[team_id]
            entry[0] += n
            if last and (entry[1] is None or last > entry[1]):
                entry[1] = last

    rows = [
        _row(team, played[team.id][0], len(parsed.get(team.id, ())), played[team.id][1])
        for team in db.scalars(select(Team))
    ]
    rows.sort(key=lambda r: (-r.maps, -r.matches, r.name.lower()))
    return TeamList(
        teams=rows,
        parsed_teams=sum(1 for r in rows if r.maps),
        # Distinct matches: every match counts once for each of its two teams.
        total_matches=db.scalar(select(func.count()).select_from(Match)) or 0,
    )


@router.get("/{team_id}")
def get_team(team_id: int, db: DbSession, _: CurrentUser) -> TeamDetail:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team")
    matches = list(
        db.scalars(
            select(Match)
            .where(or_(Match.team1_id == team.id, Match.team2_id == team.id))
            .options(
                joinedload(Match.team1),
                joinedload(Match.team2),
                joinedload(Match.tournament),
                selectinload(Match.map_results).joinedload(MatchMap.game_map),
                selectinload(Match.demos),
            )
            .order_by(Match.played_at.desc(), Match.hltv_id.desc())
        ).unique()
    )
    results = [_result(team, match) for match in matches]
    record = {"won": 0, "lost": 0, "drawn": 0}
    for row in results:
        if row.outcome:
            record[{"win": "won", "loss": "lost", "draw": "drawn"}[row.outcome]] += 1

    parsed = parsed_maps_by_team(db)
    last = max((m.played_at for m in matches if m.played_at), default=None)
    return TeamDetail(
        team=_row(team, len(matches), len(parsed.get(team.id, ())), last),
        record=MatchRecord(**record),
        results=results,
        n_parsed_maps=len(parsed.get(team.id, ())),
        map_record=_map_record(db, team),
        players=_players(db, team),
        # Who a plan could be built against: an opponent this team has actually
        # met and that has parsed maps of its own, since the plan reads demos.
        plannable=sorted(
            {
                row.opponent.id: row.opponent
                for row in results
                if row.opponent and row.opponent.id in parsed
            }.values(),
            key=lambda t: t.name.lower(),
        )
        if team.id in parsed
        else [],
    )


def _result(team: Team, match: Match) -> TeamResult:
    """One match seen from this team's side: our score first, theirs second.

    Map scorelines are flipped by the map's own attribution, which is resolved
    from the demo and can be missing (H1); an unattributed map keeps its raw
    scoreline rather than guessing which half is ours.
    """
    if match.team1_id == team.id:
        opponent, ours, theirs = match.team2, match.team1_score, match.team2_score
    else:
        opponent, ours, theirs = match.team1, match.team2_score, match.team1_score
    outcome = ""
    if ours is not None and theirs is not None:
        outcome = "win" if ours > theirs else "loss" if ours < theirs else "draw"

    maps = []
    for played in sorted(match.map_results, key=lambda m: m.map_number):
        if played.team1_id == team.id:
            mine, yours = played.team1_score, played.team2_score
        elif played.team2_id == team.id:
            mine, yours = played.team2_score, played.team1_score
        else:
            mine = yours = None
        maps.append(
            TeamResultMap(
                name=map_label(played.game_map),
                number=played.map_number,
                score=f"{mine}-{yours}" if mine is not None and yours is not None
                else played.scoreline,
                attributed=mine is not None,
                won=(played.winner_id == team.id) if played.winner_id else None,
                parsed=played.is_parsed,
            )
        )  # fmt: skip
    return TeamResult(
        match_id=match.id,
        played_at=match.played_at,
        opponent=TeamRef(id=opponent.id, name=opponent.name) if opponent else None,
        ours=ours,
        theirs=theirs,
        outcome=outcome,
        score=match.score,
        tournament=match.tournament.name if match.tournament else "",
        maps=maps,
        n_parsed=sum(1 for m in maps if m.parsed),
        demo=demo_state(match),
    )


def demo_state(match: Match) -> DemoState:
    """How far down the pipeline this match got, as one word plus its reason.

    Four states share the surface "no demo here": never looked for, HLTV has no
    link, downloaded but not unpacked, unpacked but not parsed.
    """
    if any(m.is_parsed for m in match.map_results):
        return DemoState(word="parsed", cls="success", why="stats are in the database")
    if any(d.map and d.is_downloaded for d in match.demos):
        return DemoState(word="unpacked", cls="running", why="maps on disk, not parsed yet")
    archive = next((d for d in match.demos if not d.map), None)
    if archive and archive.is_downloaded:
        return DemoState(word="downloaded", cls="running", why="archive on disk, not unpacked")
    if match.demo_checked_at and not match.demo_url:
        return DemoState(word="no demo", cls="cancelled", why="HLTV published none")
    if match.demo_url:
        return DemoState(word="available", cls="queued", why="HLTV has a demo; not fetched")
    return DemoState(word="unchecked", cls="queued", why="the demo link was never looked up")


def _map_record(db: Session, team: Team) -> list[MapRecordRow]:
    """Won-lost per map over the parsed maps attributed to this team."""
    tally: dict = defaultdict(lambda: {"played": 0, "won": 0, "lost": 0})
    played = db.scalars(
        select(MatchMap)
        .options(joinedload(MatchMap.game_map))
        .where(
            or_(MatchMap.team1_id == team.id, MatchMap.team2_id == team.id),
            MatchMap.parsed_at.is_not(None),
        )
    )
    for match_map in played:
        row = tally[map_label(match_map.game_map)]
        row["played"] += 1
        if match_map.winner_id == team.id:
            row["won"] += 1
        elif match_map.winner_id:
            row["lost"] += 1
    rows = []
    for name, counts in tally.items():
        decided = counts["won"] + counts["lost"]
        pct = round(100 * counts["won"] / decided) if decided else None
        rows.append(MapRecordRow(map=name, pct=pct, **counts))
    rows.sort(key=lambda r: (-r.played, r.map))
    return rows


def _players(db: Session, team: Team) -> list[TeamPlayer]:
    """Who has appeared for this team, most recently seen first."""
    last = func.max(Match.played_at)
    rows = db.execute(
        select(
            Player.name,
            func.count(func.distinct(MapRoster.match_map_id)),
            func.sum(MapRoster.rounds_total),
            last,
        )
        .join(Player, Player.id == MapRoster.player_id)
        .join(MatchMap, MatchMap.id == MapRoster.match_map_id)
        .join(Match, Match.id == MatchMap.match_id)
        .where(MapRoster.team_id == team.id)
        .group_by(MapRoster.player_id, Player.name)
        .order_by(last.desc(), func.count(func.distinct(MapRoster.match_map_id)).desc())
    )
    return [
        TeamPlayer(name=name, maps=maps, rounds=int(rounds or 0), last=seen)
        for name, maps, rounds, seen in rows
    ]
