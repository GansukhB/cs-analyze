"""The Playbook as the «Юу хийх» tab shows it: the habits of
:mod:`app.services.playbook`, worded by :mod:`app.services.mn`.

The tab lists the Maps worth preparing; each Map's Playbook is its own request
(``GET /gameplan/{mine}/vs/{theirs}/playbook/{map}``), so the list is cheap.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.models import Team
from app.services import mn, playbook

# How many counters the plan at the top of a Map takes from each side.
PLAN_PER_SIDE = 2


def maps(report: Mapping) -> list[dict]:
    """The Maps worth a Playbook, in veto order, for the tab's map picker."""
    return [
        {
            "map": m["map"],
            "label": mn.game_map(m["map"]),
            "call": m["call"],
            "call_label": mn.VETO_CALL.get(m["call"], m["call"]),
            "mine": m["mine"],
            "theirs": m["theirs"],
            "h2h": m["h2h"],
        }
        for m in playbook.maps(report["board"]["board"])
    ]


def panel(my_team: Team, opponent: Team, map_name: str) -> dict:
    raw = playbook.build(my_team, opponent, map_name)
    their_t = mn.playbook_habits(raw["their_t"])
    their_ct = mn.playbook_habits(raw["their_ct"])
    plan = [
        {
            "side": side,
            "title": h["title"],
            "counter": h["counter"],
            "strength": h["evidence"]["strength"],
        }
        for side, habits in (("ct", their_t), ("t", their_ct))
        for h in habits[:PLAN_PER_SIDE]
    ]
    economy = raw["economy"]
    return {
        "map": map_name,
        "label": mn.game_map(map_name),
        "my_team": my_team.name,
        "opponent": opponent.name,
        "sample": raw["sample"],
        "sites_known": raw["sites_known"],
        "plan": plan,
        "sections": [
            {
                "key": "their_t",
                "title": f"{opponent.name}-ийн T тал → манай CT төлөвлөгөө",
                "habits": their_t,
            },
            {
                "key": "their_ct",
                "title": f"{opponent.name}-ийн CT тал → манай T төлөвлөгөө",
                "habits": their_ct,
            },
        ],
        "pistols": [mn.playbook_pistol(row) for row in raw["pistols"]],
        "economy": {
            "known": economy["known"],
            "buys": economy.get("buys"),
            "after_pistol_loss": economy.get("after_pistol_loss"),
            "habits": mn.playbook_habits(economy["habits"]),
        },
        "players": [mn.playbook_player(p) for p in raw["matchups"]],
        "self_scout": [
            {
                "side": side,
                "label": mn.side(side),
                "habits": mn.playbook_habits(habits, whose="mine"),
            }
            for side, habits in raw["self_scout"].items()
        ],
    }
