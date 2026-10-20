"""Forecasts kept and graded (docs/plans/03 FC-4): Staff make one from a Game Plan,
and every one is graded once its series is played. Scoped to the Workspace."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DbSession, StaffUser
from app.models import Forecast, Team
from app.schemas import ForecastCreate, ForecastList, ForecastRead, ForecastSummary, TeamRef
from app.services import dbctx, forecast_store, lineup, mn

router = APIRouter(prefix="/forecasts", tags=["forecasts"])
LIST_LIMIT = 200


def _read(f: Forecast, names: dict[int, str]) -> ForecastRead:
    mine, theirs = names.get(f.my_team_id, "?"), names.get(f.opponent_id, "?")
    return ForecastRead(
        id=f.public_id,
        created_at=f.created_at,
        my_team=TeamRef(id=f.my_team_id, name=mine),
        opponent=TeamRef(id=f.opponent_id, name=theirs),
        format=f.format,
        p_series=f.p_series,
        text=mn.forecast_line(f.format, f.p_series, mine, theirs),
        model_version=f.model_version,
        outputs=f.outputs,
        graded_at=f.graded_at,
        result=f.result,
        log_loss=f.log_loss,
        brier=f.brier,
    )


def _names(db, rows) -> dict[int, str]:
    ids = {i for f in rows for i in (f.my_team_id, f.opponent_id)}
    return dict(db.execute(select(Team.id, Team.name).where(Team.id.in_(ids))).all())


@router.post("", status_code=status.HTTP_201_CREATED)
def create(body: ForecastCreate, db: DbSession, user: StaffUser) -> ForecastRead:
    mine, theirs = db.get(Team, body.my_team_id), db.get(Team, body.opponent_id)
    if mine is None or theirs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team")
    if mine.id == theirs.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick two different teams")
    try:
        with dbctx.using(db):
            my_five = lineup.resolve([int(s) for s in body.my_lineup])
            their_five = lineup.resolve([int(s) for s in body.their_lineup])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown player {exc}") from None
    try:
        row = forecast_store.record(db, user, mine, theirs, my_five, their_five, body.format)
    except ValueError:
        raise HTTPException(status.HTTP_409_CONFLICT, "A team has no Rating yet") from None
    return _read(row, {mine.id: mine.name, theirs.id: theirs.name})


@router.get("")
def index(db: DbSession, user: StaffUser) -> ForecastList:
    """The Workspace's Forecasts, newest first, graded first, and how they did."""
    forecast_store.grade(db)
    rows = db.scalars(
        select(Forecast)
        .where(Forecast.workspace_id == user.workspace_id)
        .order_by(Forecast.created_at.desc())
        .limit(LIST_LIMIT)
    ).all()
    names = _names(db, rows)
    return ForecastList(
        items=[_read(f, names) for f in rows],
        summary=ForecastSummary(**forecast_store.summary(rows)),
    )


@router.get("/{public_id}")
def detail(public_id: uuid.UUID, db: DbSession, user: StaffUser) -> ForecastRead:
    row = db.scalar(
        select(Forecast).where(
            Forecast.public_id == public_id, Forecast.workspace_id == user.workspace_id
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such forecast")
    return _read(row, _names(db, [row]))
