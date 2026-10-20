"""A Player's page (docs/plans/04-player-analytics.md PL-2), by Steam id."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status

from app.deps import CurrentUser, DbSession
from app.schemas import PlayerPage
from app.services import dbctx, player_page

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/{steamid}")
def player(
    steamid: Annotated[str, Path(pattern=r"^\d{1,20}$")], db: DbSession, user: CurrentUser
) -> PlayerPage:
    """Form, numbers by Map and Side, Findings against every Player's, spots, guns.

    The Steam id is a string in the path, as everywhere the browser holds one:
    as a JavaScript number it would lose its last digits. A Player login sees
    only their own (docs/plans WS-4)."""
    if not user.is_staff and (user.player is None or str(user.player.steamid) != steamid):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such player")
    with dbctx.using(db):
        built = player_page.build(int(steamid))
    if built is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such player")
    return PlayerPage(**built)
