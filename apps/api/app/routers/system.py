"""The footer's one request: the host's load, the worker's pulse, the Scouts."""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession
from app.models import AnalysisJob, JobStatus
from app.schemas import HostStats, JobCycle, ScoutNow, SystemState
from app.services import jobs as job_service
from app.services import system

router = APIRouter(tags=["system"])


@router.get("/system")
def system_state(db: DbSession, _: CurrentUser) -> SystemState:
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
    )
