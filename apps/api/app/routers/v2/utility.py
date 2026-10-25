"""A my team's utility over a window (v2 screen 06)."""

from typing import Literal

from fastapi import APIRouter

from app.deps import DbSession, StaffUser
from app.models import MatchKind
from app.routers.v2.common import my_team
from app.routers.v2.overview import DAYS
from app.schemas_v2 import UtilityReport
from app.services import dbctx, mn, scope, utility_report

router = APIRouter()


@router.get("/teams/{team_id}/utility", response_model_by_alias=True)
def utility(
    team_id: int,
    db: DbSession,
    user: StaffUser,
    period: Literal["30", "90", "180", "all"] = "30",
    scrims: bool = False,
    map: str | None = None,
) -> UtilityReport:
    team = my_team(db, user, team_id)
    if scrims:
        scope.allow_scrims(db)
    with dbctx.using(db):
        maps = utility_report.maps_for(team, DAYS[period], None if scrims else MatchKind.OFFICIAL)
        built = utility_report.build(db, team, maps, map)
        built["map_choices"] = [
            {"map": c["map"], "label": mn.game_map(c["map"]), "n": c["n"]}
            for c in built["map_choices"]
        ]
        return UtilityReport(team={"id": team.id, "name": team.name}, days=DAYS[period], **built)
