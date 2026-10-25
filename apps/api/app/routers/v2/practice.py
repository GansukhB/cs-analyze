"""A my team's practice week (v2 screen 09): its Practice schedule, Team goals
and Review queue, all Staff's (grilling Q4–Q6)."""

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import DbSession, StaffUser
from app.models import Match, PracticeBlock, ReviewQueueItem, TeamGoal, User
from app.routers.v2.common import my_team, team
from app.schemas_v2 import (
    BlockRead,
    BlockWrite,
    GoalKpi,
    PracticePlan,
    QueuePatch,
    QueueRead,
    QueueWrite,
    TeamGoalPatch,
    TeamGoalRead,
    TeamGoalWrite,
)
from app.services import dbctx, practice, scope, team_goals

router = APIRouter()


def _own(db: Session, user: User, model, row_id: int):
    found = db.get(model, row_id)
    if found is None or found.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return found


@router.get("/teams/{team_id}/practice")
def practice_week(
    team_id: int, db: DbSession, user: StaffUser, week: date | None = None
) -> PracticePlan:
    mine = my_team(db, user, team_id)
    start = practice.monday(week or practice.today())
    with dbctx.using(db):
        built = practice.week(db, mine, user.workspace_id, start)
        return PracticePlan(
            team={"id": mine.id, "name": mine.name}, today=practice.today(), **built
        )


# ------------------------------------------------------------- schedule blocks


@router.post("/teams/{team_id}/blocks", status_code=status.HTTP_201_CREATED)
def add_block(team_id: int, body: BlockWrite, db: DbSession, user: StaffUser) -> BlockRead:
    mine = my_team(db, user, team_id)
    if body.opponent_id is not None:
        team(db, body.opponent_id)
    b = PracticeBlock(workspace_id=user.workspace_id, team_id=mine.id, **body.model_dump())
    db.add(b)
    db.commit()
    with dbctx.using(db):
        return BlockRead(**practice.block_read(b))


@router.put("/blocks/{block_id}")
def put_block(block_id: int, body: BlockWrite, db: DbSession, user: StaffUser) -> BlockRead:
    b = _own(db, user, PracticeBlock, block_id)
    if body.opponent_id is not None:
        team(db, body.opponent_id)
    for k, v in body.model_dump().items():
        setattr(b, k, v)
    db.commit()
    with dbctx.using(db):
        return BlockRead(**practice.block_read(b))


@router.delete("/blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_block(block_id: int, db: DbSession, user: StaffUser) -> Response:
    db.delete(_own(db, user, PracticeBlock, block_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------ Team goals


@router.get("/goal-kpis")
def goal_kpis(_: StaffUser) -> list[GoalKpi]:
    return [GoalKpi(**k) for k in team_goals.kpis()]


@router.post("/teams/{team_id}/goals", status_code=status.HTTP_201_CREATED)
def add_goal(team_id: int, body: TeamGoalWrite, db: DbSession, user: StaffUser) -> TeamGoalRead:
    mine = my_team(db, user, team_id)
    if body.kpi not in team_goals.KPIS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown KPI")
    start = body.start_on or practice.today()
    if body.due_on < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Due before it starts")
    with dbctx.using(db):
        base = body.baseline
        if base is None:
            base = team_goals.baseline(mine, body.kpi, body.map, body.side, start)
        g = TeamGoal(
            workspace_id=user.workspace_id,
            team_id=mine.id,
            kpi=body.kpi,
            map=body.map,
            side=body.side,
            title=body.title.strip(),
            notes=body.notes,
            baseline=base,
            target=body.target,
            start_on=start,
            due_on=body.due_on,
            created_by_id=user.id,
        )
        db.add(g)
        db.commit()
        return TeamGoalRead(**team_goals.read(g, mine))


@router.patch("/goals/{goal_id}")
def patch_goal(goal_id: int, body: TeamGoalPatch, db: DbSession, user: StaffUser) -> TeamGoalRead:
    g = _own(db, user, TeamGoal, goal_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(g, k, v)
    db.commit()
    with dbctx.using(db):
        return TeamGoalRead(**team_goals.read(g, team(db, g.team_id)))


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, db: DbSession, user: StaffUser) -> Response:
    db.delete(_own(db, user, TeamGoal, goal_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------- Review queue


@router.post("/teams/{team_id}/queue", status_code=status.HTTP_201_CREATED)
def add_to_queue(team_id: int, body: QueueWrite, db: DbSession, user: StaffUser) -> QueueRead:
    mine = my_team(db, user, team_id)
    scope.allow_scrims(db)  # our own Scrims are worth watching too
    if db.scalar(select(Match.id).where(Match.id == body.match_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such match")
    week = practice.monday(body.week or practice.today())
    last = db.scalar(
        select(func.max(ReviewQueueItem.position)).where(
            ReviewQueueItem.workspace_id == user.workspace_id,
            ReviewQueueItem.team_id == mine.id,
            ReviewQueueItem.week == week,
        )
    )
    fields = body.model_dump(exclude={"week"})
    q = ReviewQueueItem(
        workspace_id=user.workspace_id,
        team_id=mine.id,
        week=week,
        position=(last or 0) + 1,
        **fields,
    )
    db.add(q)
    db.commit()
    with dbctx.using(db):
        return QueueRead(**practice.queue_read(q))


@router.patch("/queue/{item_id}")
def patch_queue(item_id: int, body: QueuePatch, db: DbSession, user: StaffUser) -> QueueRead:
    q = _own(db, user, ReviewQueueItem, item_id)
    if body.watched is not None:
        from app.models.base import utcnow

        q.watched_at = utcnow() if body.watched else None
        q.watched_by_id = user.id if body.watched else None
    if body.position is not None:
        q.position = body.position
    if body.title is not None:
        q.title = body.title
    if body.tag is not None:
        q.tag = body.tag
    db.commit()
    with dbctx.using(db):
        return QueueRead(**practice.queue_read(q))


@router.post("/queue/{item_id}/next-week")
def queue_next_week(item_id: int, db: DbSession, user: StaffUser) -> QueueRead:
    """An item not watched this week, moved to the next."""
    q = _own(db, user, ReviewQueueItem, item_id)
    q.week = q.week + timedelta(days=7)
    db.commit()
    with dbctx.using(db):
        return QueueRead(**practice.queue_read(q))


@router.delete("/queue/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_queue(item_id: int, db: DbSession, user: StaffUser) -> Response:
    db.delete(_own(db, user, ReviewQueueItem, item_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
