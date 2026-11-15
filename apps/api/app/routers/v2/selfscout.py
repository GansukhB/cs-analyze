"""A my team's Self-scout on one Map with no opponent (CONTEXT.md: Self-scout,
Tell): its Tells, habits, slots and Vetoes, read the Playbook's way."""

from typing import Literal

from fastapi import APIRouter, Query, Response

from app.deps import DbSession, StaffUser
from app.routers.v2.common import my_team, team
from app.schemas_v2 import SelfScout
from app.services import answers, dbctx, self_scout

router = APIRouter()
VERSION = 1


@router.get("/teams/{team_id}/self-scout")
def selfscout(
    team_id: int,
    db: DbSession,
    user: StaffUser,
    response: Response,
    map: str | None = None,
    buy: Literal["", "full", "light"] = "",
    days: int = Query(0, ge=0, le=3650),
    since: str = Query("", pattern=r"^(|\d{4}-\d{2}-\d{2})$"),
) -> SelfScout:
    """``buy``, ``days`` and ``since`` read the Rounds as the Playbook's views do (GP-9)."""
    my_team(db, user, team_id)
    params = {"team": team_id, "map": map, "buy": buy, "days": days or None, "since": since}
    return SelfScout(**answers.serve(db, "v2.self_scout", params, response=response))


@answers.kind("v2.self_scout", VERSION, daily=True)
def _selfscout(db, p: dict) -> dict:
    mine = team(db, p["team"])
    view = {k: p[k] for k in ("buy", "days", "since") if p.get(k)}
    with dbctx.using(db):
        built = self_scout.build(mine, p.get("map"), view or None)
    return SelfScout(team={"id": mine.id, "name": mine.name}, **built).model_dump(mode="json")
