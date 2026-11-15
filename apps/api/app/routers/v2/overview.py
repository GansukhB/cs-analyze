"""The overview of one my team (v2 screen 01)."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Response

from app.deps import DbSession, StaffUser
from app.routers.v2.common import my_team, team
from app.schemas_v2 import Overview, UpcomingRead
from app.services import answers, dbctx, scope, team_overview, upcoming

router = APIRouter()
VERSION = 1

DAYS = {"30": 30, "90": 90, "180": 180, "all": None}


@router.get("/teams/{team_id}/overview")
def overview(
    team_id: int,
    db: DbSession,
    user: StaffUser,
    response: Response,
    period: Literal["30", "90", "180", "all"] = "30",
    scrims: bool = False,
) -> Overview:
    """KPIs over the period against the one before it, Strengths and Weaknesses,
    Maps, form, the five, the pipeline and the next Upcoming match. Scrims count
    only when asked (grilling Q5), and only the Team's own."""
    my_team(db, user, team_id)
    params = {"team": team_id, "period": period, "scrims": scrims}
    built = answers.serve(
        db, "v2.overview", params, response=response, workspace_id=user.workspace_id
    )
    return Overview(**built)


def _live(db, p: dict, data: dict, workspace_id: int | None) -> dict:
    """What moves without a parse: the jobs, the uploads, the next Upcoming match."""
    with dbctx.using(db):
        out = {**data, "jobs": team_overview.jobs(), "uploads": [], "upcoming": None}
        if workspace_id is None:
            return out
        out["uploads"] = team_overview.uploads(workspace_id)
        found = team_overview.next_upcoming(
            p["team"], workspace_id, datetime.now(UTC).replace(tzinfo=None)
        )
        if found is not None:
            upcoming.link(found)
            db.commit()
            out["upcoming"] = UpcomingRead(**upcoming.read(found)).model_dump(mode="json")
    return out


@answers.kind("v2.overview", VERSION, live=_live, daily=True)
def _overview(db, p: dict) -> dict:
    found = team(db, p["team"])
    if p.get("scrims"):
        scope.allow_scrims(db)
    with dbctx.using(db):
        built = team_overview.build(found, None, DAYS[p["period"]], scrims=bool(p.get("scrims")))
    built["upcoming"] = None
    return Overview(team={"id": found.id, "name": found.name}, **built).model_dump(mode="json")
