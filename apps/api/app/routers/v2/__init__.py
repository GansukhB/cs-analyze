"""The v2 pages' endpoints (the DEMOLAB design), all under /v2 and Staff's.

Each screen that needs a shape the v1 endpoints don't return has its module
here; the pages call v1 endpoints wherever one already answers.
"""

from fastapi import APIRouter

from app.routers.v2 import matches, overview, players, scouting, upcoming

router = APIRouter(prefix="/v2", tags=["v2"])
router.include_router(overview.router)
router.include_router(upcoming.router)
router.include_router(matches.router)
router.include_router(players.router)
router.include_router(scouting.router)
