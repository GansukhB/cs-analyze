"""The Stratbook (CONTEXT.md: Stratbook, Strat; docs/plans/08 SB-1, SB-7).

Strats belong to the Workspace and to one of its my teams. Only Staff write
them; a Player login reads the active ones shared with the team. Every read,
print and change is logged, and every save keeps the Strat as it was before.
"""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession, StaffUser
from app.models import (
    Match,
    MatchMap,
    Strat,
    StratEvent,
    StratExample,
    StratStatus,
    StratVersion,
    StratVisibility,
    Team,
    User,
    WorkspaceTeam,
)
from app.routers.matches import _map
from app.schemas import (
    StratCoverage,
    StratElsewhere,
    StratEventRead,
    StratExampleRead,
    StratExampleWrite,
    StratRead,
    StratReport,
    StratRow,
    StratVersionRead,
    StratWrite,
    TeamRef,
)
from app.services import audit_log, dbctx, map_pool, scope, strat_match

router = APIRouter(prefix="/strats", tags=["strats"])
FIELDS = ("map_name", "side", "name", "kind", "description", "timings", "variations", "calls",
          "status", "visibility")  # fmt: skip


def _visible(user: User):
    query = select(Strat).where(Strat.workspace_id == user.workspace_id)
    if not user.is_staff:
        query = query.where(
            Strat.visibility == StratVisibility.TEAM, Strat.status == StratStatus.ACTIVE
        )
    return query


def _get(db, user: User, strat_id: int) -> Strat:
    found = db.scalar(_visible(user).where(Strat.id == strat_id))
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such strat")
    return found


def _log(db, strat: Strat, user: User, action: str) -> None:
    db.add(StratEvent(strat_id=strat.id, user_id=user.id, action=action))


def _counts(db, ids: list[int]) -> Counter:
    return Counter(
        db.scalars(select(StratExample.strat_id).where(StratExample.strat_id.in_(ids))).all()
    )


def _row(db, strat: Strat, examples: int) -> dict:
    team = db.get(Team, strat.team_id)
    return {
        "id": strat.id,
        "team": TeamRef(id=team.id, name=team.name),
        **{
            k: getattr(strat, k)
            for k in ("map_name", "side", "name", "kind", "status", "visibility")
        },  # fmt: skip
        "examples": examples,
        "updated_at": strat.updated_at,
    }


def _read(db, strat: Strat, user: User) -> StratRead:
    scope.allow_scrims(db)
    with dbctx.using(db):
        return _read_bound(db, strat, user)


def _read_bound(db, strat: Strat, user: User) -> StratRead:
    examples = []
    for e in db.scalars(
        select(StratExample)
        .where(StratExample.strat_id == strat.id, StratExample.source != "dismissed")
        .order_by(StratExample.id)
    ):
        mm = db.get(MatchMap, e.match_map_id)
        if mm is None:
            continue
        match = db.get(Match, mm.match_id)
        teams = " vs ".join(t.name for t in (match.team1, match.team2) if t) if match else ""
        examples.append(
            StratExampleRead(
                id=e.id, match_id=mm.match_id, map_number=mm.map_number, round=e.round,
                label=f"{teams or (match.opponent_label if match else '')} · R{e.round}",
                source=e.source, confirmed=e.confirmed, note=e.note,
            )
        )  # fmt: skip
    versions = len(
        db.scalars(select(StratVersion.id).where(StratVersion.strat_id == strat.id)).all()
    )
    return StratRead(
        **_row(db, strat, len(examples)),
        description=strat.description,
        roles=strat.roles or [],
        grenades=strat.grenades or [],
        timings=strat.timings,
        variations=strat.variations,
        calls=strat.calls,
        tags=strat.tags or [],
        examples_list=examples,
        versions=versions,
        can_edit=user.is_staff,
        report=StratReport(**strat_match.report(strat)),
    )


def _my_team(db, user: User, team_id: int) -> None:
    mine = set(
        db.scalars(
            select(WorkspaceTeam.team_id).where(WorkspaceTeam.workspace_id == user.workspace_id)
        )
    )
    if team_id not in mine:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A Strat is for one of our teams")


def _snapshot(strat: Strat) -> dict:
    return {
        **{k: getattr(strat, k) for k in FIELDS},
        "team_id": strat.team_id,
        "roles": strat.roles,
        "grenades": strat.grenades,
        "tags": strat.tags,
    }


@router.get("")
def list_strats(
    db: DbSession, user: CurrentUser, team_id: int | None = None, map_name: str | None = None
) -> list[StratRow]:
    query = _visible(user)
    if team_id:
        query = query.where(Strat.team_id == team_id)
    if map_name:
        query = query.where(Strat.map_name == map_name)
    rows = db.scalars(query.order_by(Strat.map_name, Strat.side, Strat.name)).all()
    counts = _counts(db, [s.id for s in rows])
    return [StratRow(**_row(db, s, counts[s.id])) for s in rows]


@router.get("/maps")
def strat_maps(db: DbSession, _: CurrentUser) -> list[str]:
    """The Active Duty Maps, the Stratbook's rows."""
    with dbctx.using(db):
        return list(map_pool.active_duty())


@router.post("", status_code=status.HTTP_201_CREATED)
def create_strat(body: StratWrite, db: DbSession, user: StaffUser) -> StratRead:
    _my_team(db, user, body.team_id)
    strat = Strat(workspace_id=user.workspace_id, created_by_id=user.id, team_id=body.team_id)
    _apply(strat, body)
    db.add(strat)
    db.flush()
    seen = set()
    for e in body.examples:
        try:
            match_map = _map(db, e.match_id, e.map_number, user)
        except HTTPException:
            continue  # a Round this login can't see is left out, not an error
        if (match_map.id, e.round) not in seen:
            seen.add((match_map.id, e.round))
            db.add(StratExample(strat_id=strat.id, match_map_id=match_map.id, round=e.round,
                                source="setplay", note=e.note.strip()))  # fmt: skip
    _log(db, strat, user, "edit")
    db.commit()
    return _read(db, strat, user)


def _apply(strat: Strat, body: StratWrite) -> None:
    for k in FIELDS:
        setattr(strat, k, getattr(body, k))
    strat.team_id = body.team_id
    strat.roles = [r.model_dump() for r in body.roles]
    strat.grenades = [g.model_dump() for g in body.grenades]
    strat.tags = [t.strip() for t in body.tags if t.strip()]


@router.get("/{strat_id}")
def get_strat(strat_id: int, db: DbSession, user: CurrentUser) -> StratRead:
    strat = _get(db, user, strat_id)
    _log(db, strat, user, "view")
    db.commit()
    return _read(db, strat, user)


@router.put("/{strat_id}")
def update_strat(strat_id: int, body: StratWrite, db: DbSession, user: StaffUser) -> StratRead:
    strat = _get(db, user, strat_id)
    _my_team(db, user, body.team_id)
    db.add(StratVersion(strat_id=strat.id, payload=_snapshot(strat), created_by_id=user.id))
    shared = body.visibility == StratVisibility.TEAM and strat.visibility != StratVisibility.TEAM
    _apply(strat, body)
    _log(db, strat, user, "share" if shared else "edit")
    db.commit()
    return _read(db, strat, user)


@router.delete("/{strat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_strat(strat_id: int, db: DbSession, user: StaffUser) -> None:
    strat = _get(db, user, strat_id)
    audit_log.record(db, user, "strat.delete", strat.name, map=strat.map_name, side=strat.side)
    db.delete(strat)
    db.commit()


@router.get("/{strat_id}/elsewhere")
def strat_elsewhere(strat_id: int, db: DbSession, user: StaffUser) -> StratElsewhere:
    """SB-5: the other Teams whose Rounds played this Strat's grenades, and how they did."""
    strat = _get(db, user, strat_id)
    with dbctx.using(db):
        return StratElsewhere(**strat_match.elsewhere(strat))


@router.post("/{strat_id}/print", status_code=status.HTTP_204_NO_CONTENT)
def printed(strat_id: int, db: DbSession, user: CurrentUser) -> None:
    """Logs a print (SB-7): the page calls it before it prints."""
    _log(db, _get(db, user, strat_id), user, "print")
    db.commit()


@router.post("/{strat_id}/examples", status_code=status.HTTP_201_CREATED)
def add_example(
    strat_id: int, body: StratExampleWrite, db: DbSession, user: StaffUser
) -> StratRead:
    strat = _get(db, user, strat_id)
    match_map = _map(db, body.match_id, body.map_number, user)
    exists = db.scalar(
        select(StratExample).where(
            StratExample.strat_id == strat.id,
            StratExample.match_map_id == match_map.id,
            StratExample.round == body.round,
        )
    )
    if exists is None:
        db.add(StratExample(strat_id=strat.id, match_map_id=match_map.id, round=body.round,
                            note=body.note.strip()))  # fmt: skip
        _log(db, strat, user, "edit")
        db.commit()
    return _read(db, strat, user)


def _example(db, strat: Strat, example_id: int) -> StratExample:
    example = db.get(StratExample, example_id)
    if example is None or example.strat_id != strat.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such example")
    return example


@router.delete("/{strat_id}/examples/{example_id}")
def drop_example(strat_id: int, example_id: int, db: DbSession, user: StaffUser) -> StratRead:
    """A Round picked by hand goes; one that was found stays, dismissed, so the
    next search does not find it again (SB-4)."""
    strat = _get(db, user, strat_id)
    example = _example(db, strat, example_id)
    if example.source == "auto":
        example.source = "dismissed"
    else:
        db.delete(example)
    _log(db, strat, user, "edit")
    db.commit()
    return _read(db, strat, user)


@router.post("/{strat_id}/examples/{example_id}/confirm")
def confirm_example(strat_id: int, example_id: int, db: DbSession, user: StaffUser) -> StratRead:
    strat = _get(db, user, strat_id)
    _example(db, strat, example_id).confirmed = True
    _log(db, strat, user, "edit")
    db.commit()
    return _read(db, strat, user)


@router.post("/{strat_id}/match")
def match_rounds(strat_id: int, db: DbSession, user: StaffUser) -> StratRead:
    """Find the Rounds that played the Strat (SB-4): kept as examples to confirm."""
    strat = _get(db, user, strat_id)
    with dbctx.using(db):
        strat_match.refresh(strat)
    db.commit()
    return _read(db, strat, user)


@router.get("/coverage/{team_id}")
def coverage(team_id: int, db: DbSession, user: StaffUser) -> dict[str, StratCoverage]:
    """Per Map: the Team's active Strats and how many were played in the last 30 days."""
    _my_team(db, user, team_id)
    with dbctx.using(db):
        return {
            k: StratCoverage(**v)
            for k, v in strat_match.coverage(user.workspace_id, team_id).items()
        }


@router.get("/{strat_id}/versions")
def versions(strat_id: int, db: DbSession, user: StaffUser) -> list[StratVersionRead]:
    strat = _get(db, user, strat_id)
    rows = db.scalars(
        select(StratVersion)
        .where(StratVersion.strat_id == strat.id)
        .order_by(StratVersion.id.desc())
    ).all()
    names = _names(db, {v.created_by_id for v in rows})
    return [
        StratVersionRead(
            id=v.id,
            created_by=names.get(v.created_by_id, ""),
            created_at=v.created_at,
            payload=v.payload,
        )  # fmt: skip
        for v in rows
    ]


@router.get("/{strat_id}/events")
def events(strat_id: int, db: DbSession, user: StaffUser) -> list[StratEventRead]:
    """Who read, printed or changed it (SB-7), newest first."""
    strat = _get(db, user, strat_id)
    rows = db.scalars(
        select(StratEvent)
        .where(StratEvent.strat_id == strat.id)
        .order_by(StratEvent.id.desc())
        .limit(200)
    ).all()
    names = _names(db, {e.user_id for e in rows})
    return [
        StratEventRead(user=names.get(e.user_id, ""), action=e.action, at=e.created_at)
        for e in rows
    ]


def _names(db, ids: set) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.username).where(User.id.in_(ids))).all())
