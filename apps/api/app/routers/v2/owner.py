"""The management summary of a my team (v2 screen 10)."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Response

from app.deps import DbSession, StaffUser
from app.routers.v2.common import my_team, team
from app.schemas_v2 import Owner
from app.services import answers, dbctx, owner

router = APIRouter()
VERSION = 1


@router.get("/teams/{team_id}/owner", response_model_by_alias=True)
def owner_summary(
    team_id: int,
    db: DbSession,
    user: StaffUser,
    response: Response,
    period: Literal["m", "q", "y"] = "q",
) -> Owner:
    my_team(db, user, team_id)
    params = {"team": team_id, "period": period}
    built = answers.serve(db, "v2.owner", params, response=response, workspace_id=user.workspace_id)
    return Owner(**built)


def _live(db, p: dict, data: dict, workspace_id: int | None) -> dict:
    """The Practice schedule's hours and the Team goals are Staff's, edited at any
    time: read on every request, beside the stored numbers."""
    found = team(db, p["team"])
    with dbctx.using(db):
        hours = owner.practice_hours(found, workspace_id, data["since"])
        months = [
            {**m, "hours": owner.month_hours(found, workspace_id, date.fromisoformat(m["month"]))}
            for m in data["months"]
        ]
        goals = owner.goals(found, workspace_id) if workspace_id is not None else []
    return {**data, "kpis": {**data["kpis"], "hours": hours}, "months": months, "goals": goals}


@answers.kind("v2.owner", VERSION, live=_live, daily=True)
def _owner(db, p: dict) -> dict:
    found = team(db, p["team"])
    with dbctx.using(db):
        built = owner.build(found, None, p["period"])
    return Owner(team={"id": found.id, "name": found.name}, **built).model_dump(
        mode="json", by_alias=True
    )
