"""Persisting what the scrapers read.

``client.py`` returns frozen dataclasses and never imports the ORM; everything
that writes to the database lives here. Every entry point is idempotent -- it
resolves an existing row by HLTV id (or, for an opponent seen only by name, by
name) and updates it, so fetching the same team twice does not duplicate
anything.

Each public function commits, the way Django's autocommit did in cstat: one
failed match must not roll back the matches stored before it. Private helpers
only flush, so a function built from several of them stays one transaction.

Dataclass and model share their names, so the dataclasses are referred to as
``client.Team``/``client.Match`` and the models as ``models.Team`` etc.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app import models
from app.models.base import utcnow
from app.services import archive as archive_service
from app.services import client, teamnames

logger = logging.getLogger(__name__)

# "2 - 0", "16-13", "2 : 1" -- HLTV renders the two halves in separate spans.
_SCORE = re.compile(r"(\d+)\s*[-–:]\s*(\d+)")


def split_score(raw: str) -> tuple[int | None, int | None]:
    """Parse ``"2 - 0"`` into ``(2, 0)``; ``(None, None)`` if it doesn't fit."""
    match = _SCORE.search(raw or "")
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


# -- teams -----------------------------------------------------------------
def get_or_create_team(db: Session, scraped: client.Team) -> models.Team:
    """Store a team that HLTV gave us an id for."""
    team = db.scalar(select(models.Team).where(models.Team.hltv_id == scraped.id))
    if team is None:
        # Adopt the placeholder an earlier results row may have created for
        # this team under the same name, rather than adding a second row.
        team = db.scalar(
            select(models.Team).where(
                models.Team.hltv_id.is_(None), models.Team.name == scraped.name
            )
        )
        if team is None:
            team = models.Team(hltv_id=scraped.id, name=scraped.name, slug=scraped.slug)
            db.add(team)
            db.commit()
            return team
        team.hltv_id = scraped.id

    if scraped.name:
        team.name = scraped.name
    if scraped.slug:
        team.slug = scraped.slug
    db.commit()
    return team


def _team_by_name(db: Session, name: str) -> models.Team | None:
    """Store a team known only by the name printed on a results row.

    Prefers an already-identified team with that name; otherwise creates (or
    reuses) an id-less placeholder that :func:`get_or_create_team` can adopt.

    The name is matched through :mod:`app.services.teamnames` rather than
    compared literally, because this is where duplicate clubs are born: HLTV
    writes ``Natus Vincere`` on one results row and ``NAVI`` on another, and a
    string comparison quietly makes two teams out of one. An identified team
    always wins the tie -- it is the row a real search created.
    """
    name = (name or "").strip()
    if not name:
        return None

    exact = db.scalar(
        select(models.Team)
        .where(models.Team.name == name)
        # Identified teams first; MySQL has no NULLS LAST.
        .order_by(models.Team.hltv_id.is_(None), models.Team.hltv_id)
        .limit(1)
    )
    if exact is not None:
        return exact

    match = teamnames.resolve(name, db.scalars(select(models.Team)).all())
    if match is not None:
        team, score, why = match
        logger.info("team name %r matched existing %r (%s, %.2f)", name, team.name, why, score)
        return team
    team = models.Team(name=name)
    db.add(team)
    db.flush()
    return team


def _tournament(db: Session, name: str) -> models.Tournament | None:
    name = (name or "").strip()
    if not name:
        return None
    tournament = db.scalar(select(models.Tournament).where(models.Tournament.name == name))
    if tournament is None:
        tournament = models.Tournament(name=name)
        db.add(tournament)
        db.flush()
    return tournament


# -- matches ---------------------------------------------------------------
def get_or_create_match(db: Session, scraped: client.Match) -> models.Match:
    """Store one match plus the teams and tournament it refers to."""
    team1_score, team2_score = split_score(scraped.score)
    match = db.scalar(select(models.Match).where(models.Match.hltv_id == scraped.id))
    if match is None:
        match = models.Match(hltv_id=scraped.id)
        db.add(match)
    match.slug = scraped.slug
    match.team1 = _team_by_name(db, scraped.team1)
    match.team2 = _team_by_name(db, scraped.team2)
    match.tournament = _tournament(db, scraped.event)
    match.score = scraped.score
    match.team1_score = team1_score
    match.team2_score = team2_score
    match.played_at = (
        scraped.played_at.replace(tzinfo=None) if scraped.played_at else None
    )  # naive UTC, like every other datetime here
    db.commit()
    return match


# -- demos -----------------------------------------------------------------
class DemoNotDownloaded(ValueError):
    """Refused an attempt to process a demo that is not on disk yet."""


def record_demo_lookup(db: Session, match: models.Match, url: str | None) -> models.Match:
    """Remember what the match page said about a demo, including "none"."""
    match.demo_url = url or ""
    match.demo_checked_at = utcnow()
    db.commit()
    return match


def _demo(db: Session, match: models.Match, map: str = "", part: int = 0) -> models.Demo:
    """The row for one demo file, keyed on ``(match, map, part)``.

    Blank ``map`` is the match archive; ``part`` is a Demo part's number, 0 for
    a map recorded whole. This is the only place demo rows are created, which
    is what keeps a re-run from making a second row.
    """
    demo = db.scalar(
        select(models.Demo).where(
            models.Demo.match_id == match.id, models.Demo.map == map, models.Demo.part == part
        )
    )
    if demo is None:
        demo = models.Demo(match=match, map=map, part=part)
        db.add(demo)
        db.flush()
    return demo


def record_download(
    db: Session,
    match: models.Match,
    path: Path,
    *,
    url: str = "",
    size_bytes: int | None = None,
) -> models.Demo:
    """Mark this match's archive as downloaded. Blank ``url`` keeps the stored one."""
    demo = _demo(db, match)
    demo.filename = path.name
    demo.path = str(path)
    demo.size_bytes = size_bytes
    demo.is_downloaded = True
    demo.downloaded_at = utcnow()
    demo.error = ""
    if url:
        demo.url = url
    db.commit()
    return demo


def record_download_failure(db: Session, match: models.Match, url: str, error: str) -> models.Demo:
    """Record a download HLTV or Cloudflare refused, so it can be retried.

    An archive downloaded and unpacked before (a Match downloading again, ADR
    0003/0005) keeps that history: the database holds every processed Demo to be
    downloaded, and the next Scout retries it from its maps' state anyway.
    """
    demo = _demo(db, match)
    demo.url = url or demo.url
    if not demo.is_processed:
        demo.is_downloaded = False
        demo.downloaded_at = None
    demo.error = str(error)[:2000]
    db.commit()
    return demo


def _mark_processed(demo: models.Demo) -> None:
    """Flip ``is_processed``, refusing anything not downloaded first.

    The database enforces the same rule (see the Demo check constraint); this
    raises the readable error before it gets that far.
    """
    if not demo.is_downloaded:
        raise DemoNotDownloaded(f"{demo} is not downloaded; nothing to process. Fetch it first.")
    demo.is_processed = True
    demo.processed_at = utcnow()
    demo.error = ""


def mark_processed(db: Session, demo: models.Demo) -> models.Demo:
    _mark_processed(demo)
    db.commit()
    return demo


def record_extraction(
    db: Session,
    archive: models.Demo,
    extracted: Iterable[tuple[archive_service.DemoEntry, Path]],
) -> list[models.Demo]:
    """Record the ``.dem`` files unpacked from ``archive`` and mark it processed.

    One row per map, or per Demo part, keyed on ``(match, map, part)``, so
    unpacking the same archive twice updates those rows rather than adding more.
    """
    rows = []
    for entry, path in extracted:
        demo = _demo(db, archive.match, map=entry.map, part=entry.part)
        demo.map_number = entry.map_number
        demo.filename = path.name
        demo.path = str(path)
        demo.size_bytes = path.stat().st_size if path.exists() else None
        demo.is_downloaded = path.exists()
        demo.downloaded_at = demo.downloaded_at or utcnow()
        demo.url = archive.url
        demo.error = ""
        rows.append(demo)

    _mark_processed(archive)
    db.commit()
    return rows


def record_processing_failure(db: Session, demo: models.Demo, error: str) -> models.Demo:
    """Record why an unpack or parse failed, leaving ``is_processed`` false."""
    demo.error = str(error)[:2000]
    db.commit()
    return demo


def forget_files(db: Session, match: models.Match) -> None:
    """The match's archive and map demos were deleted after parsing: drop their paths.

    ``is_downloaded`` stays true -- it records that the file was fetched, which
    is what ``is_processed`` requires -- so a Demo's status keeps saying what
    happened to it.
    """
    for demo in db.scalars(select(models.Demo).where(models.Demo.match_id == match.id)):
        demo.path = ""
    db.commit()


def pending_archives(db: Session, match_ids: Iterable[int] | None = None) -> list[models.Demo]:
    """Archive rows that are downloaded and still need unpacking, oldest first."""
    query = (
        select(models.Demo)
        .join(models.Demo.match)
        .options(joinedload(models.Demo.match))
        .where(models.Demo.map == "", models.Demo.is_downloaded, ~models.Demo.is_processed)
        .order_by(models.Match.played_at, models.Demo.match_id)
    )
    if match_ids is not None:
        query = query.where(models.Match.hltv_id.in_(list(match_ids)))
    return list(db.scalars(query))
