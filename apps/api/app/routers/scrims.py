"""A my team's Scrim log (docs/plans/07 RV-6): every Scrim it uploaded, newest
first, with its Maps and what its Summary says to work on. Scrims are the
Workspace's own development and nothing else reads them (docs/adr/0010)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.deps import DbSession, StaffUser
from app.models import Match, MatchKind, MatchMap, Team, WorkspaceTeam
from app.schemas import ScrimLine, ScrimLog, ScrimMap, ScrimRow, TeamRef
from app.services import mn, review_view, scope

router = APIRouter(prefix="/scrims", tags=["scrims"])
LIMIT = 20


@router.get("")
def scrim_log(
    db: DbSession, user: StaffUser, team_id: int | None = Query(default=None)
) -> ScrimLog:
    mine = list(
        db.scalars(
            select(WorkspaceTeam.team_id).where(WorkspaceTeam.workspace_id == user.workspace_id)
        )
    )
    if not mine:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This Workspace has no my team")
    team_id = team_id or mine[0]
    if team_id not in mine:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not one of this Workspace's teams")
    team = db.get(Team, team_id)
    scope.allow_scrims(db)
    matches = db.scalars(
        select(Match)
        .where(
            Match.kind == MatchKind.SCRIM,
            Match.workspace_id == user.workspace_id,
            or_(Match.team1_id == team_id, Match.team2_id == team_id),
        )
        .options(
            joinedload(Match.team1),
            joinedload(Match.team2),
            selectinload(Match.map_results).joinedload(MatchMap.game_map),
        )
        .order_by(Match.played_at.desc())
        .limit(LIMIT)
    ).unique()
    rows = []
    for match in matches:
        other = match.team2 if match.team1_id == team_id else match.team1
        panel = review_view.match_panel(db, match)
        ours = next((s for s in panel["summaries"] if s["team_id"] == team_id), None) or {}
        rows.append(
            ScrimRow(
                match_id=match.id,
                played_at=match.played_at,
                partner=(other.name if other else "") or match.opponent_label,
                maps=[
                    ScrimMap(
                        map_number=m.map_number,
                        label=mn.game_map(m.game_map.name if m.game_map else ""),
                        scoreline=m.scoreline,
                        won=(m.winner_id == team_id) if m.winner_id else None,
                    )
                    for m in sorted(match.map_results, key=lambda m: m.map_number)
                ],
                focus=[
                    ScrimLine(text=f["text"], advice=f.get("advice") or "", weight=f["weight"])
                    for f in (ours.get("focus") or [])[:3]
                ],
                strengths=[
                    ScrimLine(text=s["text"], weight=s.get("weight") or 0.0)
                    for s in (ours.get("strengths") or [])[:2]
                ],
            )
        )
    return ScrimLog(team=TeamRef(id=team.id, name=team.name), scrims=rows)
