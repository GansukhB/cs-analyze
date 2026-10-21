"""Staff's notes on a Review, the Findings they dispute, and Playlists
(docs/plans/07 RV-7).

Notes belong to the Workspace. A Player sees the notes that name him, never a
dispute, and the Playlists Staff shared. How often each Finding code is
disputed is on the Workspace page."""

from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession, StaffUser
from app.models import Match, MatchMap, NoteKind, Playlist, ReviewNote, Team, User
from app.routers.matches import _map
from app.schemas import (
    DisputeRate,
    NoteCreate,
    NoteList,
    NoteRead,
    PlaybookNoteRead,
    PlaybookNoteWrite,
    PlaylistItemRead,
    PlaylistRead,
    PlaylistSummary,
    PlaylistWrite,
)
from app.services import audit_log, dbctx, mn, playbook_notes, review, review_pool, scope

router = APIRouter(tags=["notes"])
LIMIT = 50


def _read(db, n: ReviewNote) -> NoteRead:
    mm = db.get(MatchMap, n.match_map_id)
    by = db.get(User, n.created_by_id) if n.created_by_id else None
    return NoteRead(
        id=n.id,
        kind=n.kind,
        match_id=mm.match_id if mm else 0,
        map_number=mm.map_number if mm else 0,
        round=n.round,
        t=n.t,
        code=n.code,
        sids=list(n.sids or []),
        text=n.text,
        tag=n.tag,
        reason=n.reason,
        drawing=n.drawing,
        created_by=by.username if by else "",
        created_at=n.created_at,
    )


def _mine(user: User) -> str | None:
    return str(user.player.steamid) if user.player else None


@router.get("/matches/{match_id}/maps/{map_number}/notes")
def map_notes(match_id: int, map_number: int, db: DbSession, user: CurrentUser) -> NoteList:
    match_map = _map(db, match_id, map_number, user)
    rows = db.scalars(
        select(ReviewNote)
        .where(
            ReviewNote.workspace_id == user.workspace_id, ReviewNote.match_map_id == match_map.id
        )
        .order_by(ReviewNote.round, ReviewNote.t, ReviewNote.id)
    ).all()
    if not user.is_staff:
        sid = _mine(user)
        rows = [n for n in rows if n.kind == NoteKind.NOTE and sid in (n.sids or [])]
    return NoteList(notes=[_read(db, n) for n in rows], reasons=mn.DISPUTE_REASONS)


@router.post("/matches/{match_id}/maps/{map_number}/notes", status_code=status.HTTP_201_CREATED)
def add_note(
    match_id: int, map_number: int, body: NoteCreate, db: DbSession, user: StaffUser
) -> NoteRead:
    match_map = _map(db, match_id, map_number, user)
    if body.kind == NoteKind.DISPUTE:
        if body.code not in review.CODE_KIND or body.reason not in mn.DISPUTE_REASONS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "A dispute names a Finding and a reason"
            )
    elif not body.text.strip() and not body.drawing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A note needs its text or a drawing")
    note = ReviewNote(
        workspace_id=user.workspace_id,
        match_map_id=match_map.id,
        kind=body.kind,
        round=body.round,
        t=body.t,
        code=body.code,
        sids=[s for s in body.sids if s.isdigit()],
        text=body.text.strip(),
        tag=body.tag.strip(),
        reason=body.reason,
        drawing=[d.model_dump() for d in body.drawing] if body.drawing else None,
        created_by_id=user.id,
    )
    db.add(note)
    db.commit()
    return _read(db, note)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: int, db: DbSession, user: StaffUser) -> None:
    note = db.get(ReviewNote, note_id)
    if note is None or note.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such note")
    db.delete(note)
    db.commit()


@router.get("/me/notes")
def my_notes(db: DbSession, user: CurrentUser) -> list[NoteRead]:
    """The notes Staff left that name this Player login's Player, newest first."""
    sid = _mine(user)
    if sid is None:
        return []
    rows = db.scalars(
        select(ReviewNote)
        .where(ReviewNote.workspace_id == user.workspace_id, ReviewNote.kind == NoteKind.NOTE)
        .order_by(ReviewNote.created_at.desc())
        .limit(LIMIT * 4)
    ).all()
    return [_read(db, n) for n in rows if sid in (n.sids or [])][:LIMIT]


@router.get("/workspace/disputes")
def dispute_rates(db: DbSession, user: StaffUser) -> list[DisputeRate]:
    """How often each Finding code is disputed against how often it is found."""
    rows = db.scalars(
        select(ReviewNote).where(
            ReviewNote.workspace_id == user.workspace_id, ReviewNote.kind == NoteKind.DISPUTE
        )
    ).all()
    disputes: Counter = Counter(n.code for n in rows)
    reasons: dict[str, Counter] = defaultdict(Counter)
    for n in rows:
        reasons[n.code][n.reason] += 1
    with dbctx.using(db):
        found: Counter = Counter()
        for t in review_pool.data().tallies:
            for code, events in t.codes.items():
                found[code] += len(events)
    out = [
        DisputeRate(
            code=code,
            label=mn.REVIEW_CODE.get(code, code),
            disputes=n,
            findings=found.get(code, 0),
            rate=round(n / found[code], 4) if found.get(code) else None,
            reasons=dict(reasons[code]),
        )
        for code, n in disputes.items()
    ]
    return sorted(out, key=lambda r: -(r.rate or 0))


# -- Playlists ----------------------------------------------------------------------
def _playlist(db, playlist_id: int, user: User) -> Playlist:
    found = db.get(Playlist, playlist_id)
    if found is None or found.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such playlist")
    if not user.is_staff and not found.shared:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such playlist")
    return found


def _summary(db, p: Playlist) -> dict:
    by = db.get(User, p.created_by_id) if p.created_by_id else None
    return {
        "id": p.id,
        "title": p.title,
        "rounds": len(p.items or []),
        "shared": p.shared,
        "created_by": by.username if by else "",
        "updated_at": p.updated_at,
    }


def _labels(db, items: list[dict]) -> dict[tuple[int, int], str]:
    scope.allow_scrims(db)
    out = {}
    for match_id in {i["match_id"] for i in items}:
        match = db.get(Match, match_id)
        if match is None:
            continue
        teams = (
            " vs ".join(t.name for t in (match.team1, match.team2) if t is not None)
            or match.opponent_label
        )
        for mm in match.map_results:
            game = mn.game_map(mm.game_map.name if mm.game_map else "")
            out[(match_id, mm.map_number)] = f"{teams} · {game}"
    return out


@router.get("/playlists")
def list_playlists(db: DbSession, user: CurrentUser) -> list[PlaylistSummary]:
    query = select(Playlist).where(Playlist.workspace_id == user.workspace_id)
    if not user.is_staff:
        query = query.where(Playlist.shared.is_(True))
    rows = db.scalars(query.order_by(Playlist.updated_at.desc())).all()
    return [PlaylistSummary(**_summary(db, p)) for p in rows]


@router.get("/playlists/{playlist_id}")
def get_playlist(playlist_id: int, db: DbSession, user: CurrentUser) -> PlaylistRead:
    p = _playlist(db, playlist_id, user)
    labels = _labels(db, p.items or [])
    items = [
        PlaylistItemRead(**i, label=labels.get((i["match_id"], i["map_number"]), "?"))
        for i in p.items or []
        if (i["match_id"], i["map_number"]) in labels
    ]
    return PlaylistRead(**_summary(db, p), note=p.note, items=items)


def _write(db, p: Playlist, body: PlaylistWrite, user: User) -> None:
    for item in body.items:
        _map(db, item.match_id, item.map_number, user)  # 404 on a Map he can't see
    p.title = body.title.strip()
    p.note = body.note
    p.items = [i.model_dump() for i in body.items]
    p.shared = body.shared


@router.post("/playlists", status_code=status.HTTP_201_CREATED)
def create_playlist(body: PlaylistWrite, db: DbSession, user: StaffUser) -> PlaylistRead:
    p = Playlist(workspace_id=user.workspace_id, created_by_id=user.id, title="")
    _write(db, p, body, user)
    db.add(p)
    db.commit()
    return get_playlist(p.id, db, user)


@router.put("/playlists/{playlist_id}")
def update_playlist(
    playlist_id: int, body: PlaylistWrite, db: DbSession, user: StaffUser
) -> PlaylistRead:
    p = _playlist(db, playlist_id, user)
    _write(db, p, body, user)
    db.commit()
    return get_playlist(p.id, db, user)


@router.delete("/playlists/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_playlist(playlist_id: int, db: DbSession, user: StaffUser) -> None:
    playlist = _playlist(db, playlist_id, user)
    audit_log.record(db, user, "playlist.delete", playlist.title)
    db.delete(playlist)
    db.commit()


# -- Staff's notes on Playbook lines (docs/plans/06 GP-13) ---------------------------
@router.get("/playbook-notes")
def playbook_note_list(
    team_id: int, map_name: str, db: DbSession, user: StaffUser
) -> dict[str, PlaybookNoteRead]:
    """``{habit key: note}`` for one Team's Playbook on one Map."""
    found = playbook_notes.notes(db, user.workspace_id, team_id, map_name)
    return {k: PlaybookNoteRead(**v) for k, v in found.items()}


@router.put("/playbook-notes", status_code=status.HTTP_204_NO_CONTENT)
def playbook_note_put(body: PlaybookNoteWrite, db: DbSession, user: StaffUser) -> None:
    """Write or change a note on a habit line; empty text removes it."""
    if db.get(Team, body.team_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team")
    playbook_notes.put(db, user, body.team_id, body.map_name, body.key, body.text)
    db.commit()
