"""The week's practice, laid out on the tier-2 template (docs/plans/07 RV-11).

Nothing here is stored: each day of the research's week (R3) is filled from
what the Workspace already has. Monday reviews the my team's latest official
Matches (their agenda, RV-10) and the Development goals (RV-9) with where each
stands; Tuesday and Wednesday take the Focus points of the latest Scrims as the
Scrims' goals; Thursday and Saturday prepare the next opponent from the latest
Briefings (their Game Plan and veto lab); Friday plays, Sunday rests.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Briefing,
    DevelopmentGoal,
    GoalStatus,
    Match,
    MatchKind,
    Player,
    Team,
    WorkspaceTeam,
)
from app.services import development, scrim_log

DAYS = (
    ("Даваа", "Review, Development plan-ий хяналт", ("review", "goals")),
    ("Мягмар", "Онол, Scrim, retake ба prefire", ("scrims", "goals")),
    ("Лхагва", "Scrim, Review, retake ба prefire", ("scrims",)),
    ("Пүрэв", "Өрсөлдөгчийн бэлтгэл, veto түгжих, pistol-ийн дасгал", ("prep",)),
    ("Баасан", "Тоглолт", ()),
    ("Бямба", "Scrim, дараагийн өрсөлдөгч", ("scrims", "prep")),
    ("Ням", "Амралт", ()),
)
REVIEWS = 3
SCRIMS = 3
BRIEFINGS = 3


def _reviews(db: Session, team_id: int) -> list[dict]:
    rows = db.scalars(
        select(Match)
        .where(
            Match.kind == MatchKind.OFFICIAL,
            or_(Match.team1_id == team_id, Match.team2_id == team_id),
            Match.played_at.is_not(None),
        )
        .order_by(Match.played_at.desc())
        .limit(REVIEWS)
    ).all()
    out = []
    for m in rows:
        other_id = m.team2_id if m.team1_id == team_id else m.team1_id
        other = db.get(Team, other_id) if other_id else None
        out.append({"match_id": m.id, "opponent": other.name if other else m.opponent_label,
                    "score": m.score, "played_at": m.played_at})  # fmt: skip
    return out


def _goals(db: Session, workspace_id: int) -> list[dict]:
    rows = db.execute(
        select(DevelopmentGoal, Player)
        .join(Player, Player.id == DevelopmentGoal.player_id)
        .where(
            DevelopmentGoal.workspace_id == workspace_id,
            DevelopmentGoal.status == GoalStatus.ACTIVE,
        )
        .order_by(DevelopmentGoal.due_on)
    ).all()
    specs = development.kpis()
    out = []
    for goal, player in rows:
        progress = development.progress(goal, player)
        out.append({
            "player": player.name, "steamid": str(player.steamid),
            "kpi": (specs.get(goal.kpi) or {}).get("label", goal.kpi), "target": goal.target,
            "due_on": goal.due_on, "verdict": progress["verdict"], "value": progress["value"],
        })  # fmt: skip
    return out


def _prep(db: Session, workspace_id: int, team_id: int) -> list[dict]:
    rows = db.scalars(
        select(Briefing)
        .where(Briefing.workspace_id == workspace_id, Briefing.my_team_id == team_id)
        .order_by(Briefing.created_at.desc())
        .limit(BRIEFINGS)
    ).all()
    out = []
    for b in rows:
        opponent = db.get(Team, b.opponent_id)
        out.append({"briefing": str(b.public_id), "title": b.title,
                    "mine": team_id, "theirs": b.opponent_id,
                    "opponent": opponent.name if opponent else "?",
                    "shared": b.shared_at is not None})  # fmt: skip
    return out


def week(db: Session, workspace_id: int) -> dict:
    team_id = db.scalar(
        select(WorkspaceTeam.team_id).where(WorkspaceTeam.workspace_id == workspace_id).limit(1)
    )
    if team_id is None:
        return {"team": None, "days": [], "review": [], "goals": [], "scrims": [], "prep": []}
    team = db.get(Team, team_id)
    blocks = {
        "review": _reviews(db, team_id),
        "goals": _goals(db, workspace_id),
        "scrims": [
            {
                "match_id": s["match_id"],
                "partner": s["partner"],
                "played_at": s["played_at"],
                "focus": [f["text"] for f in s["focus"]],
            }
            for s in scrim_log.log(db, workspace_id, team_id, SCRIMS)
        ],  # fmt: skip
        "prep": _prep(db, workspace_id, team_id),
    }
    return {
        "team": {"id": team.id, "name": team.name},
        "days": [{"day": day, "theme": theme, "blocks": list(keys)} for day, theme, keys in DAYS],
        **blocks,
    }
