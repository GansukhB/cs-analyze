"""The background job: from two team names to downloaded, parsed demos.

Runs the pipeline for both teams -- resolve, download, unpack, parse -- reporting
progress at every step so the page watching over the WebSocket has something
true to show. (cstat goes on to build a scouting report and render heatmaps;
those stages arrive when the report does.)

It goes **one match at a time**: download, unpack, parse, then delete that
match's files before the next one starts, so the scratch folder never holds
more than one match (~1-2 GB) and nothing outlives the run
(docs/adr/0002-tick-data-in-mysql.md). What a parse produces -- the analysis
rows and the map's Tick Data -- is in MySQL; ``data/`` is scratch. Each step
reuses the services, so a job inherits their skip rules: a match already parsed
is not fetched again, and a map on an old schema is parsed again from its
stored Tick Data instead of its Demo. A second job for the same teams is
mostly instant.

Which is exactly why the log has to be specific. Most of what a run does is
*skip* something, and "skipping" without the reason is indistinguishable from a
job that quietly did nothing. So every item says which match it is, who played
whom, and why it took the path it took -- and the slow parts (a 500 MB
download, a ten-second ingest) report inside themselves through
:func:`app.services.jobs.activity`.

Two sessions per run: ``job_db`` owns the job row and its story and commits
constantly; ``db`` writes the data. See :mod:`app.services.jobs`.

Ported from cstat's ``hltv/tasks.py``; the wording lives in :mod:`app.services.mn`.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
import traceback
import uuid
from collections import deque
from pathlib import Path

from celery.signals import worker_ready, worker_shutdown
from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session, object_session

from app.celery_app import celery_app
from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    AnalysisJob,
    Demo,
    EventLevel,
    JobKind,
    JobStage,
    JobStatus,
    MapRoster,
    Match,
    MatchMap,
    Team,
    TickDataset,
    Upload,
    UploadStatus,
)
from app.models.base import utcnow
from app.services import (
    analysis_store,
    dbctx,
    gameplan,
    heavy,
    jobs,
    mn,
    review,
    review_pool,
    store,
    system,
    tickdata,
    uploads,
)

logger = logging.getLogger(__name__)

LEVEL = EventLevel
STAGE = JobStage

# Where each stage's share of the progress bar starts and ends. The matches
# share MATCHES between them, and inside one match the download is most of it.
SPAN = {
    STAGE.RESOLVING: (2, 10),
    STAGE.PARSING: (95, 99),
}
MATCHES = (10, 95)
WITHIN_MATCH = {STAGE.FETCHING: 0.0, STAGE.UNPACKING: 0.6, STAGE.PARSING: 0.75}


def _at(stage: str, done: int = 0, total: int = 0) -> int:
    """Where the bar sits ``done`` of ``total`` items into ``stage``."""
    low, high = SPAN[stage]
    if not total:
        return low
    return low + int((high - low) * min(done, total) / total)


def _at_match(stage: str, n: int, of: int) -> int:
    """Where the bar sits when match ``n`` of ``of`` reaches ``stage``."""
    low, high = MATCHES
    share = (n - 1 + WITHIN_MATCH[stage]) / max(of, 1)
    return low + int((high - low) * share)


class _Steps:
    """The ``[3/7]`` counter a stage's items are numbered with."""

    def __init__(self, total: int):
        self.total = total
        self.done = 0

    def next(self) -> tuple[int, int]:
        self.done += 1
        return (self.done, self.total)


@celery_app.task(bind=True, name="cs_analyze.run_analysis")
def run_analysis(self, job_id: int) -> dict:
    """Entry point. Owns error handling so a failure is recorded, not just raised."""
    with SessionLocal() as job_db, SessionLocal() as db:
        job = job_db.get(AnalysisJob, job_id)
        if job is None or not _is_current(job, self.request.id):
            # A message older than the row: the job ran, ended, or was sent again
            # after the worker restarted (see `_recover`).
            logger.warning("skipping a stale message for job %s", job_id)
            return {"job": str(job.public_id) if job else None, "status": "skipped"}
        job.celery_task_id = self.request.id or ""
        job_db.commit()
        try:
            return run_pipeline(job_db, db, job)
        except jobs.JobCancelled:
            db.rollback()
            jobs.cancel(job_db, job)
            return {"job": str(job.public_id), "status": job.status}
        except BaseException as exc:  # anything else would leave the row RUNNING
            logger.exception("analysis job %s failed", job.public_id)
            db.rollback()
            jobs.fail(job_db, job, f"{type(exc).__name__}: {exc}")
            jobs.log(job_db, job, traceback.format_exc()[-2000:], level=LEVEL.DEBUG)
            raise


def _is_current(job: AnalysisJob, task_id: str | None) -> bool:
    """Whether this message is the one the row was last dispatched with. The id
    may still be blank: `jobs._dispatch` stores it just after sending."""
    return job.status == JobStatus.QUEUED and job.celery_task_id in ("", task_id)


@worker_ready.connect
def _recover(**_) -> None:
    """The worker is the only consumer, so at its start the rows are the truth:
    drop whatever the broker still holds and let `jobs.recover` re-dispatch.
    The purge also drops a queued Review refresh, so one is sent again."""
    celery_app.control.purge()
    # Nothing runs yet, so a held heavy permit is a dead worker's (OPS-6).
    heavy.clear()
    with SessionLocal() as db:
        jobs.recover(db)
        # Uploads wait on no slot: the ones the purge dropped go straight back.
        for job in db.scalars(
            select(AnalysisJob).where(
                AnalysisJob.kind == JobKind.UPLOAD,
                AnalysisJob.status == JobStatus.QUEUED,
                AnalysisJob.celery_task_id == "",
            )
        ):
            uploads.dispatch(db, job)
    review_pool.request_refresh(force=True)
    # Beside the queue, not on it: a Scout re-sent above would hold it for an hour.
    threading.Thread(target=gameplan.warm_pool, name="warm-pool", daemon=True).start()


@worker_ready.connect
def _heartbeat(**_) -> None:
    """The footer's worker light (`app/services/system.py`)."""
    system.start_heartbeat()


@worker_shutdown.connect
def _flatline(**_) -> None:
    system.stop_heartbeat()


@celery_app.task(bind=True, name="cs_analyze.ingest_upload")
def ingest_upload(self, job_id: int) -> dict:
    """A Workspace's own Demo file into one private Match (DATA-1), on the parse
    queue: parse it if its parts are still here, then re-ingest any Map whose
    "who is who" Staff have just answered."""
    with SessionLocal() as job_db, SessionLocal() as db:
        job = job_db.get(AnalysisJob, job_id)
        if job is None or not _is_current(job, self.request.id):
            logger.warning("skipping a stale message for upload job %s", job_id)
            return {"job": str(job.public_id) if job else None, "status": "skipped"}
        job.celery_task_id = self.request.id or ""
        job_db.commit()
        upload = db.scalar(select(Upload).where(Upload.job_id == job.id))
        if upload is None:
            jobs.fail(job_db, job, "Энэ job-ын upload алга.")
            return {"job": str(job.public_id), "status": job.status}
        scratch = _scratch(job)
        try:
            out = _ingest_upload(job_db, db, job, upload, scratch)
            jobs.finish(job_db, job, out)
            return out
        except jobs.JobCancelled:
            db.rollback()
            upload.status, upload.error = UploadStatus.FAILED, "Зогсоосон."
            db.commit()
            jobs.cancel(job_db, job)
            return {"job": str(job.public_id), "status": job.status}
        except BaseException as exc:
            logger.exception("upload job %s failed", job.public_id)
            db.rollback()
            upload.status, upload.error = UploadStatus.FAILED, f"{type(exc).__name__}: {exc}"[:2000]
            db.commit()
            jobs.fail(job_db, job, f"{type(exc).__name__}: {exc}")
            jobs.log(job_db, job, traceback.format_exc()[-2000:], level=LEVEL.DEBUG)
            raise
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


def _ingest_upload(job_db, db, job, upload: Upload, scratch: Path) -> dict:
    upload.status = UploadStatus.PARSING
    db.commit()
    match = uploads.match_for(db, upload)
    mine_known = uploads.known_players(db, upload.my_team_id)
    theirs_known = uploads.known_players(db, match.team2_id)
    entries = list(upload.maps or [])
    has_parts = uploads.received(db, upload)[0] > 0

    if has_parts:
        jobs.set_stage(
            job_db, job, STAGE.UNPACKING, 10, mn.UPLOAD_ASSEMBLE.format(name=upload.filename)
        )
        whole = uploads.assemble(db, upload, scratch)
        files = uploads.demo_files(whole, scratch)
        jobs.finish_stage(job_db, job, STAGE.UNPACKING, "", {"demos": len(files)})
        jobs.set_stage(job_db, job, STAGE.PARSING, 30)
        taken = {e["map_number"] for e in entries}
        for path in files:
            jobs.check_cancelled(job_db, job)
            number = max(taken, default=0) + 1
            entry = _ingest_upload_demo(
                job_db, db, job, upload, match, path, number, scratch, mine_known, theirs_known
            )
            if entry is not None:
                taken.add(number)
                entries.append(entry)
                upload.maps = list(entries)
                db.commit()
        uploads.drop_parts(db, upload)

    # "Who is who" answered: the Map again from its stored Tick Data, Teams given.
    for i, entry in enumerate(entries):
        if entry.get("mine") is None or entry.get("assigned"):
            continue
        jobs.check_cancelled(job_db, job)
        entries[i] = _reassign_upload_map(job_db, db, job, upload, match, entry)
        upload.maps = list(entries)
        db.commit()

    analysis_store.rebuild_player_match(db, match)
    _score_upload_match(db, match)
    waiting = [e for e in entries if not e.get("assigned")]
    upload.status = UploadStatus.NEEDS_SIDES if waiting else UploadStatus.DONE
    db.commit()
    jobs.finish_stage(job_db, job, STAGE.PARSING, "", {"maps": len(entries)})
    if waiting:
        jobs.log(
            job_db, job, mn.UPLOAD_WHO.format(n=len(waiting)), level=LEVEL.WARNING,
            stage=STAGE.PARSING,
        )  # fmt: skip
    return {
        "windows": None,
        "parsed_matches": [],
        "scanned": None,
        "h2h_found": None,
        "totals": {"parsing": {"parsed": sum(1 for e in entries if e.get("assigned"))}},
        "upload": str(upload.public_id),
        "match_id": match.id,
    }


def _ingest_upload_demo(
    job_db, db, job, upload, match, path: Path, number: int, scratch, mine_known, theirs_known
) -> dict | None:
    label = path.name

    def waiting(holder: str) -> None:
        jobs.activity(
            job_db, job, key="parse:waiting", stage=STAGE.PARSING,
            text=mn.HEAVY_WAIT.format(holder=holder or "өөр ажил"),
        )  # fmt: skip

    def cancelled() -> bool:
        jobs.check_cancelled(job_db, job)
        return False

    with heavy.permit(f"job:{job.public_id}", on_wait=waiting, cancelled=cancelled):
        jobs.activity(
            job_db, job, key="parse:awpy", stage=STAGE.PARSING,
            text=f"{label} · {mn.ingest_step('awpy')} ({mn.mb(path.stat().st_size)})",
        )  # fmt: skip
        result = tickdata.parse_parts([path], scratch / "tickdata", parts=False)
        parsed, bundle = result.parsed, result.bundle
        for warning in result.warnings:
            jobs.log(job_db, job, f"   ! {label}: {warning}", level=LEVEL.WARNING)
        demo = store._demo(db, match, map=parsed.map_name)
        if demo.is_processed:
            same = mn.UPLOAD_SAME_MAP.format(name=label, map=mn.game_map(parsed.map_name))
            jobs.log(job_db, job, same, level=LEVEL.WARNING, stage=STAGE.PARSING)
            return None
        demo.map_number = number
        demo.url = f"upload:{upload.public_id}/{label}"[:200]
        demo.filename = label[:255]
        demo.size_bytes = path.stat().st_size
        demo.is_downloaded = True
        demo.downloaded_at = utcnow()
        groups = uploads.side_groups(parsed)
        mine = uploads.pick_mine(groups, mine_known, theirs_known)
        given = (
            uploads.sides(groups, mine, upload.my_team_id, match.team2_id)
            if mine is not None
            else None
        )
        match_map = analysis_store.ingest_map(
            db, demo, parsed, bundle=bundle, sides=given,
            on_step=_ingest_reporter(job_db, job, label),
        )  # fmt: skip
        store._mark_processed(demo)
        db.commit()
    names = uploads.names_by_steamid(parsed)
    assigned = mine is not None or _has_my_team(match_map, upload.my_team_id)
    jobs.log(
        job_db, job,
        f"   ✓ {mn.game_map(parsed.map_name)} {match_map.scoreline} · {parsed.n_rounds} раунд",
        level=LEVEL.SUCCESS, stage=STAGE.PARSING,
    )  # fmt: skip
    return {
        "map_number": number,
        "map": parsed.map_name,
        "demo_id": demo.id,
        "groups": [[{"steamid": str(s), "name": names.get(s, "")} for s in g] for g in groups],
        "mine": mine,
        "assigned": assigned,
        "match_map_id": match_map.id,
    }


def _has_my_team(match_map: MatchMap, my_team_id: int) -> bool:
    return my_team_id in (match_map.team1_id, match_map.team2_id) and None not in (
        match_map.team1_id,
        match_map.team2_id,
    )


def _reassign_upload_map(job_db, db, job, upload, match, entry: dict) -> dict:
    demo = db.get(Demo, entry["demo_id"])
    stored = db.scalar(select(TickDataset).where(TickDataset.match_map_id == entry["match_map_id"]))
    if demo is None or stored is None:
        jobs.log(job_db, job, mn.UPLOAD_GONE.format(map=mn.game_map(entry["map"])),
                 level=LEVEL.WARNING, stage=STAGE.PARSING)  # fmt: skip
        return {**entry, "mine": None}
    groups = [[int(p["steamid"]) for p in g] for g in entry["groups"]]
    given = uploads.sides(groups, entry["mine"], upload.my_team_id, match.team2_id)
    with heavy.permit(f"job:{job.public_id}"):
        bundle, version = stored.bundle, stored.awpy_version
        parsed = tickdata.parsed_map(bundle, demo.filename, version)
        match_map = analysis_store.ingest_map(db, demo, parsed, bundle=bundle, sides=given)
        db.commit()
    jobs.log(
        job_db, job, f"   ✓ {mn.game_map(entry['map'])}: {mn.UPLOAD_SIDES_SET}",
        level=LEVEL.SUCCESS, stage=STAGE.PARSING,
    )  # fmt: skip
    return {**entry, "assigned": True, "match_map_id": match_map.id}


def _score_upload_match(db, match: Match) -> None:
    """The Match's score in Maps, from my team's side (team1)."""
    maps = db.scalars(select(MatchMap).where(MatchMap.match_id == match.id)).all()
    won = sum(1 for m in maps if m.winner_id and m.winner_id == match.team1_id)
    lost = sum(1 for m in maps if m.winner_id and m.winner_id == match.team2_id)
    match.team1_score, match.team2_score = won, lost
    match.score = f"{won} - {lost}" if won or lost else ""
    db.commit()


@celery_app.task(name="cs_analyze.refresh_reviews")
def refresh_reviews() -> dict:
    """Rebuild every stale or missing Review from its Tick Data, one Match Map at
    a time (docs/adr/0008). Not an Analysis Job: nothing waits behind it, and the
    Game Plan counts what is still waiting."""
    done = failed = 0
    try:
        with SessionLocal() as db:
            with dbctx.using(db):
                ids = review_pool.stale_ids()
            for match_map_id in ids:
                match_map = db.get(MatchMap, match_map_id)
                if match_map is None:
                    continue
                if review.rebuild(db, match_map) is None:
                    failed += 1
                    db.rollback()
                    continue
                db.commit()
                done += 1
    finally:
        review_pool.release_refresh(review_pool.REFRESH_RETRY_SECONDS if failed else 0)
    logger.info("Review refresh: %s rebuilt, %s failed", done, failed)
    return {"rebuilt": done, "failed": failed}


def run_pipeline(job_db: Session, db: Session, job: AnalysisJob) -> dict:
    jobs.check_cancelled(job_db, job)
    jobs.set_stage(
        job_db,
        job,
        STAGE.RESOLVING,
        _at(STAGE.RESOLVING),
        f"{job.my_team_name} багийг {job.opponent_name}-ийн эсрэг бэлдэж байна. "
        f"Хүсэлт: манай {job.n_my_matches}, тэдний {job.n_opponent_matches}, "
        f"хоорондын {job.n_h2h_matches} тоглолт"
        + (" · demo татна." if job.download else " · зөвхөн диск дээрх demo."),
    )

    my_team = _resolve(job_db, db, job, job.my_team_name, "манай баг")
    opponent = _resolve(job_db, db, job, job.opponent_name, "өрсөлдөгч")
    job.my_team_id, job.opponent_id = my_team.id, opponent.id
    job_db.commit()
    jobs.log(
        job_db,
        job,
        f"Багууд тодорхой болов: {my_team.name} vs {opponent.name}.",
        level=LEVEL.SUCCESS,
        stage=STAGE.RESOLVING,
    )
    jobs.finish_stage(
        job_db, job, STAGE.RESOLVING, f"{my_team.name} vs {opponent.name}", {"teams": 2}
    )

    jobs.check_cancelled(job_db, job)
    outcome: dict = {}
    scratch = _scratch(job)
    try:
        if job.download:
            outcome = _fetch(job_db, db, job, my_team, opponent, scratch)
        else:
            jobs.set_stage(job_db, job, STAGE.FETCHING, MATCHES[0])
            jobs.log(
                job_db,
                job,
                "Татах хэсгийг алгаслаа — өгөгдлийн санд байгаа tick датагаар шинжилнэ.",
                level=LEVEL.WARNING,
                stage=STAGE.FETCHING,
            )
            jobs.finish_stage(job_db, job, STAGE.FETCHING, "татахгүй гэж хүссэн")
        if not any(e.get("stage") == STAGE.UNPACKING for e in job.stage_log or []):
            # Nothing was downloaded, so nothing was unpacked: say so rather than
            # leave a finished run with a step that looks like it never got to run.
            jobs.set_stage(job_db, job, STAGE.UNPACKING, MATCHES[1])
            jobs.finish_stage(job_db, job, STAGE.UNPACKING, "задлах архив байхгүй")
        jobs.check_cancelled(job_db, job)
        reparsed = _reparse(job_db, db, job, _own_match_ids(db, my_team, opponent))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    jobs.check_cancelled(job_db, job)

    linked = _link_matches(job_db, db, job, my_team, opponent)
    windows = outcome.get("windows")
    result = {
        "windows": (
            {key: _summaries(db, ids) for key, ids in windows.items()} if windows else None
        ),
        "parsed_matches": _summaries(db, linked),
        "scanned": outcome.get("scanned"),
        "h2h_found": outcome.get("h2h_found"),
        "totals": {
            "fetching": outcome.get("totals") or {},
            "unpacking": outcome.get("unpacking") or {},
            "parsing": outcome.get("parsing") or {},
            "reparsing": reparsed,
        },
    }
    jobs.finish(job_db, job, result)
    return {"job": str(job.public_id), "status": job.status}


# -- resolving ---------------------------------------------------------------
def _local_team(db: Session, name: str) -> tuple[Team | None, list[Team]]:
    """What the stored teams say a typed name means: ``(team, candidates)``.

    A club name is not unique among stored teams (a search for "HEROIC" stores
    the live club and two dead rosters), so sample size breaks the tie: the club
    a name means is the one this database has actually seen play. When nothing
    separates the candidates, ``team`` is None and ``candidates`` carries them
    ranked, so the caller can ask HLTV, whose ordering is the authority.
    """
    lowered = func.lower(Team.name)
    candidates = list(db.scalars(select(Team).where(lowered == name.lower()).order_by(Team.id)))
    if not candidates:
        candidates = list(
            db.scalars(select(Team).where(lowered.contains(name.lower())).order_by(Team.id))
        )
    if len(candidates) <= 1:
        return (candidates[0] if candidates else None), candidates

    counts = {
        team.id: db.scalar(
            select(func.count())
            .select_from(Match)
            .where(or_(Match.team1_id == team.id, Match.team2_id == team.id))
        )
        for team in candidates
    }
    # Rows created by a search are inserted in HLTV's relevance order, so id
    # order preserves it and breaks a remaining tie.
    ranked = sorted(candidates, key=lambda t: (-counts[t.id], t.id))
    decided = counts[ranked[0].id] > counts[ranked[1].id]
    return (ranked[0] if decided else None), ranked


def _resolve(job_db: Session, db: Session, job: AnalysisJob, name: str, role: str) -> Team:
    """Find the team locally; fall back to an HLTV search only if needed."""
    jobs.check_cancelled(job_db, job)
    name = (name or "").strip()
    jobs.activity(
        job_db, job, key="resolve", stage=STAGE.RESOLVING, text=f"{role}: “{name}”-ыг хайж байна"
    )
    team, candidates = _local_team(db, name)
    if team is None and len(candidates) > 1 and not job.download:
        # Only HLTV could break the tie, and downloading is off. Use the first and
        # name the others, which beats failing on a question the reader can answer
        # by typing the fuller name.
        team = candidates[0]
        others = ", ".join(f"{t.name} (id={t.hltv_id or '?'})" for t in candidates[1:5])
        jobs.log(
            job_db,
            job,
            f"{role}: “{name}”-д {len(candidates)} баг тохирч байна; "
            f"{team.name}-ыг сонголоо. Бусад: {others}.",
            level=LEVEL.WARNING,
            stage=STAGE.RESOLVING,
        )
    if team and team.hltv_id:
        jobs.log(
            job_db,
            job,
            f"{role}: “{name}” → {team.name} (HLTV id={team.hltv_id}) · {_parsed_maps(db, team)}",
            stage=STAGE.RESOLVING,
        )
        return team
    if team and not job.download:
        jobs.log(
            job_db,
            job,
            f"{role}: “{name}” → {team.name}, гэхдээ HLTV id байхгүй — "
            "татах хэсэг хаалттай тул түүний тоглолтуудыг уншиж чадахгүй.",
            level=LEVEL.WARNING,
            stage=STAGE.RESOLVING,
        )
        return team
    if team:
        # Known only by the name printed on someone else's results row. Without an
        # id there is no results page to read, so look it up now and adopt it.
        jobs.log(
            job_db,
            job,
            f"{role}: “{team.name}”-д HLTV id байхгүй — HLTV-ээс хайж байна.",
            stage=STAGE.RESOLVING,
        )

    if not job.download:
        raise ValueError(
            f"“{name}”-д тохирох баг өгөгдлийн санд байхгүй, татах хэсэг нь хаалттай. "
            "Татах эрхтэйгээр дахин ажиллуулах, эсвэл тэр багийг эхлээд татах хэрэгтэй."
        )
    if team is None:
        if candidates:
            jobs.log(
                job_db,
                job,
                f"{role}: “{name}”-д {len(candidates)} баг тохирч байна — "
                "аль нь идэвхтэй болохыг HLTV-ээс тодруулж байна.",
                stage=STAGE.RESOLVING,
            )
        else:
            jobs.log(
                job_db,
                job,
                f"{role}: “{name}” локалд байхгүй — HLTV-ээс хайж байна.",
                stage=STAGE.RESOLVING,
            )

    from app.services.browser import HltvBrowser
    from app.services.client import HltvClient

    with HltvBrowser() as browser:
        jobs.activity(
            job_db,
            job,
            key="resolve",
            stage=STAGE.RESOLVING,
            text=f"HLTV-ийн хайлт: “{team.name if team else name}”",
        )
        scraped = HltvClient(browser).resolve_team(team.name if team else name)
        if scraped is None:
            if team:
                jobs.log(
                    job_db,
                    job,
                    f"HLTV дээр “{team.name}”-тай тохирох баг олдсонгүй; "
                    "локал бичлэгээр явна, тул түүний тоглолтуудыг татаж чадахгүй.",
                    level=LEVEL.WARNING,
                    stage=STAGE.RESOLVING,
                )
                return team
            raise ValueError(f"HLTV дээр “{name}”-тай тохирох баг байхгүй.")
        team = store.get_or_create_team(db, scraped)
    jobs.log(
        job_db,
        job,
        f"{role}: {team.name}-ыг HLTV дээр олов (id={team.hltv_id}) · {_parsed_maps(db, team)}",
        level=LEVEL.SUCCESS,
        stage=STAGE.RESOLVING,
    )
    return team


def _parsed_maps(db: Session, team: Team) -> str:
    """How much of this team is already in the database.

    Said out loud at the start because it decides whether the rest of the run is
    minutes or seconds.
    """
    n = db.scalar(
        select(func.count(distinct(MatchMap.id)))
        .join(MapRoster, MapRoster.match_map_id == MatchMap.id)
        .where(MapRoster.team_id == team.id, MatchMap.parsed_at.is_not(None))
    )
    return f"өгөгдлийн санд {n} мап бэлэн" if n else "өгөгдлийн санд мап байхгүй"


# -- fetching ----------------------------------------------------------------
def _is_between(match, team_a: Team, team_b: Team) -> bool:
    """Did these two teams play each other in this match?

    Compared on normalised names, because HLTV is not consistent about the
    decorations -- "The MongolZ" on one page is "MongolZ" on another.
    """
    norm = analysis_store.normalise_team_name
    names = {norm(match.team1 or ""), norm(match.team2 or "")}
    names.discard("")
    return norm(team_a.name) in names and norm(team_b.name) in names


# How far back to look for a head-to-head. One results page holds far more than
# this, so a deeper scan is free.
H2H_SCAN_DEPTH = 40


def _plan_matches(job_db: Session, job: AnalysisJob, client, my_team: Team, opponent: Team) -> dict:
    """Split each team's recent results into head-to-head and everything else.

    HLTV's results page is one list per team, so both categories come from the
    same read. A wider window than requested is scanned, because the matches
    that are *not* against the opponent may sit behind several that are.
    """
    plan: dict = {"h2h": [], "mine": [], "theirs": []}
    window = max(job.n_my_matches, job.n_opponent_matches) + 8
    if job.n_h2h_matches:
        window = max(window, H2H_SCAN_DEPTH)
    plan["window"] = window
    plan["scanned"] = 0

    for team, own_key, own_wanted in (
        (my_team, "mine", job.n_my_matches),
        (opponent, "theirs", job.n_opponent_matches),
    ):
        if not own_wanted and not job.n_h2h_matches:
            continue
        jobs.check_cancelled(job_db, job)
        results = client.latest_matches(_as_scraped(team), window)
        plan["scanned"] = max(plan["scanned"], len(results))
        against, others = [], []
        for match in results:
            (against if _is_between(match, my_team, opponent) else others).append(match)

        # Head-to-head is read off whichever team's page we are on; the first pass
        # fills it and the second only tops it up.
        seen = {m.id for m in plan["h2h"]}
        for match in against:
            if len(plan["h2h"]) >= job.n_h2h_matches:
                break
            if match.id not in seen:
                plan["h2h"].append(match)
                seen.add(match.id)
        plan[own_key] = others[:own_wanted]

        other_team = (opponent if team is my_team else my_team).name
        jobs.log(
            job_db,
            job,
            f"{team.name}: HLTV-ийн {len(results)} тоглолтыг харлаа — "
            f"{len(against)} нь {other_team}-ийн эсрэг, {len(others)} нь бусдын эсрэг; "
            f"{len(plan[own_key])} өөрийн тоглолт"
            + (
                f" ба хоорондоос дээд тал нь {job.n_h2h_matches} авна."
                if job.n_h2h_matches
                else " авна."
            ),
            stage=STAGE.FETCHING,
        )
    return plan


LEFTOVER_HOURS = 6


def _is_job_folder(name: str) -> bool:
    try:
        uuid.UUID(name)
    except ValueError:
        return False
    return True


def _scratch(job: AnalysisJob) -> Path:
    """This run's own scratch folder, and the leftovers of any run that died:
    a job's folder whose job is no longer in flight (a killed worker, a restarted
    container), or anything else left for hours.
    """
    root = get_settings().hltv_data_dir / "tmp"
    if root.exists():
        # Uploads run beside a Scout (OPS-6): a folder of a job still in flight, or
        # one touched in the last hours (a CLI's clone), is someone else's.
        live = {
            str(j.public_id) for j in object_session(job).scalars(jobs._in_flight(all_kinds=True))
        }
        cutoff = time.time() - LEFTOVER_HOURS * 3600
        for leftover in root.iterdir():
            if leftover.name == str(job.public_id) or leftover.name in live:
                continue
            if leftover.stat().st_mtime < cutoff or _is_job_folder(leftover.name):
                shutil.rmtree(leftover, ignore_errors=True)
    folder = root / str(job.public_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _fetch(
    job_db: Session, db: Session, job: AnalysisJob, my_team: Team, opponent: Team, scratch: Path
) -> dict:
    """The three windows the job asked for, one match at a time.

    For each match: download it (unless it is already parsed), unpack it, parse
    its maps, delete its files. Returns what the scan learned (and which matches
    each window holds), so the result can explain an empty head-to-head.
    """
    from app.services.browser import HltvBlocked, HltvBrowser
    from app.services.client import HltvClient

    jobs.set_stage(
        job_db,
        job,
        STAGE.FETCHING,
        MATCHES[0],
        f"HLTV-ээс тоглолтуудыг харж байна: {my_team.name}-ийн {job.n_my_matches}, "
        f"{opponent.name}-ийн {job.n_opponent_matches}, хоорондын {job.n_h2h_matches}.",
    )
    totals = {
        "fetching": {"downloaded": 0, "skipped": 0, "missing": 0, "failed": 0},
        "unpacking": {"archives": 0, "maps": 0, "failed": 0},
        "parsing": {"parsed": 0, "rounds": 0, "failed": 0},
    }
    outcome: dict = {"h2h_found": 0, "scanned": 0, "windows": None, "totals": totals["fetching"],
                     "unpacking": totals["unpacking"], "parsing": totals["parsing"]}  # fmt: skip

    try:
        with HltvBrowser() as browser:
            client = HltvClient(browser)
            jobs.activity(
                job_db,
                job,
                key="plan",
                stage=STAGE.FETCHING,
                text="HLTV-ийн тоглолтын хуудсуудыг уншиж байна",
            )
            plan = _plan_matches(job_db, job, client, my_team, opponent)
            outcome["h2h_found"] = len(plan["h2h"])
            outcome["scanned"] = plan.get("scanned", 0)
            outcome["windows"] = {
                key: [m.id for m in plan[key]] for key in ("h2h", "mine", "theirs")
            }

            windows = (("h2h", plan["h2h"]), ("mine", plan["mine"]), ("theirs", plan["theirs"]))
            steps = _Steps(sum(len(matches) for _key, matches in windows))
            for key, matches in windows:
                label = mn.window(key, my_team.name, opponent.name)
                if not matches:
                    jobs.log(
                        job_db, job, f"── {label}: хүсээгүй эсвэл олдсонгүй.", stage=STAGE.FETCHING
                    )
                    continue
                jobs.log(
                    job_db,
                    job,
                    f"── {label}: {len(matches)} матч",
                    level=LEVEL.SUCCESS,
                    stage=STAGE.FETCHING,
                )
                for match in matches:
                    jobs.check_cancelled(job_db, job)
                    step = steps.next()
                    _process_match(
                        job_db, db, job, client, browser, match, scratch, totals, step,
                        (steps.done, steps.total),
                    )  # fmt: skip

        jobs.log(
            job_db,
            job,
            "Татах дүн — " + mn.counts(totals["fetching"]),
            level=LEVEL.ERROR if totals["fetching"]["failed"] else LEVEL.SUCCESS,
            stage=STAGE.FETCHING,
        )
        if job.n_h2h_matches and not outcome["h2h_found"]:
            jobs.log(
                job_db,
                job,
                f"HLTV-ийн сүүлийн {outcome['scanned']} тоглолтод {my_team.name} ба "
                f"{opponent.name} хоорондоо тоглосон нь байхгүй — сүүлд таарсангүй, "
                "тул хоорондын хэсгүүд хоосон байна.",
                level=LEVEL.WARNING,
                stage=STAGE.FETCHING,
            )
    except HltvBlocked as exc:
        # Cloudflare is not a reason to lose whatever is already parsed.
        jobs.log(
            job_db,
            job,
            f"HLTV-д хүрсэнгүй ({exc}). Өгөгдлийн санд байгаагаар үргэлжлүүлнэ.",
            level=LEVEL.WARNING,
            stage=STAGE.FETCHING,
        )
        jobs.finish_stage(job_db, job, STAGE.FETCHING, "", totals["fetching"])
    return outcome


def _process_match(
    job_db, db, job, client, browser, match, scratch: Path, totals: dict, step, cycle
) -> None:
    """One match end to end, and its files gone afterwards whatever happened."""
    n, of = cycle
    jobs.set_stage(job_db, job, STAGE.FETCHING, _at_match(STAGE.FETCHING, n, of), cycle=cycle)
    archive = _fetch_one(job_db, db, job, client, browser, match, scratch, totals["fetching"], step)
    jobs.finish_stage(job_db, job, STAGE.FETCHING, "", totals["fetching"])
    if archive is None:
        return
    row = store.get_or_create_match(db, match)
    maps_dir = scratch / "maps" / f"{match.id}-{match.slug}"
    try:
        jobs.check_cancelled(job_db, job)
        jobs.set_stage(job_db, job, STAGE.UNPACKING, _at_match(STAGE.UNPACKING, n, of), cycle=cycle)
        _unpack_one(job_db, db, job, row.archive_demo, archive, maps_dir, totals["unpacking"], step)
        jobs.finish_stage(job_db, job, STAGE.UNPACKING, "", totals["unpacking"])
        # The archive is not needed once its demos are out.
        archive.unlink(missing_ok=True)

        jobs.check_cancelled(job_db, job)
        jobs.set_stage(job_db, job, STAGE.PARSING, _at_match(STAGE.PARSING, n, of), cycle=cycle)
        for demo in analysis_store.pending_map_demos(db, match_ids=[match.id]):
            jobs.check_cancelled(job_db, job)
            _parse_one(job_db, db, job, demo, scratch, totals["parsing"], step)
        _warm_pool(job_db, job)
        jobs.finish_stage(job_db, job, STAGE.PARSING, "", totals["parsing"])
    except jobs.JobCancelled:
        raise
    except Exception as exc:  # one Match must not fail the Scout (docs/adr/0009)
        db.rollback()
        logger.exception("match %s failed", match.id)
        jobs.log(
            job_db,
            job,
            f"   ✗ энэ матчийг алгаслаа — {exc}",
            level=LEVEL.ERROR,
            stage=STAGE.PARSING,
            step=step,
        )
        totals["parsing"]["failed"] += 1
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(maps_dir, ignore_errors=True)
        db.rollback()
        store.forget_files(db, row)


def _redownload_reason(db: Session, row: Match) -> str:
    """Why a match whose archive was unpacked must be fetched again, or ``""``.

    A map that never parsed, with no Tick Data to parse it from, can only be
    retried from a fresh download: its Demo was deleted with the match's files.
    So can a stale map whose Tick Data predates the economy or the Loadout
    (docs/adr/0003, 0005), and a Match Map whose Demo parts were never merged:
    its Tick Data holds one part at most (docs/adr/0009).
    """
    pending = analysis_store.pending_map_demos(db, match_ids=[row.hltv_id])
    stuck = [d for d in pending if d.analysis is None or d.analysis.tick_dataset is None]
    unmerged = [d for d in pending if d not in stuck and _unmerged(d)]
    old = [d for d in pending if d not in stuck and not _reparseable(d) and d not in unmerged]
    reasons = []
    if stuck:
        names = ", ".join(mn.game_map(d.map) for d in stuck)
        reasons.append(
            f"{len(stuck)} мап ({names}) боловсруулагдаагүй бөгөөд tick дата хадгалагдаагүй"
        )
    if unmerged:
        names = ", ".join(mn.game_map(d.map) for d in unmerged)
        reasons.append(f"{len(unmerged)} мапын ({names}) demo хэсгүүд нэгтгэгдээгүй")
    if old:
        names = ", ".join(mn.game_map(d.map) for d in old)
        reasons.append(
            f"{len(old)} мапын ({names}) tick датанд эдийн засаг эсвэл зэвсэглэл байхгүй"
        )
    return "; ".join(reasons)


def _reparseable(demo: Demo) -> bool:
    return (
        demo.analysis is not None
        and not _unmerged(demo)
        and tickdata.reparseable(demo.analysis.tick_dataset)
    )


def _unmerged(demo: Demo) -> bool:
    """Part 1 of Demo parts not yet parsed together: only their Demos can."""
    return bool(demo.part) and not demo.is_processed


def _fetch_one(job_db, db, job, client, browser, match, scratch: Path, totals: dict, step):
    """One match: skip it if it is already parsed, otherwise download it.

    Returns the archive on disk, or None when there is nothing to unpack. Two
    lines per match on purpose: the first names the match, the second says what
    was decided about it, so the decision can be coloured while the identity
    stays plain.
    """
    from playwright.sync_api import Error as PlaywrightError

    from app.services.browser import HltvBlocked

    row = store.get_or_create_match(db, match)
    demo = row.archive_demo
    target = scratch / "demos" / f"{match.id}-{match.slug}.rar"
    jobs.log(
        job_db,
        job,
        mn.match_line(_match_facts(match)),
        stage=STAGE.FETCHING,
        step=step,
        payload={"match": match.id},
    )

    # Already downloaded and unpacked: its maps are parsed, or parse again from
    # their stored Tick Data. The files themselves were deleted long ago.
    if demo is not None and demo.is_processed:
        reason = _redownload_reason(db, row)
        if not reason:
            maps = [d.map for d in row.map_demos if d.is_processed]
            detail = (
                f" ({len(maps)} мап: {', '.join(mn.game_map(m) for m in maps)})" if maps else ""
            )
            jobs.log(
                job_db,
                job,
                f"   → аль хэдийн боловсруулагдсан{detail} — алгаслаа.",
                stage=STAGE.FETCHING,
                step=step,
            )
            totals["skipped"] += 1
            return None
        jobs.log(
            job_db,
            job,
            f"   → {reason} — дахин татна.",
            level=LEVEL.WARNING,
            stage=STAGE.FETCHING,
            step=step,
        )

    jobs.activity(
        job_db,
        job,
        key="demo-link",
        stage=STAGE.FETCHING,
        text=f"demo-ийн холбоосыг шалгаж байна · match {match.id}",
    )
    try:
        link = client.demo_link(match)
    except (HltvBlocked, PlaywrightError) as exc:
        if not browser.is_connected():
            # The Chromium process itself is gone; every match still queued would
            # fail the same way. _fetch() turns this into "continue with the database".
            raise HltvBlocked(str(exc)) from exc
        # A crashed tab costs this match only; the next one gets a new tab.
        browser.recover_page()
        jobs.log(
            job_db,
            job,
            f"   ✗ demo-ийн холбоосыг уншиж чадсангүй — {exc}",
            level=LEVEL.ERROR,
            stage=STAGE.FETCHING,
            step=step,
        )
        totals["failed"] += 1
        return None
    store.record_demo_lookup(db, row, link)
    if not link:
        jobs.log(
            job_db,
            job,
            "   → HLTV энэ матчид demo тавиагүй (матчийн хуудсыг шалгасан).",
            level=LEVEL.WARNING,
            stage=STAGE.FETCHING,
            step=step,
        )
        totals["missing"] += 1
        return None

    jobs.log(job_db, job, f"   ↓ татаж байна → {target.name}", stage=STAGE.FETCHING, step=step)
    target.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        settings = get_settings()
        browser.download(
            link,
            target,
            timeout_ms=settings.hltv_download_start_timeout_ms,
            on_progress=_download_reporter(job_db, job, step, match, target),
            stall_seconds=settings.hltv_download_stall_seconds,
        )
    except HltvBlocked as exc:
        target.unlink(missing_ok=True)
        store.record_download_failure(db, row, link, str(exc))
        jobs.log(
            job_db,
            job,
            f"   ✗ татаж чадсангүй — {exc}",
            level=LEVEL.ERROR,
            stage=STAGE.FETCHING,
            step=step,
        )
        totals["failed"] += 1
        if not browser.is_connected():
            raise  # same rationale as the demo_link branch above
        return None
    size = target.stat().st_size
    took = time.monotonic() - started
    store.record_download(db, row, target, url=link, size_bytes=size)
    jobs.log(
        job_db,
        job,
        f"   ✓ {mn.mb(size)} · {mn.duration(took)} · {mn.speed(size / took if took else 0)}",
        level=LEVEL.SUCCESS,
        stage=STAGE.FETCHING,
        step=step,
    )
    totals["downloaded"] += 1
    return target


# A 500 MB archive is most of a run's wall clock. The activity line carries every
# update (it overwrites itself); the story gets one line per quarter.
_LOG_EVERY_PCT = 25
# Speed is what the last few seconds did, like a browser's download bar: a stall
# shows at once instead of being averaged away. The ✓ line keeps the average.
_SPEED_WINDOW_SEC = 5.0


def _download_reporter(job_db: Session, job: AnalysisJob, step, match, target: Path):
    logged = {"pct": 0.0}
    seen: deque[tuple[float, int]] = deque()  # (elapsed, received)

    def report(received, total, elapsed) -> None:
        head = f"↓ {target.name}"
        if received is None:
            # No byte counts to be had; the clock is the only honest thing left.
            jobs.activity(
                job_db,
                job,
                key="download",
                stage=STAGE.FETCHING,
                text=f"{head} · татаж байна · {mn.duration(elapsed)}",
                data={"match": match.id},
            )
            return

        seen.append((elapsed, received))
        # Keep the newest sample that is at least a window old as the baseline.
        while len(seen) > 1 and elapsed - seen[1][0] >= _SPEED_WINDOW_SEC:
            seen.popleft()
        since, then = seen[0]
        if elapsed > since:
            rate = (received - then) / (elapsed - since)
        else:
            rate = received / elapsed if elapsed > 0 else 0
        pct = 100.0 * received / total if total else None
        bits = [head, f"{mn.mb(received)} / {mn.mb(total)}" if total else mn.mb(received)]
        if pct is not None:
            bits.append(f"{pct:.0f}%")
        bits.append(mn.speed(rate))
        if total and rate:
            bits.append(f"~{mn.duration((total - received) / rate)} үлдлээ")
        jobs.activity(
            job_db,
            job,
            key="download",
            stage=STAGE.FETCHING,
            text=" · ".join(bits),
            pct=pct,
            done=received,
            total=total,
            data={"match": match.id},
        )

        if pct is not None and pct - logged["pct"] >= _LOG_EVERY_PCT:
            logged["pct"] = _LOG_EVERY_PCT * int(pct // _LOG_EVERY_PCT)
            jobs.log(
                job_db,
                job,
                f"     {pct:.0f}% · {mn.mb(received)} / {mn.mb(total)} · {mn.speed(rate)}",
                level=LEVEL.DEBUG,
                stage=STAGE.FETCHING,
                step=step,
            )

    return report


def _match_facts(match) -> dict:
    """A scraped match as the plain keys :func:`mn.match_line` words."""
    return {
        "id": match.id,
        "team1": match.team1,
        "team2": match.team2,
        "score": match.score,
        "tournament": match.event,
        "played_at": match.played_at.date().isoformat() if match.played_at else None,
    }


def _row_facts(row: Match) -> dict:
    """The same, for a stored match rather than a scrape."""
    return {
        "id": row.hltv_id,
        "team1": row.team1.name if row.team1 else "?",
        "team2": row.team2.name if row.team2 else "?",
        "score": row.score,
        "tournament": row.tournament.name if row.tournament else "",
        "played_at": row.played_at.date().isoformat() if row.played_at else None,
    }


# -- unpacking ---------------------------------------------------------------
def _unpack_one(job_db, db, job, demo: Demo, path: Path, dest: Path, totals: dict, step) -> None:
    """Unpack one match's archive into ``dest`` and record its map demos."""
    from app.services import archive as archive_service

    try:
        jobs.activity(
            job_db,
            job,
            key="list",
            stage=STAGE.UNPACKING,
            text=f"{path.name} ({mn.mb(demo.size_bytes)}) дотрыг харж байна",
        )
        entries = archive_service.list_demos(path)
        jobs.log(
            job_db,
            job,
            f"   → {path.name} ({mn.mb(demo.size_bytes)}) · {len(entries)} мап: "
            + mn.demo_maps([(e.map, e.part) for e in entries]),
            stage=STAGE.UNPACKING,
            step=step,
        )
        started = time.monotonic()
        written = archive_service.extract(
            path, dest, entries, on_progress=_unpack_reporter(job_db, job, path)
        )
        store.record_extraction(db, demo, zip(entries, written, strict=True))
        sizes = ", ".join(
            f"{mn.game_map(e.map)}{f' ({e.part})' if e.part else ''} "
            f"{mn.mb(p.stat().st_size if p.exists() else 0)}"
            for e, p in zip(entries, written, strict=True)
        )
        jobs.log(
            job_db,
            job,
            f"   ✓ {len(written)} мап задлав ({mn.duration(time.monotonic() - started)}) · {sizes}",
            level=LEVEL.SUCCESS,
            stage=STAGE.UNPACKING,
            step=step,
        )
        totals["archives"] += 1
        totals["maps"] += len(written)
    except jobs.JobCancelled:
        raise
    except Exception as exc:  # ArchiveError, or a row that won't store: this Match only
        db.rollback()
        store.record_processing_failure(db, demo, str(exc))
        jobs.log(
            job_db,
            job,
            f"   ✗ задалж чадсангүй — {exc}",
            level=LEVEL.ERROR,
            stage=STAGE.UNPACKING,
            step=step,
        )
        totals["failed"] += 1


def _unpack_reporter(job_db: Session, job: AnalysisJob, archive: Path):
    """bsdtar prints nothing per member, so the destination is what we watch."""

    def report(done, total, written) -> None:
        jobs.activity(
            job_db,
            job,
            key="unpack",
            stage=STAGE.UNPACKING,
            text=f"{archive.name} · {done}/{total} мап бичигдлээ · {mn.mb(written)}",
            pct=(100.0 * done / total) if total else None,
            done=done,
            total=total,
        )

    return report


# -- parsing -----------------------------------------------------------------
def _parse_one(job_db, db, job, demo: Demo, scratch: Path | None, totals: dict, step) -> None:
    """Parse and ingest one Match Map while holding the host's heavy permit (OPS-6)."""

    def waiting(holder: str) -> None:
        jobs.activity(
            job_db, job, key="parse:waiting", stage=STAGE.PARSING,
            text=mn.HEAVY_WAIT.format(holder=holder or "өөр ажил"),
        )  # fmt: skip

    def cancelled() -> bool:
        jobs.check_cancelled(job_db, job)  # raises JobCancelled
        return False

    with heavy.permit(f"job:{job.public_id}", on_wait=waiting, cancelled=cancelled):
        _parse_one_now(job_db, db, job, demo, scratch, totals, step)


def _parse_one_now(job_db, db, job, demo: Demo, scratch: Path | None, totals: dict, step) -> None:
    """Parse one map and store it with its Tick Data; delete its ``.dem`` after.

    The Demo is the source when it is on disk (just unpacked); otherwise the
    map's stored Tick Data is, which is how a map on an old schema is parsed
    again without downloading anything. A Match Map recorded as Demo parts is
    parsed from all of them, merged (docs/adr/0009); ``demo`` is part 1.
    """
    parts = analysis_store.demo_parts(db, demo)
    paths = [Path(d.path) for d in parts if d.path]
    on_disk = [p for p in paths if p.exists()]
    map_label = mn.game_map(demo.map) or "?"
    jobs.log(
        job_db,
        job,
        f"{map_label} · " + mn.match_line(_row_facts(demo.match)),
        stage=STAGE.PARSING,
        step=step,
        payload={"match": demo.match.hltv_id},
    )
    jobs.log(job_db, job, f"   → {_why_parse(demo)}", stage=STAGE.PARSING, step=step)
    stored = None
    if not on_disk:
        stored = db.scalar(
            select(TickDataset)
            .join(MatchMap, MatchMap.id == TickDataset.match_map_id)
            .where(MatchMap.demo_id == demo.id)
        )
        if stored is None:
            store.record_processing_failure(db, demo, "no demo on disk and no stored tick data")
            jobs.log(
                job_db,
                job,
                "   ✗ .dem файл ч, хадгалсан tick дата ч байхгүй — дахин татахад боловсруулагдана.",
                level=LEVEL.WARNING,
                stage=STAGE.PARSING,
                step=step,
            )
            totals["failed"] += 1
            return
    try:
        started = time.monotonic()
        failed: list[tuple[str, str]] = []
        if stored is None:
            size = sum(p.stat().st_size for p in on_disk)
            if demo.part:
                jobs.log(
                    job_db,
                    job,
                    f"   → {len(parts)} хэсэгт бичигдсэн (сервер дундаа дахин эхэлсэн) — "
                    f"{len(on_disk)} хэсгийг нэгтгэж нэг мап болгоно.",
                    stage=STAGE.PARSING,
                    step=step,
                )
            jobs.activity(
                job_db,
                job,
                key="parse:awpy",
                stage=STAGE.PARSING,
                text=f"{map_label} · {mn.ingest_step('awpy')} ({mn.mb(size)})",
            )
            result = tickdata.parse_parts(
                on_disk,
                (scratch or _scratch(job)) / "tickdata",
                parts=bool(demo.part),
                on_step=lambda key: jobs.activity(
                    job_db, job, key=f"parse:{key}", stage=STAGE.PARSING,
                    text=f"{map_label} · {mn.ingest_step(key)}",
                ),
            )  # fmt: skip
            parsed, bundle, failed = result.parsed, result.bundle, result.failed
            for name, error in failed:
                jobs.log(
                    job_db,
                    job,
                    f"   ! {name}: уншиж чадсангүй, түүний раундууд орохгүй — {error}",
                    level=LEVEL.WARNING,
                    stage=STAGE.PARSING,
                    step=step,
                )
            for warning in result.warnings:
                jobs.log(
                    job_db,
                    job,
                    f"   ! parse-ийн шалгалт: {warning}",
                    level=LEVEL.WARNING,
                    stage=STAGE.PARSING,
                    step=step,
                )
            if result.missing:
                jobs.log(
                    job_db,
                    job,
                    f"   ! {len(result.missing)} раунд аль ч хэсэгт алга: "
                    + ", ".join(str(n) for n in result.missing),
                    level=LEVEL.WARNING,
                    stage=STAGE.PARSING,
                    step=step,
                )
        else:
            jobs.log(
                job_db,
                job,
                "   → .dem хадгалагдаагүй — өгөгдлийн санд байгаа tick датанаас дахин уншина.",
                stage=STAGE.PARSING,
                step=step,
            )
            jobs.activity(
                job_db, job, key="parse:stored", stage=STAGE.PARSING,
                text=f"{map_label} · {mn.ingest_step('stored')} ({mn.mb(stored.size_bytes)})",
            )  # fmt: skip
            bundle = stored.bundle
            parsed = tickdata.parsed_map(bundle, demo.filename or map_label, stored.awpy_version)
        read_took = time.monotonic() - started
        match_map = analysis_store.ingest_map(
            db, demo, parsed, bundle=bundle, on_step=_ingest_reporter(job_db, job, map_label)
        )
        unread = {name: error for name, error in failed}
        for part in parts:
            if Path(part.path).name in unread:
                part.error = unread[Path(part.path).name][:2000]
            if part is demo or (part.is_downloaded and Path(part.path).name not in unread):
                store._mark_processed(part)
        db.commit()
        players = db.scalar(
            select(func.count())
            .select_from(MapRoster)
            .where(MapRoster.match_map_id == match_map.id)
        )
        jobs.log(
            job_db,
            job,
            f"   ✓ {mn.game_map(parsed.map_name)} {match_map.scoreline} · "
            f"{parsed.n_rounds} раунд · {players} тоглогч · "
            f"tick дата {mn.mb(len(bundle or b''))} · уншилт {mn.duration(read_took)}, "
            f"бүгд {mn.duration(time.monotonic() - started)}",
            level=LEVEL.SUCCESS,
            stage=STAGE.PARSING,
            step=step,
        )
        totals["parsed"] += 1
        totals["rounds"] += parsed.n_rounds
    except Exception as exc:  # DemoParseError, or anything else one demo throws
        db.rollback()
        store.record_processing_failure(db, demo, str(exc))
        jobs.log(
            job_db,
            job,
            f"   ✗ боловсруулж чадсангүй — {exc}",
            level=LEVEL.ERROR,
            stage=STAGE.PARSING,
            step=step,
        )
        totals["failed"] += 1
    finally:
        for path in paths:
            path.unlink(missing_ok=True)


def _reparse(job_db: Session, db: Session, job: AnalysisJob, match_ids: list[int]) -> dict:
    """Maps of this fixture's teams that are behind the current schema, parsed
    again from their stored Tick Data.

    Always runs, even when nothing was downloaded: it is what keeps the analysis
    on the current ingest. Scoped to this job's own two teams, so a run never
    sits behind some other fixture's backlog. A map with no Tick Data to read
    from, or whose Tick Data predates the economy or the Loadout, is left for a download to
    fix, and counted.
    """
    pending = analysis_store.pending_map_demos(db, match_ids=match_ids)
    stored = [d for d in pending if _reparseable(d)]
    stuck = len(pending) - len(stored)
    version = analysis_store.CURRENT_SCHEMA_VERSION
    jobs.set_stage(
        job_db,
        job,
        STAGE.PARSING,
        _at(STAGE.PARSING),
        f"{len(stored)} мап хуучин schema-д байна — хадгалсан tick датанаас v{version} руу "
        "дахин боловсруулна."
        if stored
        else f"Бүх мап schema v{version}-д байна.",
    )
    totals = {"parsed": 0, "rounds": 0, "failed": 0, "stuck": stuck}
    if stuck:
        jobs.log(
            job_db,
            job,
            f"{stuck} мап боловсруулагдаагүй, эсвэл tick датанд нь эдийн засаг, зэвсэглэл "
            "байхгүй — "
            "тэдгээрийн матчийг дахин татахад боловсруулагдана.",
            level=LEVEL.WARNING,
            stage=STAGE.PARSING,
        )
    steps = _Steps(len(stored))
    for demo in stored:
        jobs.check_cancelled(job_db, job)
        _parse_one(job_db, db, job, demo, None, totals, steps.next())
        jobs.set_stage(job_db, job, STAGE.PARSING, _at(STAGE.PARSING, steps.done, steps.total))
    if totals["parsed"]:
        _warm_pool(job_db, job)
    jobs.finish_stage(job_db, job, STAGE.PARSING, "", totals)
    return totals


def _warm_pool(job_db: Session, job: AnalysisJob) -> None:
    """Measure the Pool on what was just parsed, so a Game Plan opened meanwhile
    finds it ready instead of computing it inside the request (`pool_cache`)."""
    jobs.activity(job_db, job, key="pool", stage=STAGE.PARSING, text=mn.POOL_WARMING)
    gameplan.warm_pool()


def _why_parse(demo: Demo) -> str:
    """Why this demo is queued -- never parsed, or parsed under an old schema.

    A run that re-parses forty maps nobody asked about looks broken until it
    says the schema moved.
    """
    current = analysis_store.CURRENT_SCHEMA_VERSION
    analysis = demo.analysis
    if analysis is None:
        return f"хэзээ ч боловсруулагдаагүй (schema v{current})"
    if _unmerged(demo):
        return "хэсгүүдийг нь өмнө нь тус тусад нь уншсан — одоо нэгтгэж дахин боловсруулна"
    if (analysis.schema_version or 0) < current:
        return (
            f"schema v{analysis.schema_version} → v{current} болсон тул дахин "
            "боловсруулна — шинэ үзүүлэлт хуучин матчид ч хүрнэ"
        )
    return f"дахин боловсруулахыг хүссэн (schema v{current})"


def _ingest_reporter(job_db: Session, job: AnalysisJob, map_label: str):
    """Name each ingest pass. Storing one map is ten passes and ten seconds."""

    def report(key: str) -> None:
        jobs.activity(
            job_db,
            job,
            key=f"ingest:{key}",
            stage=STAGE.PARSING,
            text=f"{map_label} · {mn.ingest_step(key)}",
        )

    return report


# -- the result --------------------------------------------------------------
def _own_match_ids(db: Session, my_team: Team, opponent: Team) -> list[int]:
    """HLTV ids of every match either side of this fixture has played.

    Scopes UNPACKING/PARSING to this job's own two teams.
    """
    ids = (my_team.id, opponent.id)
    return list(
        db.scalars(
            select(Match.hltv_id).where(or_(Match.team1_id.in_(ids), Match.team2_id.in_(ids)))
        )
    )


def _link_matches(
    job_db: Session, db: Session, job: AnalysisJob, my_team: Team, opponent: Team
) -> list[int]:
    """Attach every match with a parsed map for either team; returns their HLTV ids."""
    rows = db.execute(
        # played_at is selected because MySQL refuses DISTINCT ordered by an unselected column.
        select(Match.id, Match.hltv_id, Match.played_at)
        .join(MatchMap, MatchMap.match_id == Match.id)
        .join(MapRoster, MapRoster.match_map_id == MatchMap.id)
        .where(MapRoster.team_id.in_((my_team.id, opponent.id)), MatchMap.parsed_at.is_not(None))
        .distinct()
        .order_by(Match.played_at.desc())
    ).all()
    job.matches = list(job_db.scalars(select(Match).where(Match.id.in_([r.id for r in rows]))))
    job_db.commit()
    return [r.hltv_id for r in rows]


def _summaries(db: Session, hltv_ids: list[int]) -> list[dict]:
    """What the job page lists per match, denormalised so it keeps reading correctly."""
    if not hltv_ids:
        return []
    # Collections loaded early in the run (match.demos, map_results) are stale by now.
    db.expire_all()
    by_id = {m.hltv_id: m for m in db.scalars(select(Match).where(Match.hltv_id.in_(hltv_ids)))}
    out = []
    for hltv_id in hltv_ids:
        match = by_id.get(hltv_id)
        if match is None:
            continue
        archive = match.archive_demo
        maps = sorted(match.map_results, key=lambda m: m.map_number)
        out.append(
            {
                "match_id": match.id,
                "hltv_id": match.hltv_id,
                "url": match.url,
                "team1": match.team1.name if match.team1 else "?",
                "team2": match.team2.name if match.team2 else "?",
                "score": match.score,
                "tournament": match.tournament.name if match.tournament else "",
                "played_at": match.played_at.date().isoformat() if match.played_at else None,
                "demo": archive.status
                if archive
                else ("none" if match.demo_checked_at and not match.demo_url else "pending"),
                "maps": [
                    {
                        "map": mn.game_map(m.game_map.name) if m.game_map else "?",
                        "map_number": m.map_number,
                        "scoreline": m.scoreline,
                        "rounds": m.n_rounds,
                        "parsed": m.is_parsed,
                    }
                    for m in maps
                ],
            }
        )
    return out


def _as_scraped(team: Team):
    """The scraper's dataclass wants an id and a slug, not a model."""
    from app.services.client import Team as ScrapedTeam

    return ScrapedTeam(id=team.hltv_id, name=team.name, slug=team.slug or "team")
