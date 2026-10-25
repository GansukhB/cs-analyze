"""A my team's Matches and one Match Map's report (v2 screen 03)."""

from fastapi import APIRouter
from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.deps import DbSession, StaffUser
from app.models import Match, MatchKind, MatchMap
from app.routers.matches import _map, _match
from app.routers.teams import map_label
from app.routers.v2.common import my_team
from app.schemas_v2 import MatchList, MatchReport
from app.services import dbctx, match_report, scope, team_numbers

router = APIRouter()


def _tabs(team_id: int, match: Match) -> list[dict]:
    out = []
    for m in sorted(match.map_results, key=lambda m: m.map_number):
        ours, theirs = team_numbers.score_of(team_id, m)
        out.append(
            {
                "map_number": m.map_number,
                "label": map_label(m.game_map),
                "parsed": m.is_parsed,
                "score": f"{ours}–{theirs}" if ours is not None and theirs is not None else "",
            }
        )
    return out


@router.get("/teams/{team_id}/matches")
def team_matches(team_id: int, db: DbSession, user: StaffUser, scrims: bool = False) -> MatchList:
    """The my team's Matches, newest first, each with its Maps."""
    team = my_team(db, user, team_id)
    if scrims:
        scope.allow_scrims(db)
    q = (
        select(Match)
        .where(or_(Match.team1_id == team.id, Match.team2_id == team.id))
        .options(
            joinedload(Match.team1),
            joinedload(Match.team2),
            joinedload(Match.tournament),
            selectinload(Match.map_results).joinedload(MatchMap.game_map),
        )
        .order_by(Match.played_at.desc())
        .limit(100)
    )
    out = []
    for m in db.scalars(q).unique():
        mine = m.team1_id == team.id
        opp = m.team2 if mine else m.team1
        out.append(
            {
                "match_id": m.id,
                "played_at": m.played_at,
                "opponent": opp.name if opp else m.opponent_label,
                "ours": m.team1_score if mine else m.team2_score,
                "theirs": m.team2_score if mine else m.team1_score,
                "kind": m.kind,
                "tournament": m.tournament.name if m.tournament else "",
                "maps": _tabs(team.id, m),
            }
        )
    return MatchList(matches=out)


@router.get("/teams/{team_id}/matches/{match_id}/maps/{map_number}/report")
def report(
    team_id: int, match_id: int, map_number: int, db: DbSession, user: StaffUser
) -> MatchReport:
    """One Match Map from the my team's side; from the first Team's when the my
    team did not play it."""
    team = my_team(db, user, team_id)
    match = _match(db, match_id, user)
    mm = _map(db, match_id, map_number, user)
    us = team.id if team.id in (mm.team1_id, mm.team2_id) else (mm.team1_id or team.id)
    them = mm.team2 if mm.team1_id == us else mm.team1
    me = mm.team1 if mm.team1_id == us else mm.team2
    ours, theirs = team_numbers.score_of(us, mm)
    with dbctx.using(db):
        built = match_report.build(db, mm, us)
    return MatchReport(
        match_id=match.id,
        map_number=mm.map_number,
        map=mm.game_map.name if mm.game_map else "",
        label=map_label(mm.game_map),
        kind=match.kind,
        best_of=len(match.map_results) if match.kind != MatchKind.SCRIM else 1,
        played_at=match.played_at,
        tournament=match.tournament.name if match.tournament else "",
        us={"id": us, "name": me.name if me else team.name},
        them={"id": them.id, "name": them.name} if them else None,
        ours=ours,
        theirs=theirs,
        maps=_tabs(us, match),
        **built,
    )
