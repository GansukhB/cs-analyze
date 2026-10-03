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
import time
import traceback
from collections import deque
from pathlib import Path

from sqlalchemy import distinct, func, or_, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    AnalysisJob,
    Demo,
    EventLevel,
    JobStage,
    MapRoster,
    Match,
    MatchMap,
    Team,
    TickDataset,
)
from app.services import analysis_store, jobs, mn, store, tickdata

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
        job.celery_task_id = self.request.id or ""
        job_db.commit()
        try:
            return run_pipeline(job_db, db, job)
        except jobs.JobCancelled:
            db.rollback()
            jobs.cancel(job_db, job)
            return {"job": str(job.public_id), "status": job.status}
        except Exception as exc:
            logger.exception("analysis job %s failed", job.public_id)
            db.rollback()
            jobs.fail(job_db, job, f"{type(exc).__name__}: {exc}")
            jobs.log(job_db, job, traceback.format_exc()[-2000:], level=LEVEL.DEBUG)
            raise


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


def _scratch(job: AnalysisJob) -> Path:
    """This run's own scratch folder, and the leftovers of any run that died.

    Only one job runs at a time, so anything else under ``tmp/`` belongs to a
    run that never reached its cleanup (a killed worker, a restarted container).
    """
    root = get_settings().hltv_data_dir / "tmp"
    if root.exists():
        for leftover in root.iterdir():
            if leftover.name != str(job.public_id):
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
        jobs.finish_stage(job_db, job, STAGE.PARSING, "", totals["parsing"])
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(maps_dir, ignore_errors=True)
        db.rollback()
        store.forget_files(db, row)


def _redownload_reason(db: Session, row: Match) -> str:
    """Why a match whose archive was unpacked must be fetched again, or ``""``.

    A map that never parsed, with no Tick Data to parse it from, can only be
    retried from a fresh download: its Demo was deleted with the match's files.
    So can a stale map whose Tick Data predates the economy (docs/adr/0003).
    """
    pending = analysis_store.pending_map_demos(db, match_ids=[row.hltv_id])
    stuck = [d for d in pending if d.analysis is None or d.analysis.tick_dataset is None]
    old = [d for d in pending if d not in stuck and not _reparseable(d)]
    reasons = []
    if stuck:
        names = ", ".join(mn.game_map(d.map) for d in stuck)
        reasons.append(
            f"{len(stuck)} мап ({names}) боловсруулагдаагүй бөгөөд tick дата хадгалагдаагүй"
        )
    if old:
        names = ", ".join(mn.game_map(d.map) for d in old)
        reasons.append(f"{len(old)} мапын ({names}) tick датанд эдийн засаг байхгүй")
    return "; ".join(reasons)


def _reparseable(demo: Demo) -> bool:
    return demo.analysis is not None and tickdata.reparseable(demo.analysis.tick_dataset)


def _fetch_one(job_db, db, job, client, browser, match, scratch: Path, totals: dict, step):
    """One match: skip it if it is already parsed, otherwise download it.

    Returns the archive on disk, or None when there is nothing to unpack. Two
    lines per match on purpose: the first names the match, the second says what
    was decided about it, so the decision can be coloured while the identity
    stays plain.
    """
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
    except HltvBlocked as exc:
        if not browser.is_connected():
            # The Chromium process itself is gone; every match still queued would
            # fail the same way. _fetch() turns this into "continue with the database".
            raise
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
        browser.download(
            link, target, on_progress=_download_reporter(job_db, job, step, match, target)
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
            + ", ".join(mn.game_map(e.map) for e in entries),
            stage=STAGE.UNPACKING,
            step=step,
        )
        started = time.monotonic()
        written = archive_service.extract(
            path, dest, entries, on_progress=_unpack_reporter(job_db, job, path)
        )
        store.record_extraction(db, demo, zip(entries, written, strict=True))
        sizes = ", ".join(
            f"{mn.game_map(e.map)} {mn.mb(p.stat().st_size if p.exists() else 0)}"
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
    except archive_service.ArchiveError as exc:
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
    """Parse one map and store it with its Tick Data; delete its ``.dem`` after.

    The Demo is the source when it is on disk (just unpacked); otherwise the
    map's stored Tick Data is, which is how a map on an old schema is parsed
    again without downloading anything.
    """
    from app.services.demo_parser import parse_map

    path = Path(demo.path) if demo.path else None
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
    if path is None or not path.exists():
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
        if stored is None:
            jobs.activity(
                job_db,
                job,
                key="parse:awpy",
                stage=STAGE.PARSING,
                text=f"{map_label} · {mn.ingest_step('awpy')} ({mn.mb(path.stat().st_size)})",
            )
            parsed = parse_map(path)
            jobs.activity(
                job_db, job, key="parse:pack", stage=STAGE.PARSING,
                text=f"{map_label} · {mn.ingest_step('pack')}",
            )  # fmt: skip
            bundle = tickdata.pack(parsed, (scratch or _scratch(job)) / "tickdata")
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
        store.mark_processed(db, demo)
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
        if path is not None:
            path.unlink(missing_ok=True)


def _reparse(job_db: Session, db: Session, job: AnalysisJob, match_ids: list[int]) -> dict:
    """Maps of this fixture's teams that are behind the current schema, parsed
    again from their stored Tick Data.

    Always runs, even when nothing was downloaded: it is what keeps the analysis
    on the current ingest. Scoped to this job's own two teams, so a run never
    sits behind some other fixture's backlog. A map with no Tick Data to read
    from, or whose Tick Data predates the economy, is left for a download to
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
            f"{stuck} мап боловсруулагдаагүй, эсвэл tick датанд нь эдийн засаг байхгүй — "
            "тэдгээрийн матчийг дахин татахад боловсруулагдана.",
            level=LEVEL.WARNING,
            stage=STAGE.PARSING,
        )
    steps = _Steps(len(stored))
    for demo in stored:
        jobs.check_cancelled(job_db, job)
        _parse_one(job_db, db, job, demo, None, totals, steps.next())
        jobs.set_stage(job_db, job, STAGE.PARSING, _at(STAGE.PARSING, steps.done, steps.total))
    jobs.finish_stage(job_db, job, STAGE.PARSING, "", totals)
    return totals


def _why_parse(demo: Demo) -> str:
    """Why this demo is queued -- never parsed, or parsed under an old schema.

    A run that re-parses forty maps nobody asked about looks broken until it
    says the schema moved.
    """
    current = analysis_store.CURRENT_SCHEMA_VERSION
    analysis = demo.analysis
    if analysis is None:
        return f"хэзээ ч боловсруулагдаагүй (schema v{current})"
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
