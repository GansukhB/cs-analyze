"""Scout jobs over HTTP, plus the WebSocket that streams one job's progress.

The HTTP side mirrors cstat's views: the home page's data, the job list, one job
(also the polling fallback, with ``?after=<event id>``), STOP, and the worker
panel. The socket is read-only: the browser never sends anything that changes a
job, only the token it authenticates with.
"""

import asyncio
import contextlib
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.concurrency import run_in_threadpool
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.celery_app import celery_app
from app.config import get_settings
from app.deps import CurrentUser, DbSession, user_from_token
from app.models import AnalysisEvent, AnalysisJob, JobStatus, MatchMap, Team
from app.schemas import (
    BrokerState,
    HomeInfo,
    JobCreate,
    JobDetail,
    JobList,
    JobResult,
    JobRow,
    JobStatusPayload,
    JobWords,
    ScoutDefaults,
)
from app.services import jobs as job_service
from app.services import live, mn

router = APIRouter(tags=["jobs"])

WORDS = JobWords(stages=mn.STAGES, counts=mn.COUNTS)
SNAPSHOT_EVENTS = 500
POLL_EVENTS = 200


def _jobs_query():
    return select(AnalysisJob).options(joinedload(AnalysisJob.requested_by))


def _get_job(db: Session, public_id: uuid.UUID) -> AnalysisJob:
    job = db.scalar(_jobs_query().where(AnalysisJob.public_id == public_id))
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job")
    return job


def _events(db: Session, job: AnalysisJob, after: int | None, limit: int) -> list[dict]:
    query = select(AnalysisEvent).where(AnalysisEvent.job_id == job.id)
    if after:
        query = query.where(AnalysisEvent.id > after)
    rows = db.scalars(query.order_by(AnalysisEvent.id).limit(limit))
    return [job_service.event_payload(e) for e in rows]


@router.get("/home")
def home(db: DbSession, _: CurrentUser) -> HomeInfo:
    """What the scout form shows around itself."""
    settings = get_settings()
    recent = db.scalars(_jobs_query().order_by(AnalysisJob.created_at.desc()).limit(8))
    teams = db.scalars(
        select(Team.name).where(Team.hltv_id.is_not(None)).order_by(Team.name).limit(40)
    )
    parsed = db.scalar(
        select(func.count()).select_from(MatchMap).where(MatchMap.parsed_at.is_not(None))
    )
    return HomeInfo(
        recent_jobs=[JobRow.of(j) for j in recent],
        known_teams=list(teams),
        parsed_maps=parsed or 0,
        defaults=ScoutDefaults(
            matches=settings.analysis_default_matches, max_matches=settings.analysis_max_matches
        ),
    )


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(body: JobCreate, db: DbSession, user: CurrentUser) -> JobRow:
    job = AnalysisJob(
        my_team_name=body.my_team,
        opponent_name=body.opponent,
        n_my_matches=body.n_my_matches,
        n_opponent_matches=body.n_opponent_matches,
        n_h2h_matches=body.n_h2h_matches,
        download=body.download,
        requested_by_id=user.id,
    )
    db.add(job)
    db.commit()
    job_service.enqueue(db, job)
    return JobRow.of(job)


@router.get("/jobs")
def list_jobs(db: DbSession, _: CurrentUser) -> JobList:
    """The process viewer: every run, newest first."""
    rows = db.scalars(_jobs_query().order_by(AnalysisJob.created_at.desc()).limit(100))
    counts = dict(
        db.execute(select(AnalysisJob.status, func.count()).group_by(AnalysisJob.status)).all()
    )
    return JobList(
        jobs=[JobRow.of(j) for j in rows],
        counts={s.value: counts.get(s.value, 0) for s in JobStatus},
    )


@router.get("/jobs/{public_id}")
def get_job(
    public_id: uuid.UUID,
    db: DbSession,
    _: CurrentUser,
    after: Annotated[int | None, Query(description="Only events after this id")] = None,
) -> JobDetail:
    """One job: also the polling fallback when the WebSocket is unavailable."""
    job = _get_job(db, public_id)
    return JobDetail(
        job=JobRow.of(job),
        status=JobStatusPayload(**job_service.status_payload(job)),
        events=_events(db, job, after, POLL_EVENTS if after else SNAPSHOT_EVENTS),
        result=JobResult(**job.result) if job.result else None,
        words=WORDS,
    )


@router.post("/jobs/{public_id}/cancel")
def cancel_job(public_id: uuid.UUID, db: DbSession, _: CurrentUser) -> JobStatusPayload:
    """STOP. A running job is asked to stop itself between items (the threads
    pool cannot kill it); a job still queued is revoked and finalised here,
    since nothing would ever poll the flag for a task that never runs."""
    job = _get_job(db, public_id)
    if not job.is_finished:
        job.cancel_requested = True
        db.commit()
        if job.celery_task_id:
            with contextlib.suppress(Exception):
                celery_app.control.revoke(job.celery_task_id)
        if job.status == JobStatus.QUEUED:
            job_service.cancel(db, job)
    return JobStatusPayload(**job_service.status_payload(job))


@router.get("/workers")
def workers(_: CurrentUser) -> BrokerState:
    """What Redis and the workers say about themselves right now."""
    settings = get_settings()
    state = BrokerState(
        redis_url=settings.redis_broker_url,
        connected=False,
        queued=None,
        workers=[],
        active=[],
        error="",
    )
    try:
        client = Redis.from_url(settings.redis_broker_url, socket_connect_timeout=1)
        client.ping()
        state.connected = True
        state.queued = client.llen(settings.celery_queue)
    except Exception as exc:
        state.error = f"Redis unreachable: {exc}"
        return state
    try:
        active = celery_app.control.inspect(timeout=1).active() or {}
        state.workers = sorted(active)
        state.active = [
            {"worker": worker, "task": task.get("name"), "id": task.get("id")}
            for worker, tasks in active.items()
            for task in tasks
        ]
    except Exception as exc:  # inspection is best-effort; the queue length is the fact
        state.error = f"No worker responded: {exc}"
    return state


# -- live ----------------------------------------------------------------------
def _snapshot(db: Session, public_id: uuid.UUID) -> dict | None:
    job = db.scalar(select(AnalysisJob).where(AnalysisJob.public_id == public_id))
    if job is None:
        return None
    payload = job_service.status_payload(job)
    payload["events"] = _events(db, job, None, SNAPSHOT_EVENTS)
    return payload


@router.websocket("/ws/jobs/{public_id}")
async def job_socket(ws: WebSocket, public_id: uuid.UUID, db: DbSession) -> None:
    """Snapshot on connect, then every message the worker publishes for this job.

    The first client message must be ``{"token": "<jwt>"}`` (browsers cannot set
    an Authorization header on a WebSocket, and a token in the URL ends up in
    access logs). Close codes: 4401 not authenticated, 4404 no such job.
    """
    await ws.accept()
    try:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=10)
        token = hello.get("token") if isinstance(hello, dict) else None
    except (TimeoutError, WebSocketDisconnect, ValueError):
        await ws.close(code=4401)
        return
    if await run_in_threadpool(user_from_token, db, token) is None:
        await ws.close(code=4401)
        return

    # Subscribe before reading the snapshot, so nothing published in between is
    # lost; the browser drops events it already has by id.
    async with live.subscribe(public_id) as messages:
        snapshot = await run_in_threadpool(_snapshot, db, public_id)
        if snapshot is None:
            await ws.close(code=4404)
            return
        await ws.send_json({"kind": "snapshot", "payload": snapshot})

        async def relay() -> None:
            async for message in messages:
                await ws.send_json(message)

        async def until_closed() -> None:
            with contextlib.suppress(WebSocketDisconnect):
                while True:
                    await ws.receive_text()

        tasks = {asyncio.create_task(relay()), asyncio.create_task(until_closed())}
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
