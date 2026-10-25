"""The overview of one my team (v2 screen 01)."""

from typing import Literal

from fastapi import APIRouter

from app.deps import DbSession, StaffUser
from app.routers.v2.common import my_team
from app.schemas_v2 import Overview, UpcomingRead
from app.services import dbctx, scope, team_overview, upcoming

router = APIRouter()

DAYS = {"30": 30, "90": 90, "180": 180, "all": None}


@router.get("/teams/{team_id}/overview")
def overview(
    team_id: int,
    db: DbSession,
    user: StaffUser,
    period: Literal["30", "90", "180", "all"] = "30",
    scrims: bool = False,
) -> Overview:
    """KPIs over the period against the one before it, Strengths and Weaknesses,
    Maps, form, the five, the pipeline and the next Upcoming match. Scrims count
    only when asked (grilling Q5), and only the Team's own."""
    team = my_team(db, user, team_id)
    if scrims:
        scope.allow_scrims(db)
    with dbctx.using(db):
        built = team_overview.build(team, user.workspace_id, DAYS[period], scrims=scrims)
        found = built["upcoming"]
        if found is not None:
            upcoming.link(found)
            db.commit()
            built["upcoming"] = UpcomingRead(**upcoming.read(found))
        return Overview(team={"id": team.id, "name": team.name}, **built)
