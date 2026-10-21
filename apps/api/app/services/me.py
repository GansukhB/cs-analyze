"""A Player login's own page (docs/plans/01 WS-4): their latest Match Maps and
Scrims, and their Focus points from the last few, worst Swing first.

Scrims count here: they are the Player's own development (docs/adr/0010), and
the page is theirs and their Staff's. Only Reviews already stored at the current
version are read, so opening the page never rebuilds one.
"""

from __future__ import annotations

import gzip
import json

from sqlalchemy import select

from app.models import (
    GameMap,
    MapRoster,
    Match,
    MatchKind,
    MatchMap,
    MatchMapReview,
    Player,
    PlayerMap,
    Team,
)
from app.services import mn, review, scope
from app.services.dbctx import db

RECENT = 10  # Match Maps listed
FOCUS_MAPS = 5  # the Focus points are read from this many
FOCUS = 8
KEEP_UP = 3  # Key plays shown as what to keep doing
# Findings about a whole side, as the Review's filters treat them (src/review/filters.ts).
TEAM_CODES = {"time_out", "kitless", "advantage_lost", "late_execute", "into_stack", "stack_read"}


def _own_swing(finding: dict, sid: str) -> float | None:
    """The Swing a Finding puts on this Player, or None when it isn't theirs.

    A lost advantage is the whole side's (review.py), so a Player carries only
    what their own death cost in it; a time-out or a missing kit is the Team's
    and stays in its Summary."""
    sids = finding.get("sids") or []
    if finding["code"] == "advantage_lost":
        deaths = (finding.get("facts") or {}).get("deaths") or []
        own = [float(d.get("swing") or 0.0) for d in deaths if d.get("sid") == sid]
        return own[0] if own else None
    if finding["code"] in TEAM_CODES or not sids or sids[0] != sid:
        return None
    return float(finding.get("swing") or 0.0)


def build(player: Player) -> dict:
    session = db()
    scope.allow_scrims(session)
    sid = str(player.steamid)
    rows = session.execute(
        select(MatchMap, MapRoster.team_id, Match, GameMap.name)
        .join(MapRoster, MapRoster.match_map_id == MatchMap.id)
        .join(Match, Match.id == MatchMap.match_id)
        .outerjoin(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(MapRoster.player_id == player.id, MatchMap.parsed_at.is_not(None))
        .order_by(Match.played_at.desc(), MatchMap.map_number.desc())
        .limit(RECENT)
    ).all()
    ids = [mm.id for mm, *_ in rows]
    teams = {x for mm, t, _m, _n in rows for x in (t, mm.team1_id, mm.team2_id) if x}
    names = dict(session.execute(select(Team.id, Team.name).where(Team.id.in_(teams))).all())
    stats = {
        r.match_map_id: r
        for r in session.scalars(
            select(PlayerMap).where(
                PlayerMap.player_id == player.id, PlayerMap.match_map_id.in_(ids)
            )
        )
    }
    stored = {
        mm_id: json.loads(gzip.decompress(payload))
        for mm_id, payload in session.execute(
            select(MatchMapReview.match_map_id, MatchMapReview.payload).where(
                MatchMapReview.match_map_id.in_(ids), MatchMapReview.version == review.version()
            )
        )
    }

    maps, focus, keep = [], [], []
    for i, (mm, team_id, match, map_name) in enumerate(rows):
        other = mm.team2_id if mm.team1_id == team_id else mm.team1_id
        st = stats.get(mm.id)
        payload = stored.get(mm.id)
        swings = []
        if payload:
            for r in payload.get("rounds") or []:
                if sid in (r.get("sides") or {}):
                    swings.append(float((r.get("swing") or {}).get(sid, 0.0)))
        maps.append(
            {
                "match_id": mm.match_id,
                "map_number": mm.map_number,
                "map": mn.game_map(map_name or ""),
                "played_at": match.played_at,
                "team": names.get(team_id, ""),
                "opponent": names.get(other, "") or match.opponent_label,
                "scrim": match.kind == MatchKind.SCRIM,
                "won": mm.winner_id == team_id if mm.winner_id and team_id else None,
                "score": mm.scoreline,
                "kills": st.kills if st else 0,
                "deaths": st.deaths if st else 0,
                "adr": round(st.adr, 1) if st and st.adr is not None else None,
                "swing_per_round": round(sum(swings) / len(swings), 4) if swings else None,
                "reviewed": payload is not None,
            }
        )
        if payload is None or i >= FOCUS_MAPS:
            continue
        who_names = {p["sid"]: p.get("name") or "?" for p in payload.get("players") or []}

        def who(s, who_names=who_names):
            return who_names.get(s, "?") if s else ""

        for f in payload.get("findings") or []:
            swing = _own_swing(f, sid)
            if swing is None:
                continue
            kind = review.CODE_KIND.get(f["code"], "")
            worded = mn.review_finding(f, who)
            item = {
                "match_id": mm.match_id,
                "map_number": mm.map_number,
                "map": mn.game_map(map_name or ""),
                "round": f.get("round"),
                "t": f.get("t"),
                "code": f["code"],
                "kind": kind,
                "label": mn.REVIEW_CODE.get(f["code"], f["code"]),
                "title": worded["title"],
                "text": worded["text"],
                "swing": round(swing, 4),
                "scrim": match.kind == MatchKind.SCRIM,
            }
            # Mistakes and Missed chances cost Swing; Key plays and Utility effects add it.
            (focus if kind in ("mistake", "missed_chance") else keep).append(item)
    focus.sort(key=lambda f: f["swing"])
    keep.sort(key=lambda f: -f["swing"])
    return {
        "player": {"steamid": sid, "name": player.name},
        "maps": maps,
        "focus": focus[:FOCUS],
        "keep": keep[:KEEP_UP],
        "focus_maps": min(FOCUS_MAPS, sum(1 for m in maps[:FOCUS_MAPS] if m["reviewed"])),
    }
