"""A Briefing's notes drafted by the Assistant (docs/plans/10 AS-6).

Staff pick a Briefing's lines; this writes, per Map, a short Mongolian page from
those lines alone (their habits and the counters, our Levers, the matchups, the
pistol and economy plan) and one opening note. Every number in the draft is
checked against the lines it was written from (AS-4's runtime check): a number
the lines don't hold, to its rounding, is listed for Staff to check before they
save. Staff edit the draft; nothing is saved until they do.
"""

from __future__ import annotations

import json
import re

from app.config import get_settings
from app.services import assistant

MAX_TOKENS = 4000
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")

SYSTEM = """You write the notes of a Counter-Strike 2 Briefing: what a coach hands \
the players before a match. You are given, per map, lines a coach picked from the \
game plan (the opponent's habits with their counters, our Levers and Cautions, \
player matchups, pistol and economy plans), each with its numbers.

Rules:
- Write in Mongolian. Keep CS2 terms in English (site names, callouts, buy types, \
utility names, "retake", "rush", "stack", "pistol", "force buy", "eco", "Lever").
- Use only what the lines say. Every number you write must be one of the lines' \
numbers, unchanged or rounded; never add a statistic, a player or a habit.
- Per map at most 150 words, as 3 to 5 short paragraphs a player reads in a minute: \
what they do and how we answer, what we use, who to watch, the pistol and economy.
- The opening note is at most 60 words: the one or two things that matter most \
across the maps.
- Answer with JSON only: {"note": "...", "maps": {"<map id>": "..."}} with the map \
ids you were given."""


def numbers(text: str) -> set[float]:
    return {float(n.replace(",", ".")) for n in _NUMBER.findall(text or "")}


def _known(value: float, source: set[float]) -> bool:
    """A number is the lines' own when it is one of them, or one rounded."""
    return any(
        abs(value - s) < 1e-9 or abs(value - round(s)) < 1e-9 or abs(value - round(s, 1)) < 1e-9
        for s in source
    )


def unverified(draft: str, lines_text: str) -> list[str]:
    source = numbers(lines_text)
    return sorted({f"{n:g}" for n in numbers(draft) if not _known(n, source)})


def _lines_text(items: list[dict]) -> str:
    out = []
    for item in items:
        parts = [item.get("section") or "", item.get("title") or ""]
        parts += item.get("lines") or []
        if item.get("counter"):
            parts.append("→ " + item["counter"])
        out.append(" | ".join(p for p in parts if p))
    return "\n".join(out)


def _parse(text: str) -> dict:
    body = text.strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*|\s*```$", "", body)
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("the draft was not JSON")
    return json.loads(body[start : end + 1])


def draft(
    my_team: str, opponent: str, maps: list[dict], forecast_line: str = ""
) -> tuple[dict, assistant.Usage]:
    """``maps`` is ``[{"map", "label", "items"}]`` as a Briefing freezes them.
    Returns ``({"note", "maps": {map: text}, "unverified": {map|"note": [n]}}, usage)``."""
    settings = get_settings()
    usage = assistant.Usage(model=settings.claude_model)
    per_map = {m["map"]: _lines_text(m["items"]) for m in maps}
    prompt = {
        "fixture": f"{my_team} vs {opponent}",
        "forecast": forecast_line,
        "maps": [{"map": m["map"], "name": m["label"], "lines": per_map[m["map"]]} for m in maps],
    }
    message = assistant._client().beta.messages.create(
        model=settings.claude_model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(prompt, ensure_ascii=False)}],
        betas=[assistant.FALLBACK_BETA],
        fallbacks="default",
    )
    usage.add(getattr(message, "usage", None))
    text = "".join(
        getattr(b, "text", "") for b in message.content if getattr(b, "type", "") == "text"
    )
    parsed = _parse(text)
    every = "\n".join(per_map.values()) + "\n" + forecast_line
    out_maps = {m: str((parsed.get("maps") or {}).get(m) or "").strip() for m in per_map}
    note = str(parsed.get("note") or "").strip()
    checks = {m: unverified(t, per_map[m]) for m, t in out_maps.items()}
    checks["note"] = unverified(note, every)
    return {
        "note": note,
        "maps": out_maps,
        "unverified": {k: v for k, v in checks.items() if v},
    }, usage
