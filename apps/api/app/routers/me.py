"""A Player login's own page (docs/plans/01 WS-4)."""

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas import MeOverview
from app.services import dbctx, me

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/overview")
def overview(db: DbSession, user: CurrentUser) -> MeOverview:
    """My latest Match Maps and Scrims, and my Focus points from the last five."""
    if user.player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This login is not tied to a Player")
    with dbctx.using(db):
        return MeOverview(**me.build(user.player))
