"""Upcoming matches (CONTEXT.md): what Staff enter, with their checklist and
the counters picked for them (grilling Q3, Q8)."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.deps import DbSession, StaffUser
from app.models import UpcomingMatch, User
from app.routers.v2.common import my_team, team
from app.schemas_v2 import UpcomingList, UpcomingPatch, UpcomingRead, UpcomingWrite
from app.services import dbctx, upcoming

router = APIRouter()


def _own(db: Session, user: User, upcoming_id: int) -> UpcomingMatch:
    found = db.get(UpcomingMatch, upcoming_id)
    if found is None or found.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such upcoming match")
    return found


def _read(db: Session, u: UpcomingMatch) -> UpcomingRead:
    with dbctx.using(db):
        return UpcomingRead(**upcoming.read(u))


@router.get("/upcoming")
def list_upcoming(
    db: DbSession, user: StaffUser, team_id: int | None = None, past: bool = False
) -> UpcomingList:
    with dbctx.using(db):
        found = upcoming.listing(user.workspace_id, team_id, past=past)
        for u in found:
            upcoming.link(u)
        db.commit()
        return UpcomingList(upcoming=[UpcomingRead(**upcoming.read(u)) for u in found])


@router.post("/upcoming", status_code=status.HTTP_201_CREATED)
def create_upcoming(body: UpcomingWrite, db: DbSession, user: StaffUser) -> UpcomingRead:
    my_team(db, user, body.team_id)
    team(db, body.opponent_id)
    if body.opponent_id == body.team_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A team can't play itself")
    u = UpcomingMatch(
        workspace_id=user.workspace_id,
        team_id=body.team_id,
        opponent_id=body.opponent_id,
        starts_at=upcoming.naive_utc(body.starts_at),
        best_of=body.best_of,
        tournament=body.tournament.strip(),
        checklist=[{"text": t, "done": False} for t in upcoming.DEFAULT_CHECKLIST],
        counters=[],
        created_by_id=user.id,
    )
    db.add(u)
    db.commit()
    return _read(db, u)


@router.patch("/upcoming/{upcoming_id}")
def patch_upcoming(
    upcoming_id: int, body: UpcomingPatch, db: DbSession, user: StaffUser
) -> UpcomingRead:
    u = _own(db, user, upcoming_id)
    if body.starts_at is not None:
        u.starts_at = upcoming.naive_utc(body.starts_at)
        u.match_id = None  # read again around the new start
    if body.best_of is not None:
        u.best_of = body.best_of
    if body.tournament is not None:
        u.tournament = body.tournament.strip()
    if body.checklist is not None:
        u.checklist = [i.model_dump() for i in body.checklist]
    if body.counters is not None:
        u.counters = [c.model_dump() for c in body.counters]
    db.commit()
    return _read(db, u)


@router.delete("/upcoming/{upcoming_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upcoming(upcoming_id: int, db: DbSession, user: StaffUser) -> Response:
    db.delete(_own(db, user, upcoming_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
