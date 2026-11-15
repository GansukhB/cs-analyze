"""A my team's utility over a window (v2 screen 06)."""

from typing import Literal

from fastapi import APIRouter, Response

from app.deps import DbSession, StaffUser
from app.models import MatchKind
from app.routers.v2.common import my_team, team
from app.routers.v2.overview import DAYS
from app.schemas_v2 import UtilityReport
from app.services import answers, dbctx, mn, scope, utility_report

router = APIRouter()
VERSION = 1


@router.get("/teams/{team_id}/utility", response_model_by_alias=True)
def utility(
    team_id: int,
    db: DbSession,
    user: StaffUser,
    response: Response,
    period: Literal["30", "90", "180", "all"] = "30",
    scrims: bool = False,
    map: str | None = None,
) -> UtilityReport:
    my_team(db, user, team_id)
    params = {"team": team_id, "period": period, "scrims": scrims, "map": map}
    return UtilityReport(**answers.serve(db, "v2.utility", params, response=response))


@answers.kind("v2.utility", VERSION, daily=True)
def _utility(db, p: dict) -> dict:
    found = team(db, p["team"])
    scrims = bool(p.get("scrims"))
    if scrims:
        scope.allow_scrims(db)
    days = DAYS[p["period"]]
    with dbctx.using(db):
        maps = utility_report.maps_for(found, days, None if scrims else MatchKind.OFFICIAL)
        built = utility_report.build(db, found, maps, p.get("map"))
        built["map_choices"] = [
            {"map": c["map"], "label": mn.game_map(c["map"]), "n": c["n"]}
            for c in built["map_choices"]
        ]
        out = UtilityReport(team={"id": found.id, "name": found.name}, days=days, **built)
    return out.model_dump(mode="json", by_alias=True)
