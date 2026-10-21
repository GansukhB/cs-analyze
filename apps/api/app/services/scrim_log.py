"""A my team's Scrim log (docs/plans/07 RV-6): every Scrim its Workspace
uploaded, newest first, with its Maps and what its Summary says to work on.
Scrims are the Workspace's own development and nothing else reads them
(docs/adr/0010). The Scrims page and the Assistant's ``scrims`` tool read it."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Match, MatchKind, MatchMap
from app.services import mn, review_view, scope

LIMIT = 20


def log(db: Session, workspace_id: int, team_id: int, limit: int = LIMIT) -> list[dict]:
    scope.allow_scrims(db)
    matches = db.scalars(
        select(Match)
        .where(
            Match.kind == MatchKind.SCRIM,
            Match.workspace_id == workspace_id,
            or_(Match.team1_id == team_id, Match.team2_id == team_id),
        )
        .options(
            joinedload(Match.team1),
            joinedload(Match.team2),
            selectinload(Match.map_results).joinedload(MatchMap.game_map),
        )
        .order_by(Match.played_at.desc())
        .limit(limit)
    ).unique()
    rows = []
    for match in matches:
        other = match.team2 if match.team1_id == team_id else match.team1
        panel = review_view.match_panel(db, match)
        ours = next((s for s in panel["summaries"] if s["team_id"] == team_id), None) or {}
        rows.append(
            {
                "match_id": match.id,
                "played_at": match.played_at,
                "partner": (other.name if other else "") or match.opponent_label,
                "maps": [
                    {
                        "map_number": m.map_number,
                        "label": mn.game_map(m.game_map.name if m.game_map else ""),
                        "scoreline": m.scoreline,
                        "won": (m.winner_id == team_id) if m.winner_id else None,
                    }
                    for m in sorted(match.map_results, key=lambda m: m.map_number)
                ],
                "focus": [
                    {"text": f["text"], "advice": f.get("advice") or "", "weight": f["weight"]}
                    for f in (ours.get("focus") or [])[:3]
                ],
                "strengths": [
                    {"text": s["text"], "weight": s.get("weight") or 0.0}
                    for s in (ours.get("strengths") or [])[:2]
                ],
            }
        )
    return rows
