"""What the stored data covers, and what it lacks (docs/plans/02 DATA-9)."""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import DbSession, StaffUser
from app.schemas import Coverage, MomentumRow
from app.services import coverage, dbctx, momentum

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/coverage")
def data_coverage(db: DbSession, user: StaffUser) -> Coverage:
    """Each Team's parsed Match Maps and what they lack, each Map's Pool, and the
    Match Maps a Scout would download again. The Workspace's Teams come first."""
    found = coverage.overview(db, user.workspace_id)
    return Coverage(schema_version=found.pop("schema"), **found)


@router.get("/momentum")
def data_momentum(db: DbSession, _: StaffUser) -> list[MomentumRow]:
    """TM-11, on the Pool only: after a streak of three or more, the next Round won
    against what the two buys expected, and with the other Team's timeout or not."""
    with dbctx.using(db):
        return [MomentumRow(**row) for row in momentum.study()]
