"""The Round search (docs/plans/09 VIZ-7): "find me Rounds like this"."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, status

from app.deps import DbSession, StaffUser
from app.schemas import SearchAsk, SearchResult
from app.services import dbctx, round_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/places/{map_name}")
def places(map_name: str, db: DbSession, _: StaffUser) -> list[str]:
    """The Callouts a condition can name on this Map, the most used first."""
    if not re.fullmatch(r"de_[a-z0-9_]{2,30}", map_name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such map: {map_name}")
    with dbctx.using(db):
        return round_search.places(map_name)


@router.get("/spots/{map_name}")
def spot_names(map_name: str, _: StaffUser) -> list[str]:
    """The hand-drawn Spots a condition can name on this Map (VIZ-7)."""
    if not re.fullmatch(r"de_[a-z0-9_]{2,30}", map_name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No such map: {map_name}")
    return round_search.spot_names(map_name)


@router.post("/rounds")
def rounds(body: SearchAsk, db: DbSession, _: StaffUser) -> SearchResult:
    """Every Round where all the conditions held for the Side, newest first."""
    with dbctx.using(db):
        found = round_search.search(
            body.map_name, body.side, [c.model_dump() for c in body.conditions], body.team_id,
            body.buy, body.heat, body.score,
        )  # fmt: skip
    return SearchResult(**found)
