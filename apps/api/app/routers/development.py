"""Development plans (docs/plans/07 RV-9): Staff set a Player's goals; he reads
his own. Goals belong to the Workspace."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession, StaffUser
from app.models import DevelopmentGoal, Player, User
from app.schemas import (
    DevelopmentPlan,
    GoalCreate,
    GoalPatch,
    GoalProgress,
    GoalRead,
    GoalSuggestion,
    KpiChoice,
)
from app.services import dbctx, development

router = APIRouter(tags=["development"])
Steamid = Annotated[str, Path(pattern=r"^\d{1,20}$")]


def _player(db, steamid: str) -> Player:
    found = db.scalar(select(Player).where(Player.steamid == int(steamid)))
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such player")
    return found


def _allowed(user: User, player: Player) -> None:
    if not user.is_staff and user.player_id != player.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such player")


def _read(goal: DevelopmentGoal, player: Player) -> GoalRead:
    spec = development.kpis().get(goal.kpi) or {"label": goal.kpi, "better": "higher", "unit": ""}
    return GoalRead(
        id=goal.id,
        kpi=goal.kpi,
        label=spec["label"],
        better=spec["better"],
        unit=spec["unit"],
        baseline=goal.baseline,
        target=goal.target,
        start_on=goal.start_on,
        due_on=goal.due_on,
        status=goal.status,
        notes=goal.notes,
        progress=GoalProgress(**development.progress(goal, player)),
    )


@router.get("/players/{steamid}/goals")
def plan(steamid: Steamid, db: DbSession, user: CurrentUser) -> DevelopmentPlan:
    """His goals with their progress; for Staff, suggested goals and every KPI too."""
    player = _player(db, steamid)
    _allowed(user, player)
    with dbctx.using(db):
        goals = [_read(g, player) for g in development.by_player(user.workspace_id, player.id)]
        suggestions = development.suggest(player) if user.is_staff else []
    choices = [
        KpiChoice(kpi=k, label=v["label"], better=v["better"], unit=v["unit"])
        for k, v in development.kpis().items()
    ]
    return DevelopmentPlan(
        goals=goals,
        suggestions=[GoalSuggestion(**s) for s in suggestions],
        kpis=choices if user.is_staff else [],
    )


@router.post("/players/{steamid}/goals", status_code=status.HTTP_201_CREATED)
def add_goal(steamid: Steamid, body: GoalCreate, db: DbSession, user: StaffUser) -> GoalRead:
    player = _player(db, steamid)
    if body.kpi not in development.kpis():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No such KPI")
    start, due = development.default_dates()
    start, due = body.start_on or start, body.due_on or due
    if due <= start:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The goal must end after it starts")
    with dbctx.using(db):
        baseline = body.baseline
        if baseline is None:
            since = start - timedelta(days=development.BASELINE_DAYS)
            baseline = development.measure(player, body.kpi, since, start)["value"]
        goal = DevelopmentGoal(
            workspace_id=user.workspace_id,
            player_id=player.id,
            kpi=body.kpi,
            baseline=baseline,
            target=body.target,
            start_on=start,
            due_on=due,
            notes=body.notes.strip(),
            created_by_id=user.id,
        )
        db.add(goal)
        db.commit()
        return _read(goal, player)


def _goal(db, user: User, goal_id: int) -> DevelopmentGoal:
    goal = db.get(DevelopmentGoal, goal_id)
    if goal is None or goal.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such goal")
    return goal


@router.patch("/goals/{goal_id}")
def change_goal(goal_id: int, body: GoalPatch, db: DbSession, user: StaffUser) -> GoalRead:
    goal = _goal(db, user, goal_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(
                goal, key, value.strip() if isinstance(value, str) and key == "notes" else value
            )
    db.commit()
    with dbctx.using(db):
        return _read(goal, db.get(Player, goal.player_id))


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, db: DbSession, user: StaffUser) -> None:
    db.delete(_goal(db, user, goal_id))
    db.commit()
