"""A my team's Self-scout on one Map with no opponent (CONTEXT.md: Self-scout,
Tell): its Tells, habits, slots and Vetoes, read the Playbook's way."""

from typing import Literal

from fastapi import APIRouter, Query

from app.deps import DbSession, StaffUser
from app.routers.v2.common import my_team
from app.schemas_v2 import SelfScout
from app.services import dbctx, self_scout

router = APIRouter()


@router.get("/teams/{team_id}/self-scout")
def selfscout(
    team_id: int,
    db: DbSession,
    user: StaffUser,
    map: str | None = None,
    buy: Literal["", "full", "light"] = "",
    days: int = Query(0, ge=0, le=3650),
    since: str = Query("", pattern=r"^(|\d{4}-\d{2}-\d{2})$"),
) -> SelfScout:
    """``buy``, ``days`` and ``since`` read the Rounds as the Playbook's views do (GP-9)."""
    mine = my_team(db, user, team_id)
    view = {k: v for k, v in (("buy", buy), ("days", days), ("since", since)) if v}
    with dbctx.using(db):
        built = self_scout.build(mine, map, view or None)
    return SelfScout(team={"id": mine.id, "name": mine.name}, **built)
