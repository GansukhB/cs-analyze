"""A Workspace's own Demos in (docs/plans/02 DATA-1): describe, send in parts,
close; then answer "who is who" for a Map whose Players didn't say. Staff only,
and every upload is its Workspace's alone (docs/adr/0011)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import select

from app.deps import DbSession, StaffUser
from app.models import AnalysisJob, Team, Upload, User
from app.models.upload import PART_BYTES
from app.schemas import (
    TeamRef,
    UploadCreate,
    UploadList,
    UploadMap,
    UploadPartAck,
    UploadPlayer,
    UploadRead,
    UploadSides,
)
from app.services import mn, uploads

router = APIRouter(prefix="/uploads", tags=["uploads"])
LIST_LIMIT = 100


def _get(db, user: User, public_id: uuid.UUID) -> Upload:
    found = db.scalar(
        select(Upload).where(
            Upload.public_id == public_id, Upload.workspace_id == user.workspace_id
        )
    )
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such upload")
    return found


def _ref(db, team_id: int | None) -> TeamRef | None:
    team = db.get(Team, team_id) if team_id else None
    return TeamRef(id=team.id, name=team.name) if team else None


def _read(db, u: Upload) -> UploadRead:
    mine = {str(s) for s in uploads.known_players(db, u.my_team_id)}
    theirs = {str(s) for s in uploads.known_players(db, u.opponent_id)} - mine

    def player(p: dict) -> UploadPlayer:
        sid = p["steamid"]
        known = "mine" if sid in mine else "theirs" if sid in theirs else ""
        return UploadPlayer(steamid=sid, name=p.get("name") or "", known=known)

    job_id = db.scalar(select(AnalysisJob.public_id).where(AnalysisJob.id == u.job_id))
    return UploadRead(
        id=u.public_id,
        created_at=u.created_at,
        kind=u.kind,
        played_on=u.played_on,
        my_team=_ref(db, u.my_team_id) or TeamRef(id=u.my_team_id, name="?"),
        opponent=_ref(db, u.opponent_id),
        opponent_name=u.opponent_name,
        note=u.note,
        filename=u.filename,
        size_bytes=u.size_bytes,
        parts_total=u.parts_total,
        part_bytes=PART_BYTES,
        received=uploads.received(db, u)[0],
        status=u.status,
        error=u.error,
        job_id=job_id,
        match_id=u.match_id,
        maps=[
            UploadMap(
                map_number=e["map_number"],
                map=mn.game_map(e["map"]),
                mine=e.get("mine"),
                assigned=bool(e.get("assigned")),
                groups=[[player(p) for p in g] for g in e.get("groups") or []],
            )
            for e in u.maps or []
        ],
    )


def _fail(exc: uploads.UploadError):
    raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None


@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: UploadCreate, db: DbSession, user: StaffUser) -> UploadRead:
    try:
        u = uploads.create(db, user, **body.model_dump())
    except uploads.UploadError as exc:
        _fail(exc)
    return _read(db, u)


@router.put("/{public_id}/parts/{n}")
def put_part(
    public_id: uuid.UUID,
    n: int,
    db: DbSession,
    user: StaffUser,
    data: Annotated[UploadFile, File()],
) -> UploadPartAck:
    """One part of the file (0-based), at most ``part_bytes``; sending it again replaces it."""
    u = _get(db, user, public_id)
    chunk = data.file.read(PART_BYTES + 1)
    try:
        count = uploads.put_part(db, u, n, chunk)
    except uploads.UploadError as exc:
        _fail(exc)
    return UploadPartAck(received=count, parts_total=u.parts_total)


@router.post("/{public_id}/complete")
def complete(public_id: uuid.UUID, db: DbSession, user: StaffUser) -> UploadRead:
    u = _get(db, user, public_id)
    try:
        uploads.complete(db, u, user)
    except uploads.UploadError as exc:
        _fail(exc)
    db.refresh(u)
    return _read(db, u)


@router.post("/{public_id}/sides")
def sides(public_id: uuid.UUID, body: UploadSides, db: DbSession, user: StaffUser) -> UploadRead:
    """Staff say which five are ours on one Map; it is stored again with the Teams."""
    u = _get(db, user, public_id)
    try:
        uploads.answer(db, u, body.map_number, body.mine, user)
    except uploads.UploadError as exc:
        _fail(exc)
    db.refresh(u)
    return _read(db, u)


@router.get("")
def index(db: DbSession, user: StaffUser) -> UploadList:
    rows = db.scalars(
        select(Upload)
        .where(Upload.workspace_id == user.workspace_id)
        .order_by(Upload.created_at.desc())
        .limit(LIST_LIMIT)
    ).all()
    return UploadList(uploads=[_read(db, u) for u in rows])


@router.get("/{public_id}")
def detail(public_id: uuid.UUID, db: DbSession, user: StaffUser) -> UploadRead:
    return _read(db, _get(db, user, public_id))
