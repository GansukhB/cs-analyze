"""What the stored data covers, and what it lacks (docs/plans/02 DATA-9).

For each Team: its parsed Match Maps by Map, how many are behind the parse
schema, which Tick Data lacks the Loadout (its Match must be downloaded
again), Sightings or schema 14's events, whose cuts or Review are stale, and
when it last played and was parsed. For each Map: how many Teams and Match
Maps make its Pool. And the Match Maps a Scout would download again.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    GameMap,
    Match,
    MatchMap,
    MatchMapReview,
    Team,
    TickDataset,
    WorkspaceTeam,
)
from app.services import review, scope, spots, tickdata
from app.services.analysis_store import CURRENT_SCHEMA_VERSION

MAX_QUEUE = 100


def _flags(mm, tables, derived, row_version, row_spots) -> dict:
    data = SimpleNamespace(tables=tables) if tables is not None else None
    name = mm.map_name
    return {
        "behind": mm.schema_version < CURRENT_SCHEMA_VERSION,
        "no_tickdata": data is None,
        "no_loadout": data is not None and not tickdata.reparseable(data),
        "no_sightings": data is not None and not tickdata.has_sightings(data),
        "no_events": data is not None and not tickdata.has_events(data),
        "derived_stale": data is not None and derived != tickdata.derived_version(),
        "review_stale": data is not None
        and (row_version != review.version() or row_spots != spots.version(name)),
    }


def overview(db: Session, workspace_id: int | None = None) -> dict:
    scope.allow_scrims(db)
    rows = db.execute(
        select(
            MatchMap.id, MatchMap.match_id, MatchMap.map_number, MatchMap.schema_version,
            MatchMap.parsed_at, MatchMap.team1_id, MatchMap.team2_id,
            GameMap.name.label("map_name"), Match.played_at, TickDataset.tables,
            TickDataset.derived_version,
            MatchMapReview.version.label("review_version"),
            MatchMapReview.spots_version.label("review_spots"),
        )
        .join(Match, Match.id == MatchMap.match_id)
        .outerjoin(GameMap, GameMap.id == MatchMap.game_map_id)
        .outerjoin(TickDataset, TickDataset.match_map_id == MatchMap.id)
        .outerjoin(MatchMapReview, MatchMapReview.match_map_id == MatchMap.id)
        .where(MatchMap.parsed_at.is_not(None))
    ).all()  # fmt: skip
    names = dict(db.execute(select(Team.id, Team.name)).all())
    mine = set()
    if workspace_id is not None:
        mine = set(
            db.scalars(
                select(WorkspaceTeam.team_id).where(WorkspaceTeam.workspace_id == workspace_id)
            )
        )
    teams: dict[int, dict] = {}
    pools: dict[str, dict] = defaultdict(lambda: {"maps": 0, "teams": set()})
    queue = []
    totals: Counter = Counter()
    for mm in rows:
        flags = _flags(mm, mm.tables, mm.derived_version, mm.review_version, mm.review_spots)
        name = mm.map_name or "?"
        pools[name]["maps"] += 1
        totals["maps"] += 1
        totals.update(k for k, v in flags.items() if v)
        if flags["behind"] and (flags["no_tickdata"] or flags["no_loadout"]):
            queue.append(
                {"match": mm.match_id, "map": mm.map_number, "map_name": name,
                 "teams": " vs ".join(names.get(t, "?") for t in (mm.team1_id, mm.team2_id)),
                 "played_at": mm.played_at,
                 "reason": "no_tickdata" if flags["no_tickdata"] else "no_loadout"}
            )  # fmt: skip
        for team_id in (mm.team1_id, mm.team2_id):
            if team_id is None:
                continue
            pools[name]["teams"].add(team_id)
            t = teams.setdefault(
                team_id,
                {"id": team_id, "name": names.get(team_id, "?"), "mine": team_id in mine,
                 "maps": 0, "by_map": Counter(), "flags": Counter(),
                 "last_played": None, "last_parsed": None},
            )  # fmt: skip
            t["maps"] += 1
            t["by_map"][name] += 1
            t["flags"].update(k for k, v in flags.items() if v)
            if mm.played_at and (t["last_played"] is None or mm.played_at > t["last_played"]):
                t["last_played"] = mm.played_at
            if t["last_parsed"] is None or mm.parsed_at > t["last_parsed"]:
                t["last_parsed"] = mm.parsed_at
    team_rows = sorted(teams.values(), key=lambda t: (not t["mine"], -t["maps"], t["name"]))
    queue.sort(key=lambda q: q["played_at"] or 0, reverse=True)
    return {
        "schema": CURRENT_SCHEMA_VERSION,
        "totals": dict(totals),
        "teams": [
            {**t, "by_map": sorted(t["by_map"].items(), key=lambda kv: -kv[1]),
             "flags": dict(t["flags"])}
            for t in team_rows
        ],
        "maps": sorted(
            ({"map": k, "maps": v["maps"], "teams": len(v["teams"])} for k, v in pools.items()),
            key=lambda m: -m["maps"],
        ),
        "queue": queue[:MAX_QUEUE],
        "queued": len(queue),
    }  # fmt: skip
