"""A my team's practice week (v2 screen 09): its Practice schedule, Team goals and
the Development plans of its five, the week's Review queue, the drills its
latest Match's Review agenda suggests, and the next Upcoming match.

Weeks run Monday to Sunday on Ulaanbaatar's calendar. Bind a session with
``dbctx.using``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    DevelopmentGoal,
    GoalStatus,
    Match,
    MatchKind,
    MatchMap,
    PracticeBlock,
    ReviewQueueItem,
    Team,
    TeamGoal,
    UpcomingMatch,
)
from app.services import agenda, development, mn, team_goals, team_overview, upcoming
from app.services.dbctx import db

UB = timezone(timedelta(hours=8))
KINDS = ("scrim", "drill", "review", "match", "rest")
DRILLS = 4


def today() -> date:
    return datetime.now(UB).date()


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def hours(block: PracticeBlock) -> float:
    """A block's length in hours from its HH:MM start and end; 0 without both."""
    try:
        h1, m1 = map(int, block.start.split(":"))
        h2, m2 = map(int, block.end.split(":"))
    except ValueError:
        return 0.0
    minutes = (h2 * 60 + m2) - (h1 * 60 + m1)
    if minutes < 0:  # past midnight
        minutes += 24 * 60
    return minutes / 60


def block_read(b: PracticeBlock) -> dict:
    opponent = db().get(Team, b.opponent_id) if b.opponent_id else None
    return {
        "id": b.id,
        "day": b.day,
        "start": b.start,
        "end": b.end,
        "kind": b.kind,
        "title": b.title,
        "note": b.note,
        "opponent": {"id": opponent.id, "name": opponent.name} if opponent else None,
        "hours": round(hours(b), 2),
    }


def queue_read(q: ReviewQueueItem) -> dict:
    mm = db().scalar(
        select(MatchMap).where(MatchMap.match_id == q.match_id, MatchMap.map_number == q.map_number)
    )
    label = mn.game_map(mm.game_map.name) if mm and mm.game_map else ""
    return {
        "id": q.id,
        "match_id": q.match_id,
        "map_number": q.map_number,
        "map": label,
        "round": q.round,
        "t": q.t,
        "seconds": q.seconds,
        "title": q.title,
        "tag": q.tag,
        "source": q.source,
        "position": q.position,
        "watched": q.watched_at is not None,
    }


def week(session: Session, team: Team, workspace_id: int, start: date) -> dict:
    end = start + timedelta(days=7)
    blocks = list(
        db().scalars(
            select(PracticeBlock)
            .where(
                PracticeBlock.workspace_id == workspace_id,
                PracticeBlock.team_id == team.id,
                PracticeBlock.day >= start,
                PracticeBlock.day < end,
            )
            .order_by(PracticeBlock.day, PracticeBlock.start)
        )
    )
    by_kind: dict[str, float] = {k: 0.0 for k in KINDS}
    for b in blocks:
        by_kind[b.kind] = by_kind.get(b.kind, 0.0) + hours(b)
    queue = list(
        db().scalars(
            select(ReviewQueueItem)
            .where(
                ReviewQueueItem.workspace_id == workspace_id,
                ReviewQueueItem.team_id == team.id,
                ReviewQueueItem.week == start,
            )
            .order_by(ReviewQueueItem.position, ReviewQueueItem.id)
        )
    )
    goals = list(
        db().scalars(
            select(TeamGoal)
            .where(TeamGoal.workspace_id == workspace_id, TeamGoal.team_id == team.id)
            .order_by(TeamGoal.due_on)
        )
    )
    active = [g for g in goals if g.status == GoalStatus.ACTIVE and g.due_on >= start]
    history = [g for g in goals if g not in active]
    return {
        "week": start,
        "blocks": [block_read(b) for b in blocks],
        "hours": {k: round(v, 1) for k, v in by_kind.items()},
        "queue": [queue_read(q) for q in queue],
        "goals": [team_goals.read(g, team) for g in active],
        "history": [team_goals.read(g, team) for g in history[-8:]],
        "player_goals": _player_goals(team, workspace_id),
        "drills": _drills(session, team),
        "upcoming": _upcoming(team, workspace_id, start),
    }


def _player_goals(team: Team, workspace_id: int) -> list[dict]:
    five = team_overview.current_five(team)
    if not five:
        return []
    rows = db().scalars(
        select(DevelopmentGoal).where(
            DevelopmentGoal.workspace_id == workspace_id,
            DevelopmentGoal.player_id.in_([p.id for p in five]),
            DevelopmentGoal.status == GoalStatus.ACTIVE,
        )
    )
    by_id = {p.id: p for p in five}
    out = []
    for g in rows:
        player = by_id[g.player_id]
        spec = development.kpis().get(g.kpi) or {"label": g.kpi, "better": "higher", "unit": ""}
        p = development.progress(g, player)
        out.append(
            {
                "id": g.id,
                "player": player.name,
                "steamid": str(player.steamid),
                "label": spec["label"],
                "better": spec["better"],
                "unit": spec["unit"],
                "baseline": g.baseline,
                "target": g.target,
                "due_on": g.due_on,
                "value": p["value"],
                "verdict": p["verdict"],
            }
        )
    return out


def _drills(session: Session, team: Team) -> list[dict]:
    """The latest official Match's Review agenda: its drills, from the Focus points."""
    latest = db().scalar(
        select(Match)
        .join(MatchMap, MatchMap.match_id == Match.id)
        .where(
            or_(Match.team1_id == team.id, Match.team2_id == team.id),
            Match.kind == MatchKind.OFFICIAL,
            MatchMap.parsed_at.is_not(None),
        )
        .order_by(Match.played_at.desc())
        .limit(1)
    )
    if latest is None:
        return []
    try:
        built = agenda.build(session, latest, team.id)
    except Exception:  # the week stands without the agenda's drills
        return []
    actions = next((s for s in built["sections"] if s["key"] == "actions"), None) or {}
    opponent = built.get("opponent") or ""
    return [
        {
            "text": item["text"].removeprefix("Дасгал: "),
            "source": f"vs {opponent}",
            "match_id": latest.id,
        }  # fmt: skip
        for item in actions.get("items", [])
        if item["text"].startswith("Дасгал: ")
    ][:DRILLS]


def _upcoming(team: Team, workspace_id: int, start: date) -> dict | None:
    """The first Upcoming match from the week's Monday on."""
    since = (
        datetime.combine(start, datetime.min.time(), tzinfo=UB).astimezone(UTC).replace(tzinfo=None)
    )
    found = db().scalar(
        select(UpcomingMatch)
        .where(
            UpcomingMatch.workspace_id == workspace_id,
            UpcomingMatch.team_id == team.id,
            UpcomingMatch.starts_at >= since,
        )
        .order_by(UpcomingMatch.starts_at)
        .limit(1)
    )
    return upcoming.read(found) if found else None
