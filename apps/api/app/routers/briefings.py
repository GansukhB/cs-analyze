"""Briefings (docs/plans/01 WS-5): Staff freeze lines of a Game Plan with notes
and share them; Players of the Workspace read what was shared."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import get_settings
from app.deps import CurrentUser, DbSession, StaffUser
from app.models import Briefing, Team, User
from app.models.base import utcnow
from app.routers import assistant as assistant_router
from app.routers import gameplan as gp
from app.schemas import (
    BriefingCreate,
    BriefingDraft,
    BriefingList,
    BriefingRead,
    BriefingRow,
    TeamRef,
)
from app.services import (
    assistant,
    briefing_draft,
    briefings,
    dbctx,
    decision,
    forecast,
    gameplan_view,
    lineup,
    mn,
)

router = APIRouter(prefix="/briefings", tags=["briefings"])
LIST_LIMIT = 100


def _ref(db, team_id: int) -> TeamRef:
    team = db.get(Team, team_id)
    return TeamRef(id=team_id, name=team.name if team else "?")


def _row(db, b: Briefing) -> dict:
    by = db.get(User, b.created_by_id) if b.created_by_id else None
    return {
        "id": b.public_id,
        "title": b.title,
        "my_team": _ref(db, b.my_team_id),
        "opponent": _ref(db, b.opponent_id),
        "created_at": b.created_at,
        "shared_at": b.shared_at,
        "created_by": by.username if by else "",
    }


def _visible(user: User):
    query = select(Briefing).where(Briefing.workspace_id == user.workspace_id)
    return query if user.is_staff else query.where(Briefing.shared_at.is_not(None))


def _get(db, user: User, public_id: uuid.UUID) -> Briefing:
    found = db.scalar(_visible(user).where(Briefing.public_id == public_id))
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such briefing")
    return found


def _frozen(db, body, my_team, opponent, my_five, their_five) -> tuple[list[dict], str]:
    """Each Map's picked lines frozen from its Playbook as it reads now, and the
    stamp; 409 when a parse moved the Game Plan since the page loaded."""
    stamp = gameplan_view.stamp()
    if body.stamp and body.stamp != stamp:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The Game Plan changed since this page loaded: reload it"
        )
    maps = []
    try:
        for pick in body.maps:
            panel, _hit = gp.playbook_data(
                db, my_team, opponent, my_five, their_five, pick.map, stamp
            )
            items = [briefings.freeze(panel, path) for path in pick.picks]
            if items or pick.note.strip():
                maps.append(
                    {"map": pick.map, "label": panel.get("label") or pick.map,
                     "note": pick.note.strip(), "items": items}
                )  # fmt: skip
    except briefings.BriefingError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return maps, stamp


def _forecast_view(my_team, opponent, my_five, their_five) -> dict:
    built = forecast.build(
        my_team,
        opponent,
        my_lineup=[p.name for p in my_five] or None,
        their_lineup=[p.name for p in their_five] or None,
    )
    return decision._forecast(built, my_team, opponent)


@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: BriefingCreate, db: DbSession, user: StaffUser) -> BriefingRead:
    """Freeze the picked lines of each Map's Playbook as they read now."""
    my_team, opponent = gp._fixture(db, body.my_team_id, body.opponent_id)
    my_five, their_five = gp._lineups(
        db, my_team, opponent, ",".join(body.my_lineup), ",".join(body.their_lineup)
    )
    with dbctx.using(db), lineup.using({my_team.id: my_five, opponent.id: their_five}):
        maps, stamp = _frozen(db, body, my_team, opponent, my_five, their_five)
        content = {
            "note": body.note.strip(),
            "lineups": {
                "mine": [p.name for p in my_five] or [p.name for p in lineup.latest_five(my_team)],
                "theirs": [p.name for p in their_five]
                or [p.name for p in lineup.latest_five(opponent)],
            },
            "maps": maps,
            "stamp": stamp,
        }
        if body.include_forecast:
            content["forecast"] = _forecast_view(my_team, opponent, my_five, their_five)
    row = Briefing(
        workspace_id=user.workspace_id,
        my_team_id=my_team.id,
        opponent_id=opponent.id,
        my_lineup=[str(p.steamid) for p in my_five],
        their_lineup=[str(p.steamid) for p in their_five],
        title=body.title.strip(),
        payload=briefings.pack(content),
        include_forecast=body.include_forecast,
        created_by_id=user.id,
        shared_at=utcnow() if body.share else None,
    )
    db.add(row)
    db.commit()
    return BriefingRead(**_row(db, row), include_forecast=row.include_forecast, content=content)


@router.post("/draft")
def draft(body: BriefingCreate, db: DbSession, user: StaffUser) -> BriefingDraft:
    """The Assistant's draft of the notes for the picked lines (AS-6): nothing is
    saved; Staff edit it. Numbers the lines don't hold are listed to check."""
    if not assistant.is_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, mn.ASSISTANT_NOT_CONFIGURED)
    cost, _chars = assistant_router.spent_today(db, user)
    if cost >= get_settings().assistant_daily_usd:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, mn.ASSISTANT_LIMIT)
    my_team, opponent = gp._fixture(db, body.my_team_id, body.opponent_id)
    my_five, their_five = gp._lineups(
        db, my_team, opponent, ",".join(body.my_lineup), ",".join(body.their_lineup)
    )
    with dbctx.using(db), lineup.using({my_team.id: my_five, opponent.id: their_five}):
        maps, _stamp = _frozen(db, body, my_team, opponent, my_five, their_five)
        line = ""
        if body.include_forecast:
            series = _forecast_view(my_team, opponent, my_five, their_five)["series"]
            line = " ".join(f"{s['format']}: ~{s['pct']}% ({s['word']})." for s in series)
    maps = [m for m in maps if m["items"]]
    if not maps:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick some lines first")
    try:
        written, usage = briefing_draft.draft(my_team.name, opponent.name, maps, line)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"The draft came back unreadable: {exc}"
        ) from None
    assistant_router._record(user.id, user.workspace_id, usage)
    return BriefingDraft(**written, cost_usd=round(usage.cost_usd(), 4))


@router.get("")
def index(db: DbSession, user: CurrentUser) -> BriefingList:
    """Staff see every Briefing of the Workspace; a Player, the shared ones."""
    rows = db.scalars(_visible(user).order_by(Briefing.created_at.desc()).limit(LIST_LIMIT)).all()
    return BriefingList(briefings=[BriefingRow(**_row(db, b)) for b in rows])


@router.get("/{public_id}")
def detail(public_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BriefingRead:
    b = _get(db, user, public_id)
    return BriefingRead(
        **_row(db, b), include_forecast=b.include_forecast, content=briefings.unpack(b.payload)
    )


@router.post("/{public_id}/share")
def share(public_id: uuid.UUID, db: DbSession, user: StaffUser) -> BriefingRow:
    b = _get(db, user, public_id)
    b.shared_at = b.shared_at or utcnow()
    db.commit()
    return BriefingRow(**_row(db, b))


@router.delete("/{public_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(public_id: uuid.UUID, db: DbSession, user: StaffUser) -> None:
    db.delete(_get(db, user, public_id))
    db.commit()
