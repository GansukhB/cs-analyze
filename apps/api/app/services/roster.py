"""A Team's roster over time (docs/plans/05 TM-10): who played for it when.

Each Player's Match Maps for the Team, by the day the Match was played, cut
into stretches wherever :data:`GAP_DAYS` pass without them: a stand-in for a
week reads as a short bar, a benching as a gap, a return as a second bar.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select

from app.models import MapRoster, Match, MatchMap, Player
from app.services.dbctx import db

GAP_DAYS = 45


def timeline(team_id: int) -> dict:
    rows = (
        db()
        .execute(
            select(Player.steamid, Player.name, Match.played_at)
            .join(MapRoster, MapRoster.player_id == Player.id)
            .join(MatchMap, MatchMap.id == MapRoster.match_map_id)
            .join(Match, Match.id == MatchMap.match_id)
            .where(MapRoster.team_id == team_id, Match.played_at.is_not(None))
            .order_by(Match.played_at)
        )
        .all()
    )
    days: dict[int, list] = defaultdict(list)
    names: dict[int, str] = {}
    for steamid, name, played in rows:
        days[steamid].append(played)
        names[steamid] = name
    players = []
    for steamid, played in days.items():
        spans = []
        start = prev = played[0]
        maps = 1
        for when in played[1:]:
            if when - prev > timedelta(days=GAP_DAYS):
                spans.append({"from": start.date(), "to": prev.date(), "maps": maps})
                start, maps = when, 0
            prev = when
            maps += 1
        spans.append({"from": start.date(), "to": prev.date(), "maps": maps})
        players.append(
            {"steamid": str(steamid), "name": names[steamid], "maps": len(played), "spans": spans}
        )
    # The latest on top: the current five first, then who left, most recent first.
    players.sort(key=lambda p: (p["spans"][-1]["to"], p["maps"]), reverse=True)
    first = min((p["spans"][0]["from"] for p in players), default=None)
    last = max((p["spans"][-1]["to"] for p in players), default=None)
    return {"from": first, "to": last, "players": players}
