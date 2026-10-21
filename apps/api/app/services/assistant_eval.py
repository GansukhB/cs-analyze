"""The Assistant's golden set, asked and scored (docs/plans/10 AS-4).

Each question of ``app/data/assistant_golden.json`` is asked as a fresh chat
on its page (Teams, Matches and Players named there, resolved on this DB),
voice off. Scored: whether a tool it expects was called, and the numbers the
reply states that no tool returned (:mod:`grounding`). The language is read by
hand from the report. Every question is a paid turn, so the CLI asks first.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Match, MatchMap, Player, Team
from app.services import assistant

PATH = Path(__file__).resolve().parent.parent / "data" / "assistant_golden.json"
# What one question costs at the default model, roughly, for the CLI's warning.
COST_GUESS_USD = 0.06


def questions() -> list[dict]:
    return json.loads(PATH.read_text())["questions"]


def _team(session: Session, name: str) -> Team | None:
    return session.scalar(select(Team).where(func.lower(Team.name) == name.lower()))


def resolve(session: Session, page: dict) -> dict | None:
    """A question's page as the client would send it, or None when this DB
    lacks a Team, Match or Player it names."""
    if not page:
        return {}
    if "mine" in page:
        mine, theirs = _team(session, page["mine"]), _team(session, page["theirs"])
        return {"mine": mine.id, "theirs": theirs.id} if mine and theirs else None
    if "team" in page:
        team = _team(session, page["team"])
        return {"team": team.id} if team else None
    if "match" in page:
        a, b = (_team(session, n) for n in page["match"])
        if not a or not b:
            return None
        match_id = session.scalar(
            select(Match.id)
            .join(MatchMap, MatchMap.match_id == Match.id)
            .where(
                or_(
                    (Match.team1_id == a.id) & (Match.team2_id == b.id),
                    (Match.team1_id == b.id) & (Match.team2_id == a.id),
                ),
                MatchMap.parsed_at.is_not(None),
            )
            .order_by(Match.played_at.desc())
            .limit(1)
        )
        if match_id is None:
            return None
        return {"match": match_id, "map": page.get("map"), "round": page.get("round")}
    if "player" in page:
        player = session.scalar(
            select(Player).where(func.lower(Player.name) == page["player"].lower()).limit(1)
        )
        return {"player": str(player.steamid)} if player else None
    if page.get("picker"):
        return {"picker": True}
    return None


def ask(session: Session, item: dict, user=None) -> dict:
    """One question asked and scored."""
    raw = resolve(session, item["page"])
    if raw is None:
        return {"q": item["q"], "skipped": "a name on its page is not in this DB"}
    ctx = assistant.clean_context(session, raw, user)
    usage = assistant.Usage()
    paragraphs = []
    for event in assistant.chat_events(
        session, [], item["q"], context=ctx, voice_on=False, usage=usage
    ):
        if event["type"] == "paragraph":
            paragraphs.append(event["text"])
    return {
        "q": item["q"],
        "page": item["page"],
        "expected": item["tools"],
        "called": usage.tools,
        "tool_ok": any(t in item["tools"] for t in usage.tools),
        "unchecked": usage.unchecked,
        "answer": "\n\n".join(paragraphs),
        "cost_usd": round(usage.cost_usd(), 4),
    }


def summary(results: list[dict]) -> dict:
    asked = [r for r in results if "skipped" not in r]
    return {
        "asked": len(asked),
        "skipped": len(results) - len(asked),
        "tool_ok": sum(r["tool_ok"] for r in asked),
        "with_unchecked": sum(1 for r in asked if r["unchecked"]),
        "unchecked": sum(len(r["unchecked"]) for r in asked),
        "cost_usd": round(sum(r["cost_usd"] for r in asked), 3),
    }
