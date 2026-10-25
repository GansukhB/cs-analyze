"""The management summary of a my team (v2 screen 10)."""

from typing import Literal

from fastapi import APIRouter

from app.deps import DbSession, StaffUser
from app.routers.v2.common import my_team
from app.schemas_v2 import Owner
from app.services import dbctx, owner

router = APIRouter()


@router.get("/teams/{team_id}/owner", response_model_by_alias=True)
def owner_summary(
    team_id: int, db: DbSession, user: StaffUser, period: Literal["m", "q", "y"] = "q"
) -> Owner:
    team = my_team(db, user, team_id)
    with dbctx.using(db):
        built = owner.build(team, user.workspace_id, period)
        return Owner(team={"id": team.id, "name": team.name}, **built)
