"""Briefings (docs/plans/01 WS-5): Staff freeze lines of a Game Plan with notes
and share them; Players of the Workspace read what was shared."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import get_settings
from app.deps import CurrentUser, DbSession, StaffUser
from app.models import Briefing, Match, Strat, StratStatus, StratVisibility, Team, User
from app.models.base import utcnow
from app.routers import assistant as assistant_router
from app.routers import gameplan as gp
from app.schemas import (
    BriefingCreate,
    BriefingDraft,
    BriefingList,
    BriefingRead,
    BriefingRow,
    PlanCheck,
    TeamRef,
)
from app.services import (
    assistant,
    audit_log,
    briefing_draft,
    briefings,
    dbctx,
    decision,
    drawn_notes,
    forecast,
    gameplan_view,
    lineup,
    mn,
    plan_check,
    playbook_notes,
    scope,
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


def _strats(db, workspace_id: int, team_id: int, map_name: str, ids: list[int]) -> list[dict]:
    """SB-6: the picked Strats as the Briefing names them; 400 for one that is not
    the my team's, on this Map, active and shared (its readers could not open it)."""
    out = []
    for strat_id in dict.fromkeys(ids):
        strat = db.get(Strat, strat_id)
        if (
            strat is None or strat.workspace_id != workspace_id or strat.team_id != team_id
            or strat.map_name != map_name or strat.status != StratStatus.ACTIVE
            or strat.visibility != StratVisibility.TEAM
        ):  # fmt: skip
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Strat {strat_id} is not an active shared one"
            )
        out.append({"id": strat.id, "name": strat.name, "side": strat.side, "kind": strat.kind})
    return out


def _frozen(db, body, my_team, opponent, my_five, their_five, workspace_id: int):
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
            # GP-13: each habit line takes Staff's note on it, theirs or our own.
            for team_id in (opponent.id, my_team.id):
                written = playbook_notes.notes(db, workspace_id, team_id, pick.map)
                for item in items:
                    note = written.get(item.get("key") or "")
                    if note and not item.get("note"):
                        item["note"] = note["text"]
            strats = _strats(db, workspace_id, my_team.id, pick.map, pick.strats)
            drawings = drawn_notes.freeze(workspace_id, pick.map, pick.drawings)
            if items or strats or drawings or pick.note.strip():
                maps.append(
                    {"map": pick.map, "label": panel.get("label") or pick.map,
                     "note": pick.note.strip(), "items": items, "strats": strats,
                     "drawings": drawings}
                )  # fmt: skip
    except (briefings.BriefingError, ValueError) as exc:
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
        maps, stamp = _frozen(db, body, my_team, opponent, my_five, their_five,
                              user.workspace_id)  # fmt: skip
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
        maps, _stamp = _frozen(db, body, my_team, opponent, my_five, their_five,
                               user.workspace_id)  # fmt: skip
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


@router.get("/{public_id}/check")
def check(
    public_id: uuid.UUID, db: DbSession, user: StaffUser, match_id: int | None = None
) -> PlanCheck:
    """After the Match: each habit the Briefing named against the opponent's
    Rounds, the Maps played and the Forecast (GP-8)."""
    b = _get(db, user, public_id)
    scope.allow_scrims(db)
    match = db.get(Match, match_id) if match_id else None
    pair = {b.my_team_id, b.opponent_id}
    if match_id and (match is None or {match.team1_id, match.team2_id} != pair):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a Match between these Teams")
    with dbctx.using(db):
        return PlanCheck(**plan_check.check(b, match))


@router.post("/{public_id}/share")
def share(public_id: uuid.UUID, db: DbSession, user: StaffUser) -> BriefingRow:
    b = _get(db, user, public_id)
    if b.shared_at is None:
        audit_log.record(db, user, "briefing.share", b.title)
    b.shared_at = b.shared_at or utcnow()
    db.commit()
    return BriefingRow(**_row(db, b))


@router.delete("/{public_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(public_id: uuid.UUID, db: DbSession, user: StaffUser) -> None:
    b = _get(db, user, public_id)
    audit_log.record(db, user, "briefing.delete", b.title, shared=b.shared_at is not None)
    db.delete(b)
    db.commit()
