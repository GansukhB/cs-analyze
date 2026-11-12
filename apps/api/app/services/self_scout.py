"""Self-scout with no Fixture (CONTEXT.md: Self-scout, Tell): what a my team does
on one Map, read the way the Playbook reads an opponent, so Staff see what any
opponent could prepare against.

The Rounds are the Playbook's (the current five's era, the window, the GP-9
view), with no Head-to-head marked since there is no opponent. Each Map's Tells
come first, then the habits and Set plays worded as ours, the five slots per
Side, and the Team's Vetoes (Bo1 and Bo3 apart). Scrims never count: the
session's scope hides them (docs/adr/0010).

Bind a session with ``dbctx.using``.
"""

from __future__ import annotations

from collections import Counter

from app.models import Team
from app.services import levers, map_pool, mapstrategy, mn, playbook, tells, veto_history


def build(team: Team, map_name: str | None, view: dict | None = None) -> dict:
    window = mapstrategy.maps_in_window(team)
    era, _narrowed = mapstrategy.era_maps(team, window)
    counts = Counter(m.game_map.name for m in era if m.game_map)
    pool = list(map_pool.active_duty())
    names = pool + sorted(set(counts) - set(pool), key=lambda n: -counts[n])
    chosen = (
        map_name if map_name in counts else (max(pool, key=lambda n: counts[n]) if counts else None)
    )
    out = {
        "maps": [
            {"map": n, "label": mn.game_map(n), "active": n in pool, "maps": counts[n]}
            for n in names
        ],
        "map": chosen,
        "label": mn.game_map(chosen) if chosen else None,
        "sample": None,
        "tells": [],
        "habits": [],
        "slots": {},
        "vetoes": veto_summary(team, "mine"),
    }
    if not chosen or not counts[chosen]:
        return out
    every = playbook._team_rounds(team, None, chosen)
    rounds = playbook._viewed(team, every, view)
    sites = playbook.site_centroids(chosen)
    detail = playbook._detail(every)
    pools = playbook.map_pools(chosen)
    habits = {
        side: playbook._fielded_only(
            team, playbook.side_habits(team.id, rounds, side, detail, sites, pools)
        )
        for side in ("ct", "t")
    }
    for found in habits.values():
        levers.annotate(found, team, chosen)
    out.update(
        sample={
            "maps": len({r.match_map_id for r in rounds}),
            "all_maps": sum(1 for m in window if m.game_map and m.game_map.name == chosen),
            "rounds": len(rounds),
            "of": len(every),
            "ct": sum(1 for r in rounds if r.side_of(team.id) == "ct"),
            "t": sum(1 for r in rounds if r.side_of(team.id) == "t"),
            "sites_known": "A" in sites and "B" in sites,
        },
        tells=[
            mn.tell(t, whose="mine")
            for t in tells.for_team(
                team.id,
                rounds,
                detail.setup,
                sites,
                chosen,
                every_map=playbook._team_rounds(team, None, None),
            )
        ],  # fmt: skip
        habits=[
            {"side": side, "label": mn.side(side), "habits": mn.playbook_habits(h, whose="mine")}
            for side, h in habits.items()
        ],
        slots={
            side: playbook._slots(team, rounds, side, detail, chosen, sites) for side in ("ct", "t")
        },
    )
    return out


def veto_summary(team: Team, whose: str) -> dict:
    """The Team's Veto history worded (``whose``: ``mine`` or ``theirs``): per format
    its Maps and Tells, and the latest Vetoes."""
    raw = veto_history.summary(team)
    return {
        "team": {"id": team.id, "name": team.name},
        "since": raw["since"],
        "vetoes": raw["vetoes"],
        "formats": [
            {
                "best_of": f["best_of"],
                "vetoes": f["vetoes"],
                "maps": [{**row, "label": mn.game_map(row["map"])} for row in f["maps"]],
                "tells": [mn.veto_tell(t, whose=whose) for t in f["tells"]],
            }
            for f in raw["formats"].values()
        ],
        "recent": [
            {**v, "steps": [{**s, "label": mn.game_map(s["map"])} for s in v["steps"]]}
            for v in raw["recent"]
        ],
    }
