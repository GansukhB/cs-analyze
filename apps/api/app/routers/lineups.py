"""The lineup library (docs/plans/08 SB-3): grenades thrown the same way again,
with the practice-server command that puts you on the spot."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas import Lineup
from app.services import dbctx, lineups

router = APIRouter(prefix="/lineups", tags=["lineups"])


@router.get("/{map_name}", response_model_by_alias=True)
def library(
    map_name: str,
    db: DbSession,
    _: CurrentUser,
    side: str | None = None,
    type: str | None = None,
    team: str | None = None,
) -> list[Lineup]:
    """Every lineup on the Map, the most thrown first; by Side, kind or a Team."""
    if not re.fullmatch(r"de_[a-z0-9_]{2,30}", map_name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such map: {map_name}")
    with dbctx.using(db):
        found = lineups.library(map_name)
    if side:
        found = [lu for lu in found if lu["side"] == side]
    if type:
        found = [lu for lu in found if lu["type"] == type]
    if team:
        found = [lu for lu in found if any(t == team for t, _n in lu["teams"])]
    return [Lineup(**lu) for lu in found]
