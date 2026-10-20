"""A Workspace's own Demos in: Scrims and official Matches HLTV doesn't carry
(CONTEXT.md: Scrim; docs/plans/02-data-sources.md DATA-1).

Staff describe the file (:func:`create`), send it in parts (:func:`put_part`,
kept in MySQL, docs/adr/0002) and close it (:func:`complete`), which queues a
job on the parse queue (OPS-6). The job (``tasks.ingest_upload``) puts the
parts together in its scratch folder, unpacks an archive, parses each Demo under
the heavy permit and ingests it as a Map of one private Match
(:func:`match_for`), then drops the parts.

**Who is who.** A Scrim's Demo rarely names its clubs. Each Map's Players are
split into the two sides they started on (:func:`side_groups`); the side with
more of my team's known Players is mine (:func:`pick_mine`). When neither side
clearly is, the Map is stored with no Teams (it counts nowhere) and waits for
Staff to say which five are ours (:func:`answer`), then it is re-ingested from
its stored Tick Data with the Teams given outright.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    AnalysisJob,
    JobKind,
    MapRoster,
    Match,
    MatchSource,
    Player,
    Team,
    Upload,
    UploadPart,
    UploadStatus,
    User,
    WorkspaceTeam,
)
from app.models.upload import MAX_PARTS, PART_BYTES
from app.services import archive, jobs, store

logger = logging.getLogger(__name__)

DEMO_SUFFIX = ".dem"
ARCHIVE_SUFFIXES = (".zip", ".rar", ".7z", ".gz", ".bz2", ".xz", ".tar", ".tgz")
# A side is ours when it holds at least this many of my team's known Players,
# and more than the other side does.
MIN_KNOWN = 2


class UploadError(ValueError):
    """Something about the upload a person can fix; its text says what."""


def _suffix(filename: str) -> str:
    return Path(filename.lower()).suffix


def check_file(filename: str, size: int) -> None:
    if _suffix(filename) not in (DEMO_SUFFIX, *ARCHIVE_SUFFIXES):
        raise UploadError(".dem эсвэл archive (.zip, .rar, .7z, .gz, .bz2) файл сонгоно уу.")
    if size <= 0:
        raise UploadError("Файл хоосон байна.")
    if size > PART_BYTES * MAX_PARTS:
        raise UploadError(f"Файл хэт том: {PART_BYTES * MAX_PARTS // 2**20} MB хүртэл.")


def create(
    db: Session,
    user: User,
    *,
    kind: str,
    played_on: date,
    my_team_id: int,
    opponent_id: int | None,
    opponent_name: str,
    note: str,
    filename: str,
    size: int,
) -> Upload:
    check_file(filename, size)
    mine = db.scalar(
        select(WorkspaceTeam.team_id).where(
            WorkspaceTeam.workspace_id == user.workspace_id, WorkspaceTeam.team_id == my_team_id
        )
    )
    if mine is None:
        raise UploadError("Энэ Workspace-ийн my team биш.")
    if opponent_id is not None:
        if opponent_id == my_team_id:
            raise UploadError("Өрсөлдөгч нь өөр баг байх ёстой.")
        if db.get(Team, opponent_id) is None:
            raise UploadError("Ийм баг алга.")
    elif not opponent_name.strip():
        raise UploadError("Өрсөлдөгч эсвэл scrim-ийн түншийн нэрийг бичнэ үү.")
    upload = Upload(
        workspace_id=user.workspace_id,
        created_by_id=user.id,
        kind=kind,
        played_on=played_on,
        my_team_id=my_team_id,
        opponent_id=opponent_id,
        opponent_name=opponent_name.strip()[:120],
        note=note.strip()[:500],
        filename=Path(filename).name[:255],
        size_bytes=size,
        parts_total=math.ceil(size / PART_BYTES),
        status=UploadStatus.RECEIVING,
        maps=[],
    )
    db.add(upload)
    db.commit()
    return upload


def put_part(db: Session, upload: Upload, n: int, data: bytes) -> int:
    """Keep part ``n`` (0-based); sending it again replaces it. Returns how many are in."""
    if upload.status != UploadStatus.RECEIVING:
        raise UploadError("Энэ upload аль хэдийн хаагдсан.")
    if not 0 <= n < upload.parts_total:
        raise UploadError(f"Хэсгийн дугаар 0–{upload.parts_total - 1} байх ёстой.")
    if not data or len(data) > PART_BYTES:
        raise UploadError(f"Хэсэг бүр 1 byte-аас {PART_BYTES} byte хүртэл.")
    db.execute(delete(UploadPart).where(UploadPart.upload_id == upload.id, UploadPart.n == n))
    db.add(UploadPart(upload_id=upload.id, n=n, data=data))
    db.commit()
    return received(db, upload)[0]


def received(db: Session, upload: Upload) -> tuple[int, int]:
    """(parts in, bytes in)."""
    count, size = db.execute(
        select(
            func.count(UploadPart.id), func.coalesce(func.sum(func.length(UploadPart.data)), 0)
        ).where(UploadPart.upload_id == upload.id)
    ).one()
    return int(count), int(size)


def complete(db: Session, upload: Upload, user: User) -> AnalysisJob:
    """Close the upload once every part is in, and queue its parse."""
    if upload.status != UploadStatus.RECEIVING:
        raise UploadError("Энэ upload аль хэдийн хаагдсан.")
    count, size = received(db, upload)
    if count != upload.parts_total or size != upload.size_bytes:
        raise UploadError(
            f"{upload.parts_total} хэсгээс {count} нь ирсэн ({size}/{upload.size_bytes} byte)."
        )
    return queue(db, upload, user)


def queue(db: Session, upload: Upload, user: User | None) -> AnalysisJob:
    """A fresh job for ``upload`` on the parse queue (a parse, or a "who is who" answer)."""
    my_team = db.get(Team, upload.my_team_id)
    opponent = db.get(Team, upload.opponent_id) if upload.opponent_id else None
    job = AnalysisJob(
        kind=JobKind.UPLOAD,
        requested_by_id=user.id if user else None,
        my_team_name=my_team.name if my_team else "",
        opponent_name=opponent.name if opponent else upload.opponent_name,
        my_team_id=upload.my_team_id,
        opponent_id=upload.opponent_id,
        download=False,
    )
    db.add(job)
    db.flush()
    upload.job_id = job.id
    upload.status = UploadStatus.QUEUED
    upload.error = ""
    db.commit()
    dispatch(db, job)
    return job


def dispatch(db: Session, job: AnalysisJob) -> None:
    """Send an upload job to the parse queue. A broker failure fails the job."""
    from app.tasks import ingest_upload

    try:
        sent = ingest_upload.apply_async((job.id,), queue=get_settings().celery_parse_queue)
    except Exception as exc:
        logger.exception("could not queue upload job %s", job.public_id)
        jobs.fail(db, job, f"Celery broker-т хүрсэнгүй ({exc}).")
        return
    job.celery_task_id = sent.id
    db.commit()
    jobs.log(db, job, "Parse-ийн дараалалд орлоо.", stage="queued")


# ------------------------------------------------------------- the job's side ---
def assemble(db: Session, upload: Upload, folder: Path) -> Path:
    """Write the parts, in order, to one file in the job's ``folder``."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / upload.filename
    with target.open("wb") as out:
        for n in range(upload.parts_total):
            data = db.scalar(
                select(UploadPart.data).where(UploadPart.upload_id == upload.id, UploadPart.n == n)
            )
            if data is None:
                raise UploadError(f"Хэсэг {n} алга.")
            out.write(data)
    return target


def demo_files(path: Path, folder: Path) -> list[Path]:
    """The Demos in an uploaded file: itself, or what its archive holds."""
    if path.suffix.lower() == DEMO_SUFFIX:
        return [path]
    entries = archive.list_demos(path)
    if not entries:
        raise UploadError("Archive дотор .dem файл алга.")
    return archive.extract(path, folder / "demos", entries)


def drop_parts(db: Session, upload: Upload) -> None:
    db.execute(delete(UploadPart).where(UploadPart.upload_id == upload.id))
    db.commit()


def match_for(db: Session, upload: Upload) -> Match:
    """The upload's one private Match, made on first use."""
    if upload.match_id:
        found = db.get(Match, upload.match_id)
        if found is not None:
            return found
    opponent = (
        db.get(Team, upload.opponent_id)
        if upload.opponent_id
        else store._team_by_name(db, upload.opponent_name)
    )
    match = Match(
        hltv_id=None,
        workspace_id=upload.workspace_id,
        kind=upload.kind,
        source=MatchSource.UPLOAD,
        team1_id=upload.my_team_id,
        team2_id=opponent.id if opponent else None,
        opponent_label=upload.opponent_name if not upload.opponent_id else "",
        played_at=datetime.combine(upload.played_on, time(12, 0)),
        score="",
    )
    db.add(match)
    db.flush()
    upload.match_id = match.id
    db.commit()
    return match


def side_groups(parsed) -> list[list[int]]:
    """The Map's Players as the two sides they played on, by Steam id.

    The first Round with both sides fixes who is with whom; anyone who joins
    later goes with the side most of his Round's teammates are on."""
    by_round: dict[int, dict[str, set[int]]] = defaultdict(lambda: {"ct": set(), "t": set()})
    for row in parsed.player_sides.to_dicts():
        side = str(row["side"])
        if side in ("ct", "t"):
            by_round[int(row["round_num"])][side].add(int(row["steamid"]))
    groups: list[set[int]] = [set(), set()]
    for number in sorted(by_round):
        sides = by_round[number]
        if not groups[0] and not groups[1]:
            if sides["ct"] and sides["t"]:
                groups = [set(sides["ct"]), set(sides["t"])]
            continue
        for side in ("ct", "t"):
            members = sides[side]
            if not members:
                continue
            ours = [len(members & g) for g in groups]
            if max(ours) == 0:
                continue
            home = groups[ours.index(max(ours))]
            for sid in members:
                if not any(sid in g for g in groups):
                    home.add(sid)
    return [sorted(g) for g in groups]


def known_players(db: Session, team_id: int | None) -> set[int]:
    """Steam ids of the Players any stored Map rostered for ``team_id``."""
    if team_id is None:
        return set()
    return set(
        db.scalars(
            select(Player.steamid)
            .join(MapRoster, MapRoster.player_id == Player.id)
            .where(MapRoster.team_id == team_id)
            .distinct()
        )
    )


def pick_mine(groups: list[list[int]], mine: set[int], theirs: set[int]) -> int | None:
    """Which side is my team's, or None when the Players don't say clearly."""
    if len(groups) != 2:
        return None
    ours = [len(set(g) & mine) for g in groups]
    if max(ours) >= MIN_KNOWN and ours[0] != ours[1]:
        return ours.index(max(ours))
    known = [len(set(g) & theirs) for g in groups]
    if max(known) >= MIN_KNOWN and known[0] != known[1]:
        return 1 - known.index(max(known))
    return None


def sides(groups: list[list[int]], mine: int, my_team_id: int, opponent_id: int | None) -> dict:
    """Steam id -> Team id for ``ingest_map``: my side mine, the other theirs."""
    out = {sid: my_team_id for sid in groups[mine]}
    if opponent_id is not None:
        out.update({sid: opponent_id for sid in groups[1 - mine]})
    return out


def answer(db: Session, upload: Upload, map_number: int, mine: int, user: User) -> AnalysisJob:
    """Staff said which side is ours on one Map: re-ingest it with the Teams given."""
    if mine not in (0, 1):
        raise UploadError("0 эсвэл 1 гэж сонгоно уу.")
    entries = list(upload.maps or [])
    entry = next((e for e in entries if e["map_number"] == map_number), None)
    if entry is None:
        raise UploadError("Ийм Map энэ upload-д алга.")
    entry = {**entry, "mine": mine, "assigned": False}
    upload.maps = [entry if e["map_number"] == map_number else e for e in entries]
    db.commit()
    return queue(db, upload, user)


def names_by_steamid(parsed) -> dict[int, str]:
    return {int(r["steamid"]): str(r.get("name") or "") for r in parsed.roster.to_dicts()}
