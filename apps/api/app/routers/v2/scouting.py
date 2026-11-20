"""An opponent's scouting page (v2 screen 07): the numbers the Playbook doesn't
give, and the Upcoming match its counters are kept on."""

from fastapi import APIRouter, Response

from app.deps import DbSession, StaffUser
from app.routers.v2.common import my_team, team
from app.schemas_v2 import Scouting, UpcomingRead
from app.services import answers, dbctx, forecast, scouting_v2, self_scout, upcoming

router = APIRouter()
VERSION = 1


@router.get("/teams/{team_id}/scouting/{opponent_id}", response_model_by_alias=True)
def scouting(
    team_id: int,
    opponent_id: int,
    db: DbSession,
    user: StaffUser,
    response: Response,
    map: str | None = None,
) -> Scouting:
    my_team(db, user, team_id)
    team(db, opponent_id)
    params = {"team": team_id, "opponent": opponent_id, "map": map}
    built = answers.serve(
        db, "v2.scouting", params, response=response, workspace_id=user.workspace_id
    )
    return Scouting(**built)


def _upcoming(db, p: dict, data: dict, workspace_id: int | None) -> dict:
    """The Upcoming match is Staff's, edited at any time: read on every request."""
    with dbctx.using(db):
        u = upcoming.for_fixture(workspace_id, p["team"], p["opponent"])
        found = UpcomingRead(**upcoming.read(u)).model_dump(mode="json") if u else None
    return {**data, "upcoming": found}


@answers.kind("v2.scouting", VERSION, live=_upcoming, deps=answers.teams("team", "opponent"))
def _scouting(db, p: dict) -> dict:
    mine, theirs = team(db, p["team"]), team(db, p["opponent"])
    with dbctx.using(db):
        built = scouting_v2.build(mine, theirs, p.get("map"))
        out = Scouting(
            team={"id": mine.id, "name": mine.name},
            opponent={"id": theirs.id, "name": theirs.name},
            upcoming=None,
            vetoes={
                "mine": self_scout.veto_summary(mine, "mine"),
                "theirs": self_scout.veto_summary(theirs, "theirs"),
                "policy_from_vetoes": forecast.veto_history_helps(),
            },
            **built,
        )
    return out.model_dump(mode="json", by_alias=True)
