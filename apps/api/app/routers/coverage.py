"""What the stored data covers, and what it lacks (docs/plans/02 DATA-9)."""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import DbSession, StaffUser
from app.schemas import Coverage
from app.services import coverage

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/coverage")
def data_coverage(db: DbSession, user: StaffUser) -> Coverage:
    """Each Team's parsed Match Maps and what they lack, each Map's Pool, and the
    Match Maps a Scout would download again. The Workspace's Teams come first."""
    found = coverage.overview(db, user.workspace_id)
    return Coverage(schema_version=found.pop("schema"), **found)
