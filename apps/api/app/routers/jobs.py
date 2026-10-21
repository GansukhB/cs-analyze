"""Scout jobs over HTTP, plus the WebSocket that streams one job's progress.

The HTTP side mirrors cstat's views: the home page's data, the job list, one job
(also the polling fallback, with ``?after=<event id>``), STOP, and the worker
panel. The socket is read-only: the browser never sends anything that changes a
job, only the token it authenticates with.
"""

import asyncio
import contextlib
import threading
import time
import uuid
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from fastapi.concurrency import run_in_threadpool
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app import db as database
from app.celery_app import celery_app
from app.config import get_settings
from app.deps import DbSession, StaffUser, user_from_token
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
    JobTimings,
    JobWords,
    ScoutDefaults,
)
from app.services import jobs as job_service
from app.services import live, mn, system

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
def home(db: DbSession, _: StaffUser) -> HomeInfo:
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
        # HLTV has several Teams of one name (dead rosters, academies): one entry each.
        known_teams=list(dict.fromkeys(teams)),
        parsed_maps=parsed or 0,
        defaults=ScoutDefaults(
            matches=settings.analysis_default_matches, max_matches=settings.analysis_max_matches
        ),
    )


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(body: JobCreate, db: DbSession, user: StaffUser) -> JobRow:
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
def list_jobs(db: DbSession, _: StaffUser) -> JobList:
    """The process viewer: every run, newest first."""
    rows = db.scalars(_jobs_query().order_by(AnalysisJob.created_at.desc()).limit(100))
    counts = dict(
        db.execute(select(AnalysisJob.status, func.count()).group_by(AnalysisJob.status)).all()
    )
    return JobList(
        jobs=[JobRow.of(j) for j in rows],
        counts={s.value: counts.get(s.value, 0) for s in JobStatus},
    )


@router.get("/jobs/timings")
def job_timings(db: DbSession, _: StaffUser) -> JobTimings:
    """Median seconds per archive downloaded and unpacked, per Map parsed and per
    Match, over the latest finished Scouts (OPS-5)."""
    return JobTimings(**job_service.timings(db))


@router.get("/jobs/{public_id}")
def get_job(
    public_id: uuid.UUID,
    db: DbSession,
    _: StaffUser,
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
def cancel_job(public_id: uuid.UUID, db: DbSession, _: StaffUser) -> JobStatusPayload:
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


def redact_url(url: str) -> str:
    """The broker URL without its credentials: in production it carries the Redis
    ACL user and password, and every User can open the Jobs page."""
    parts = urlsplit(url)
    if not parts.hostname:
        return parts.scheme + "://"
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    if parts.username or parts.password:
        host = "***@" + host
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


# `inspect` is a broadcast that waits out its whole timeout when nobody answers,
# and the Jobs page polls every 4 s; one answer serves the polls of the next 15 s.
INSPECT_TTL_SECONDS = 15.0
_inspect_lock = threading.Lock()
_inspected: dict = {"at": 0.0, "active": {}}


def _active_tasks() -> dict:
    with _inspect_lock:
        if time.monotonic() - _inspected["at"] >= INSPECT_TTL_SECONDS:
            _inspected["active"] = celery_app.control.inspect(timeout=1).active() or {}
            _inspected["at"] = time.monotonic()
        return _inspected["active"]


@router.get("/workers")
def workers(_: StaffUser) -> BrokerState:
    """What Redis and the workers say about themselves right now."""
    settings = get_settings()
    state = BrokerState(
        redis_url=redact_url(settings.redis_broker_url),
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
        state.error = f"Redis unreachable: {type(exc).__name__}"
        return state
    if not system.worker_alive():
        # No heartbeat: no worker to ask, so don't wait out a broadcast nobody answers.
        return state
    try:
        active = _active_tasks()
        state.workers = sorted(active)
        state.active = [
            {"worker": worker, "task": task.get("name"), "id": task.get("id")}
            for worker, tasks in active.items()
            for task in tasks
        ]
    except Exception as exc:  # inspection is best-effort; the queue length is the fact
        state.error = f"No worker responded: {type(exc).__name__}"
    return state


# -- live ----------------------------------------------------------------------
# The socket can stay open for hours; each read opens its own short session
# instead of holding one (and a pooled connection) for the socket's lifetime.
def _authenticated(token: str | None) -> bool:
    with database.SessionLocal() as db:
        user = user_from_token(db, token)
        return user is not None and user.is_staff


def _snapshot(public_id: uuid.UUID) -> dict | None:
    with database.SessionLocal() as db:
        job = db.scalar(select(AnalysisJob).where(AnalysisJob.public_id == public_id))
        if job is None:
            return None
        payload = job_service.status_payload(job)
        payload["events"] = _events(db, job, None, SNAPSHOT_EVENTS)
        return payload


@router.websocket("/ws/jobs/{public_id}")
async def job_socket(ws: WebSocket, public_id: uuid.UUID) -> None:
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
    if not await run_in_threadpool(_authenticated, token):
        await ws.close(code=4401)
        return

    # Subscribe before reading the snapshot, so nothing published in between is
    # lost; the browser drops events it already has by id.
    async with live.subscribe(public_id) as messages:
        snapshot = await run_in_threadpool(_snapshot, public_id)
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
