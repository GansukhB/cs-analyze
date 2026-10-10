"""Bringing cstat's teams, matches and map demos into cs-analyze.

cstat (``~/gs/cstat``) is the Django project this one was ported from. Its
SQLite database lists the HLTV teams, tournaments and matches it scouted, and
its ``data/maps`` folder still holds every map demo it unpacked. This reads
both and writes neither: the database is opened read-only and the ``.dem``
files are parsed where they lie, never moved or deleted (they are cstat's).

What cs-analyze already holds wins. A team, tournament or match found here by
HLTV id (or name) only gets its blank fields filled; a map already parsed under
the current schema with re-parseable Tick Data is left alone. Everything else
is parsed from cstat's ``.dem``, which is what brings the economy (schema 11)
and the Replay's Loadout to maps that were parsed before them. Safe to run
again: it picks up only what is new or stale.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.services import analysis_store, store, tickdata
from app.services.archive import parse_demo_name


def _when(value: str | None) -> datetime | None:
    """cstat's SQLite datetimes are naive UTC text, like every datetime here."""
    return datetime.fromisoformat(value) if value else None


def _fill(row, **values) -> None:
    """Set each attribute that is still blank (None or "")."""
    for key, value in values.items():
        if value not in (None, "") and getattr(row, key) in (None, ""):
            setattr(row, key, value)


def _read(root: Path) -> dict[str, list[sqlite3.Row]]:
    path = root / "db.sqlite3"
    if not path.is_file():
        raise FileNotFoundError(f"No cstat database at {path}")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return {
            table: con.execute(f"SELECT * FROM hltv_{table} ORDER BY id").fetchall()  # noqa: S608
            for table in ("team", "teamalias", "event", "match", "demo")
        }
    finally:
        con.close()


def _team(db: Session, row: sqlite3.Row) -> models.Team:
    team = None
    if row["hltv_id"]:
        team = db.scalar(select(models.Team).where(models.Team.hltv_id == row["hltv_id"]))
        if team is None:
            # Adopt a placeholder created under the same name, as a Scout would.
            team = db.scalar(
                select(models.Team).where(
                    models.Team.hltv_id.is_(None), models.Team.name == row["name"]
                )
            )
        if team is None:
            team = models.Team(hltv_id=row["hltv_id"], name=row["name"], slug=row["slug"] or "")
            db.add(team)
            db.flush()
            return team
    else:
        team = store._team_by_name(db, row["name"])
    _fill(team, hltv_id=row["hltv_id"], slug=row["slug"])
    return team


def _tournament(db: Session, row: sqlite3.Row) -> models.Tournament:
    found = None
    if row["hltv_id"]:
        found = db.scalar(
            select(models.Tournament).where(models.Tournament.hltv_id == row["hltv_id"])
        )
    if found is None:
        found = db.scalar(select(models.Tournament).where(models.Tournament.name == row["name"]))
    if found is None:
        found = models.Tournament(name=row["name"])
        db.add(found)
    _fill(found, hltv_id=row["hltv_id"], slug=row["slug"])
    db.flush()
    return found


def _match(db: Session, row: sqlite3.Row, teams: dict, tournaments: dict) -> models.Match:
    match = db.scalar(select(models.Match).where(models.Match.hltv_id == row["hltv_id"]))
    if match is None:
        match = models.Match(hltv_id=row["hltv_id"])
        db.add(match)
    _fill(
        match,
        slug=row["slug"],
        score=row["score"],
        team1_score=row["team1_score"],
        team2_score=row["team2_score"],
        played_at=_when(row["played_at"]),
        demo_url=row["demo_url"],
        demo_checked_at=_when(row["demo_checked_at"]),
    )
    _fill(
        match,
        team1_id=teams.get(row["team1_id"]),
        team2_id=teams.get(row["team2_id"]),
        tournament_id=tournaments.get(row["event_id"]),
    )
    db.flush()
    return match


def _dem_path(root: Path, row: sqlite3.Row) -> Path | None:
    """Where cstat keeps this map demo: its recorded path, else data/maps/*/<file>."""
    recorded = Path(row["path"]) if row["path"] else None
    if recorded and recorded.is_file():
        return recorded
    if row["filename"]:
        return next((root / "data" / "maps").glob(f"*/{row['filename']}"), None)
    return None


def _current(demo: models.Demo) -> bool:
    """Already parsed under this schema, from Tick Data a re-parse could use and
    that has Sightings: cstat still has the Demo, so a map lacking them gets them
    here even though a Scout never downloads again for them (docs/adr/0006)."""
    analysis = demo.analysis
    return (
        analysis is not None
        and (not demo.part or demo.is_processed)  # Demo parts merged (docs/adr/0009)
        and (analysis.schema_version or 0) >= analysis_store.CURRENT_SCHEMA_VERSION
        and tickdata.reparseable(analysis.tick_dataset)
        and tickdata.has_sightings(analysis.tick_dataset)
    )


def run(
    db: Session,
    root: Path,
    *,
    parse: bool = True,
    log: Callable[[str], None] = print,
    match_hltv_id: int | None = None,
    map_name: str | None = None,
) -> dict:
    """Import cstat's rows, then parse every map demo that is missing or stale here.

    ``match_hltv_id`` and ``map_name`` (``inferno`` or ``de_inferno``) narrow the
    parse to one Match, or one map of it; the rows are imported in full either way.
    """
    rows = _read(root)
    teams = {r["id"]: _team(db, r).id for r in rows["team"]}
    for r in rows["teamalias"]:
        if teams.get(r["team_id"]) and not db.scalar(
            select(models.TeamAlias).where(models.TeamAlias.clan_name == r["clan_name"])
        ):
            db.add(models.TeamAlias(clan_name=r["clan_name"], team_id=teams[r["team_id"]],
                                    note=r["note"] or "cstat"))  # fmt: skip
    tournaments = {r["id"]: _tournament(db, r).id for r in rows["event"]}
    matches = {r["id"]: _match(db, r, teams, tournaments) for r in rows["match"]}
    db.commit()
    log(
        f"cstat: {len(teams)} баг, {len(tournaments)} тэмцээн, {len(matches)} тоглолт "
        "(байгаа мөрийн зөвхөн хоосон талбарыг бөглөв)."
    )

    totals = {"maps": 0, "parsed": 0, "current": 0, "missing": 0, "failed": 0}
    # Each Match Map to parse: part 1 (or its only Demo) and every file, in order.
    groups: dict[tuple[int, str], list[tuple[models.Demo, Path | None]]] = {}
    for r in rows["demo"]:
        match = matches.get(r["match_id"])
        if match is None:
            continue
        if match_hltv_id is not None and match.hltv_id != match_hltv_id:
            continue
        map_, number, part = r["map"] or "", r["map_number"], 0
        if map_ and r["filename"] and (number is None or "-" in map_):
            # cstat kept a file's whole stem as the map of a Bo1 or a Demo part.
            entry = parse_demo_name(r["filename"])
            map_, number, part = entry.map, number or entry.map_number, entry.part
        if map_name and map_ and map_.removeprefix("de_") != map_name.removeprefix("de_"):
            continue
        demo = store._demo(db, match, map_, part)
        _fill(demo, url=r["url"], filename=r["filename"], size_bytes=r["size_bytes"],
              map_number=number, downloaded_at=_when(r["downloaded_at"]))  # fmt: skip
        if r["is_downloaded"]:
            demo.is_downloaded = True
        if not r["map"]:
            # The archive: cstat unpacked it, and its map demos are listed below.
            if r["is_processed"] and demo.is_downloaded and not demo.is_processed:
                store._mark_processed(demo)
            continue
        groups.setdefault((match.id, map_), []).append((demo, _dem_path(root, r)))
    queue: list[list[tuple[models.Demo, Path]]] = []
    for group in groups.values():
        group.sort(key=lambda item: item[0].part)
        totals["maps"] += 1
        if _current(group[0][0]):
            totals["current"] += 1
            continue
        for demo, path in group:
            if path is None:
                totals["missing"] += 1
                log(f"  ? {demo.filename}: .dem файл cstat-д алга")
        files = [(demo, path) for demo, path in group if path is not None]
        if files:
            queue.append(files)
    db.commit()
    log(
        f"Map demo {totals['maps']}: {totals['current']} нь аль хэдийн schema "
        f"v{analysis_store.CURRENT_SCHEMA_VERSION}-д, {len(queue)} нь parse хийгдэнэ."
    )
    if not parse:
        return totals

    scratch = get_settings().hltv_data_dir / "tmp" / "cstat-import"
    started_all = time.monotonic()
    try:
        for n, files in enumerate(queue, start=1):
            started = time.monotonic()
            demo, path = files[0]
            try:
                result = tickdata.parse_parts(
                    [p for _d, p in files], scratch, parts=bool(demo.part)
                )
                parsed = result.parsed
                match_map = analysis_store.ingest_map(db, demo, parsed, bundle=result.bundle)
                unread = dict(result.failed)
                for part, part_path in files:
                    if part_path.name in unread:
                        part.error = unread[part_path.name][:2000]
                    elif part.is_downloaded or part is demo:
                        store._mark_processed(part)
                db.commit()
                totals["parsed"] += 1
                merged = f" ({len(files)} хэсэг нэгтгэв)" if demo.part else ""
                log(f"  ✓ {n}/{len(queue)} {path.name}{merged} · {match_map.scoreline} · "
                    f"{parsed.n_rounds} раунд · {time.monotonic() - started:.0f}с")  # fmt: skip
                for name, error in result.failed:
                    log(f"    ! {name}: уншиж чадсангүй — {error}")
                if result.missing:
                    log(f"    ! аль ч хэсэгт алга раунд: {', '.join(map(str, result.missing))}")
            except Exception as exc:  # one bad demo must not stop the rest
                db.rollback()
                store.record_processing_failure(db, demo, str(exc))
                totals["failed"] += 1
                log(f"  ✗ {n}/{len(queue)} {path.name}: {exc}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    log(
        f"Дууслаа: {totals['parsed']} parse хийв, {totals['failed']} алдаа, "
        f"{totals['missing']} файлгүй · {time.monotonic() - started_all:.0f}с."
    )
    return totals
