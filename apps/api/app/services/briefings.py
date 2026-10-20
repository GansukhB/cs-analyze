"""Briefings (CONTEXT.md: Briefing; docs/plans/01 WS-5).

Staff pick lines from a Fixture's Playbooks by their place in the panel
(``plan.0``, ``advice.ct.levers.1``, ``sections.setups.2``, ``pistols.0``,
``economy.1``, ``players.3``, ``self.t.0``); :func:`freeze` turns each into one
plain line (kind, title, lines, counter, Replay refs) cut from the panel the
server computes itself, so a Briefing says exactly what the Game Plan said when
it was made and nothing a browser sent.
"""

from __future__ import annotations

import gzip
import json


class BriefingError(ValueError):
    """A pick that names no line, or a Game Plan that moved since the page loaded."""


def _refs(evidence: dict | None) -> list[dict]:
    return list((evidence or {}).get("refs") or [])[:6]


def _habit(h: dict, section: str) -> dict:
    lines = [x for x in (h.get("detail"), h.get("review")) if x]
    return {
        "kind": "habit",
        "section": section,
        "title": h.get("title") or "",
        "lines": lines,
        "counter": h.get("counter") or "",
        "refs": _refs(h.get("evidence")),
    }


def freeze(panel: dict, path: str) -> dict:
    """The line at ``path`` in one Map's Playbook ``panel``, as a Briefing keeps it."""
    parts = path.split(".")
    try:
        head = parts[0]
        if head == "plan":
            p = panel["plan"][int(parts[1])]
            return {
                "kind": "plan", "section": (p.get("side") or "").upper(), "title": p["title"],
                "lines": [], "counter": p.get("counter") or "", "refs": [],
            }  # fmt: skip
        if head == "advice":
            side = next(s for s in panel["advice"]["sides"] if s["side"] == parts[1])
            a = side[parts[2]][int(parts[3])]
            refs = [r for proof in a.get("proofs") or [] for r in _refs(proof.get("evidence"))]
            return {
                "kind": a.get("role") or parts[2].rstrip("s"),
                "section": side.get("label") or parts[1],
                "title": a["title"],
                "lines": list(a.get("facts") or []),
                "counter": a.get("counter") or "",
                "refs": refs[:6],
            }
        if head == "sections":
            section = next(s for s in panel["sections"] if s["key"] == parts[1])
            return _habit(section["habits"][int(parts[2])], section.get("title") or "")
        if head == "economy":
            return _habit(panel["economy"]["habits"][int(parts[1])], "Эдийн засаг")
        if head == "self":
            side = next(s for s in panel["self_scout"] if s["side"] == parts[1])
            return _habit(side["habits"][int(parts[2])], f"Self-scout · {side.get('label', '')}")
        if head == "pistols":
            p = panel["pistols"][int(parts[1])]
            return {
                "kind": "pistol", "section": "Pistol", "title": p.get("text") or "",
                "lines": [p["next"]] if p.get("next") else [], "counter": "",
                "refs": [p["ref"]] if p.get("ref") else [],
            }  # fmt: skip
        if head == "players":
            p = panel["players"][int(parts[1])]
            lines = list(p.get("lines") or []) + ([p["duels"]] if p.get("duels") else [])
            return {
                "kind": "player", "section": ", ".join(p.get("tags") or []),
                "title": p.get("player") or "", "lines": lines, "counter": "", "refs": [],
            }  # fmt: skip
    except (KeyError, IndexError, ValueError, StopIteration):
        pass
    raise BriefingError(f"Ийм мөр алга: {path}")


def pack(payload: dict) -> bytes:
    return gzip.compress(json.dumps(payload, default=str).encode())


def unpack(blob: bytes) -> dict:
    return json.loads(gzip.decompress(blob))
