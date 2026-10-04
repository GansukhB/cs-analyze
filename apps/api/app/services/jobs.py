"""Driving an :class:`~app.models.AnalysisJob`: status, story, live push.

Every status change goes through here so four things stay in step: the row in
the database, the ordered story of events, the stage-by-stage record the page's
checklist reads, and the live channel the browser is listening on. A dropped
WebSocket costs nothing -- the page re-reads the same rows on load.

Three kinds of update, and the difference matters:

* :func:`log` -- one line of the story. A row, kept forever, readable back.
* :func:`activity` -- what is happening *right now* inside a step: bytes of an
  archive, files of an extract, which ingest pass is running. Pushed on every
  call, stored only every few seconds, and never a row.
* :func:`set_stage` / :func:`finish_stage` -- the coarse ladder, with timings
  and tallies, so a finished job still shows where its time went.

Every function takes the session that owns ``job``. In the worker that is a
session of its own, separate from the one the pipeline writes data through:
these functions commit constantly, and committing the data session would
commit half an ingest. Ported from cstat's ``hltv/services/jobs.py``.
"""

from __future__ import annotations

import copy
import datetime as dt
import logging
import time
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import AnalysisEvent, AnalysisJob, EventLevel, JobStage, JobStatus
from app.models.base import utcnow
from app.services import live

logger = logging.getLogger(__name__)

# How often an activity snapshot is written to the row. Pushing is free; writing
# is not, and nothing reads the stored copy except a page load or a poll.
ACTIVITY_PERSIST_SEC = 3.0

# The ladder every job climbs, in order. Queued and done are not steps, so they
# stay out of the checklist. Analysing and rendering join when the report does.
LADDER = (JobStage.RESOLVING, JobStage.FETCHING, JobStage.UNPACKING, JobStage.PARSING)

STAGE_LABELS = {
    JobStage.QUEUED: "Queued",
    JobStage.RESOLVING: "Resolving teams",
    JobStage.FETCHING: "Downloading demos",
    JobStage.UNPACKING: "Unpacking archives",
    JobStage.PARSING: "Parsing demos",
    JobStage.DONE: "Done",
}


def iso(value: dt.datetime | None) -> str | None:
    """Naive UTC (how datetimes are stored) as an ISO string a browser reads as UTC."""
    return value.replace(tzinfo=dt.UTC).isoformat() if value else None


def _json_safe(value):
    """Make ``value`` safe to store in a JSON column.

    MySQL's ``SUM()``/``AVG()`` promote integers to DECIMAL, which ``json.dumps``
    cannot serialize. Recurses through dicts and lists.
    """
    if isinstance(value, Decimal):
        as_int = int(value)
        return as_int if as_int == value else float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    return value


# -- the queue ----------------------------------------------------------------
# Two analysis jobs must never run at once: they walk the same disk (data/demos,
# data/maps), the same parquet cache and, when downloading, the same
# Cloudflare-cleared browser session. The worker's threads pool runs more than
# one task at a time, so single-flight is enforced here: a new job is only handed
# to Celery if nothing else is RUNNING or already sitting in the broker, and
# every terminal state (`finish`/`fail`/`cancel`) hands on the next-oldest
# waiting job. A job that loses the race stays QUEUED with no `celery_task_id`.
def _in_flight():
    """Jobs that occupy the one slot: running, or sent to Celery and waiting."""
    return select(AnalysisJob).where(
        or_(
            AnalysisJob.status == JobStatus.RUNNING,
            and_(AnalysisJob.status == JobStatus.QUEUED, AnalysisJob.celery_task_id != ""),
        )
    )


def _dispatch(db: Session, job: AnalysisJob) -> None:
    """Hand `job` to Celery right now. Never raises -- a broker failure fails
    the job rather than the caller."""
    from app.tasks import run_analysis

    try:
        async_result = run_analysis.delay(job.id)
    except Exception as exc:
        logger.exception("could not queue job %s", job.public_id)
        fail(
            db,
            job,
            f"Celery broker-т хүрсэнгүй ({exc}). Redis ажиллаж байна уу, worker асаалттай юу?",
        )
        return
    job.celery_task_id = async_result.id
    db.commit()
    log(db, job, "Дараалалд орлоо — worker process хүлээж байна.", stage=JobStage.QUEUED)


def enqueue(db: Session, job: AnalysisJob) -> None:
    """Start `job` now, or leave it queued behind whatever is already in flight.

    ``FOR UPDATE`` makes two near-simultaneous submissions resolve to one running
    and one waiting on MySQL; SQLite (tests) ignores it.
    """
    blocked = db.scalars(_in_flight().where(AnalysisJob.id != job.id).with_for_update()).first()
    db.commit()
    if blocked is not None:
        log(
            db,
            job,
            "Өмнөх job ажиллаж дуусахыг хүлээж байна — дуусмагц автоматаар эхэлнэ.",
            stage=JobStage.QUEUED,
        )
        return
    _dispatch(db, job)


def start_next(db: Session, after: AnalysisJob | None = None) -> None:
    """Start the longest-waiting queued job, if the slot is free.

    Called whenever a job stops being in flight. Re-checks the slot itself, so
    a call while something else still runs is a no-op. A candidate whose STOP
    was pressed while it waited is finalised as cancelled instead of started.
    """
    busy = db.scalars(_in_flight().with_for_update()).first()
    candidate = None
    if busy is None:
        waiting = [AnalysisJob.status == JobStatus.QUEUED, AnalysisJob.celery_task_id == ""]
        if after is not None:
            waiting.append(AnalysisJob.id != after.id)
        candidate = db.scalars(
            select(AnalysisJob)
            .where(*waiting)
            .order_by(AnalysisJob.created_at, AnalysisJob.id)
            .with_for_update()
        ).first()
    db.commit()
    if candidate is None:
        return
    if candidate.cancel_requested:
        cancel(db, candidate)
        return
    _dispatch(db, candidate)


def recover(db: Session) -> None:
    """Pick the queue back up when the worker starts, from the rows alone.

    There is one worker, so at its start nothing can be running: a RUNNING row
    is a job the previous process died in (a deploy's SIGKILL, the OOM killer)
    and would otherwise hold the slot forever. It is failed. A job that was
    sent to Celery but never started loses its task id, because the caller
    purged the broker first, and is sent again in its turn; ``run_analysis``
    ignores any old message that resurfaces.
    """
    orphans = db.scalars(select(AnalysisJob).where(AnalysisJob.status == JobStatus.RUNNING)).all()
    for job in db.scalars(
        select(AnalysisJob).where(
            AnalysisJob.status == JobStatus.QUEUED, AnalysisJob.celery_task_id != ""
        )
    ):
        job.celery_task_id = ""
    db.commit()
    for job in orphans:
        fail(db, job, "Worker дахин эхэлсэн тул энэ job дундаа тасарлаа. Дахин эхлүүлнэ үү.")
    start_next(db)


# -- the story ---------------------------------------------------------------
def event_payload(event: AnalysisEvent) -> dict:
    return {
        "id": event.id,
        "level": event.level,
        "stage": event.stage,
        "message": event.message,
        "payload": event.payload or {},
        "at": iso(event.created_at),
    }


def log(
    db: Session,
    job: AnalysisJob,
    message: str,
    *,
    level: str = EventLevel.INFO,
    stage: str = "",
    payload: dict | None = None,
    step: tuple[int, int] | None = None,
) -> AnalysisEvent:
    """Append to the job's story and mirror it to any live watcher.

    ``step=(3, 7)`` marks the line as the third of seven items in this stage. It
    goes in the payload rather than the text so the page can put it in its own
    column.
    """
    data = _json_safe(dict(payload or {}))
    if step:
        data["step"], data["steps"] = int(step[0]), int(step[1])
    event = AnalysisEvent(
        job_id=job.id, level=level, stage=stage or job.stage, message=message, payload=data
    )
    db.add(event)
    db.commit()
    live.publish(job.public_id, "event", event_payload(event))
    return event


_activity_written_at: dict[int, float] = {}


def activity(
    db: Session,
    job: AnalysisJob,
    *,
    key: str,
    text: str,
    stage: str = "",
    pct: float | None = None,
    done: int | None = None,
    total: int | None = None,
    data: dict | None = None,
    force: bool = False,
) -> None:
    """Report what the current step is doing, without writing a story line.

    The push is cheap; the row is written at most every
    :data:`ACTIVITY_PERSIST_SEC` seconds, or immediately with ``force``.
    """
    snapshot = {
        "key": key,
        "text": text,
        "stage": stage or job.stage,
        "pct": None if pct is None else max(0, min(100, round(float(pct)))),
        "done": done,
        "total": total,
        "at": iso(utcnow()),
    }
    if data:
        snapshot.update(data)
    snapshot = _json_safe(snapshot)
    job.activity = snapshot
    live.publish(job.public_id, "activity", snapshot)

    now = time.monotonic()
    if force or now - _activity_written_at.get(job.id, 0.0) >= ACTIVITY_PERSIST_SEC:
        _activity_written_at[job.id] = now
        db.commit()


def clear_activity(db: Session, job: AnalysisJob) -> None:
    """Forget the current step -- nothing is in progress any more."""
    job.activity = {}
    _activity_written_at.pop(job.id, None)
    db.commit()
    live.publish(job.public_id, "activity", {})


# -- the stage ladder --------------------------------------------------------
def _closed(entries: list) -> list:
    """A copy of the stage log with an end time stamped on anything still open."""
    now = utcnow()
    out = copy.deepcopy(entries or [])
    for entry in out:
        if entry.get("finished_at"):
            continue
        entry["finished_at"] = iso(now)
        started = entry.get("started_at")
        if started:
            try:
                begun = dt.datetime.fromisoformat(started).replace(tzinfo=None)
                entry["seconds"] = round((now - begun).total_seconds(), 1)
            except (TypeError, ValueError):
                entry["seconds"] = None
    return out


def _set_stage_log(job: AnalysisJob, entries: list) -> None:
    # JSON columns don't track in-place edits; reassign and flag explicitly.
    job.stage_log = entries
    flag_modified(job, "stage_log")


def set_stage(
    db: Session,
    job: AnalysisJob,
    stage: str,
    progress: int,
    message: str = "",
    cycle: tuple[int, int] | None = None,
) -> None:
    """Move to ``stage``, closing the previous one in the stage log.

    ``cycle`` is ``(n, of)`` while the run goes match by match: downloading,
    unpacking and parsing repeat for every match, and each repeat opens a new
    entry tagged with the match it belongs to.
    """
    current = (job.stage_log or [])[-1:] or [{}]
    moved = job.stage != stage or (cycle is not None and current[0].get("cycle") != cycle[0])
    if moved:
        entry = {
            "stage": stage,
            "label": STAGE_LABELS.get(stage, stage),
            "started_at": iso(utcnow()),
            "finished_at": None,
            "seconds": None,
            "summary": "",
            "counts": {},
        }
        if cycle is not None:
            entry["cycle"], entry["cycles"] = cycle
        _set_stage_log(job, _closed(job.stage_log) + [entry])
    job.stage = stage
    job.progress = max(0, min(100, progress))
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.RUNNING
        job.started_at = job.started_at or utcnow()
    db.commit()

    live.publish(job.public_id, "status", status_payload(job))
    if message:
        log(db, job, message, stage=stage)


def finish_stage(
    db: Session, job: AnalysisJob, stage: str, summary: str = "", counts: dict | None = None
) -> None:
    """Record what a stage actually did, so the checklist can say it in one line."""
    entries = copy.deepcopy(job.stage_log or [])
    for entry in reversed(entries):
        if entry.get("stage") == stage:
            entry["summary"] = summary or entry.get("summary", "")
            if counts:
                entry["counts"] = _json_safe({k: v for k, v in counts.items() if v})
            break
    _set_stage_log(job, entries)
    job.activity = {}
    db.commit()
    live.publish(job.public_id, "status", status_payload(job))


def _terminate(job: AnalysisJob, status: str) -> None:
    job.status = status
    job.finished_at = utcnow()
    _set_stage_log(job, _closed(job.stage_log))
    job.activity = {}


def finish(db: Session, job: AnalysisJob, result: dict) -> None:
    _terminate(job, JobStatus.SUCCESS)
    job.stage = JobStage.DONE
    job.progress = 100
    job.result = _json_safe(result)
    db.commit()
    log(db, job, "Татах ба боловсруулах ажил дууслаа.", level=EventLevel.SUCCESS)
    live.publish(job.public_id, "status", status_payload(job))
    start_next(db, job)


def fail(db: Session, job: AnalysisJob, error: str) -> None:
    _terminate(job, JobStatus.FAILED)
    job.error = str(error)[:4000]
    db.commit()
    log(db, job, str(error)[:500], level=EventLevel.ERROR)
    live.publish(job.public_id, "status", status_payload(job))
    start_next(db, job)


class JobCancelled(Exception):
    """Raised inside a running task once :func:`check_cancelled` sees the flag.

    The threads pool cannot force-kill a running task, so the STOP button only
    sets a flag on the row, and the task notices it between items (one match,
    one archive, one demo) and stops itself -- never mid file-write.
    """


def check_cancelled(db: Session, job: AnalysisJob) -> None:
    """Raise :class:`JobCancelled` if the STOP button has been pressed.

    Reads the one column on a fresh connection: the flag is set by the API
    process, and the job session may be sitting in a transaction that would
    not see it (or would block it with a pending UPDATE of the same row).
    """
    with db.get_bind().connect() as conn:
        requested = conn.scalar(
            select(AnalysisJob.cancel_requested).where(AnalysisJob.id == job.id)
        )
    if requested:
        raise JobCancelled()


def cancel(db: Session, job: AnalysisJob) -> None:
    """Finalise a job that stopped after a STOP request (a status, not an error)."""
    _terminate(job, JobStatus.CANCELLED)
    db.commit()
    log(db, job, "Хэрэглэгч зогсоолоо.", level=EventLevel.WARNING)
    live.publish(job.public_id, "status", status_payload(job))
    start_next(db, job)


def status_payload(job: AnalysisJob) -> dict:
    return {
        "public_id": str(job.public_id),
        "status": job.status,
        "stage": job.stage,
        "stage_label": STAGE_LABELS.get(job.stage, job.stage),
        "progress": job.progress,
        "error": job.error,
        "duration": job.duration_seconds,
        "finished": job.is_finished,
        "activity": job.activity or {},
        "stages": stage_ladder(job),
        "cycle": current_cycle(job),
    }


def current_cycle(job: AnalysisJob) -> dict | None:
    """``{n, of}``: which match a match-by-match run is on, or None."""
    for entry in reversed(job.stage_log or []):
        if entry.get("cycle"):
            return {"n": entry["cycle"], "of": entry.get("cycles") or entry["cycle"]}
    return None


def stage_ladder(job: AnalysisJob) -> list:
    """Every stage of the run with its state, for the page's checklist.

    Merges what happened (``stage_log``) with what has not happened yet, so the
    reader sees the whole route rather than only the part already travelled.
    """
    logged = {entry.get("stage"): entry for entry in job.stage_log or []}
    failed = job.status == JobStatus.FAILED
    # On a match-by-match run, the stages after the current one have not yet
    # happened *for this match*, whatever the previous match did.
    cycle = (current_cycle(job) or {}).get("n")
    position = LADDER.index(job.stage) if job.stage in LADDER else -1
    rows = []
    for index, stage in enumerate(LADDER):
        entry = logged.get(stage) or {}
        later_this_match = (
            cycle is not None
            and not job.is_finished
            and index > position
            and (entry.get("cycle") or 0) < cycle
        )
        if later_this_match:
            state = "pending"
        elif entry.get("finished_at"):
            state = "failed" if (failed and stage == job.stage) else "done"
        elif stage == job.stage and not job.is_finished:
            state = "running"
        elif stage == job.stage and failed:
            state = "failed"
        elif entry:
            state = "done"
        else:
            state = "pending"
        rows.append(
            {
                "stage": stage,
                "label": STAGE_LABELS.get(stage, stage),
                "state": state,
                "seconds": entry.get("seconds"),
                "summary": entry.get("summary") or "",
                "counts": entry.get("counts") or {},
            }
        )
    return rows
