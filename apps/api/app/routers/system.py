"""The footer's one request: the host's load, the worker's pulse, the Scouts."""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import DbSession, StaffUser
from app.models import AnalysisJob, JobStatus
from app.schemas import HostStats, JobCycle, PatchList, PatchRef, ScoutNow, SystemState
from app.services import jobs as job_service
from app.services import map_pool, patches, system
from app.services.dbctx import using

router = APIRouter(tags=["system"])


@router.get("/system")
def system_state(db: DbSession, _: StaffUser) -> SystemState:
    # Single-flight (jobs.enqueue): at most one runs, the rest wait QUEUED.
    running = db.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.status == JobStatus.RUNNING)
        .order_by(AnalysisJob.started_at.desc())
        .limit(1)
    )
    queued = db.scalar(
        select(func.count()).select_from(AnalysisJob).where(AnalysisJob.status == JobStatus.QUEUED)
    )
    scout = None
    if running is not None:
        cycle = job_service.current_cycle(running)
        scout = ScoutNow(
            public_id=running.public_id,
            label=running.label,
            stage_label=job_service.STAGE_LABELS.get(running.stage, running.stage),
            cycle=JobCycle(**cycle) if cycle else None,
        )
    return SystemState(
        host=HostStats(**system.host()),
        worker=system.worker_alive(),
        scout=scout,
        queued=queued or 0,
        version=get_settings().deployed_commit,
    )


@router.get("/patches")
def patch_list(db: DbSession, _: StaffUser) -> PatchList:
    """The patches that start an era, newest first, and today's Active Duty (DATA-7)."""
    with using(db):
        active = list(map_pool.active_duty())
    return PatchList(patches=[PatchRef(**p) for p in reversed(patches.every())], active=active)
