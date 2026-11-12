"""An opponent's scouting page (v2 screen 07): the numbers the Playbook doesn't
give, and the Upcoming match its counters are kept on."""

from fastapi import APIRouter

from app.deps import DbSession, StaffUser
from app.routers.v2.common import my_team, team
from app.schemas_v2 import Scouting, UpcomingRead
from app.services import dbctx, forecast, scouting_v2, self_scout, upcoming

router = APIRouter()


@router.get("/teams/{team_id}/scouting/{opponent_id}", response_model_by_alias=True)
def scouting(
    team_id: int, opponent_id: int, db: DbSession, user: StaffUser, map: str | None = None
) -> Scouting:
    mine = my_team(db, user, team_id)
    theirs = team(db, opponent_id)
    with dbctx.using(db):
        built = scouting_v2.build(mine, theirs, map)
        u = upcoming.for_fixture(user.workspace_id, mine.id, theirs.id)
        return Scouting(
            team={"id": mine.id, "name": mine.name},
            opponent={"id": theirs.id, "name": theirs.name},
            upcoming=UpcomingRead(**upcoming.read(u)) if u else None,
            vetoes={
                "mine": self_scout.veto_summary(mine, "mine"),
                "theirs": self_scout.veto_summary(theirs, "theirs"),
                "policy_from_vetoes": forecast.veto_history_helps(),
            },
            **built,
        )
