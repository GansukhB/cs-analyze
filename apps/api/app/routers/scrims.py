"""A my team's Scrim log (docs/plans/07 RV-6): every Scrim it uploaded, newest
first, with its Maps and what its Summary says to work on. Scrims are the
Workspace's own development and nothing else reads them (docs/adr/0010)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.deps import DbSession, StaffUser
from app.models import Team, WorkspaceTeam
from app.schemas import ScrimLog, ScrimRow, TeamRef
from app.services import scrim_log as scrims_service

router = APIRouter(prefix="/scrims", tags=["scrims"])


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
    rows = scrims_service.log(db, user.workspace_id, team_id)
    return ScrimLog(team=TeamRef(id=team.id, name=team.name), scrims=[ScrimRow(**r) for r in rows])
