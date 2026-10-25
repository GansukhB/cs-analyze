"""The v2 overview of one my team (the DEMOLAB design's first screen).

Its numbers over a window of days against the window before it, its Strengths
and Weaknesses against the Pool as cards with their Rounds, each Map's record,
the last results, the Team's average Player rating Map by Map, its current five,
what the worker is doing and the Team's latest demos, and the next Upcoming
match. Every number is read from stored rows (team_numbers, player_rating,
review_pool). Bind a session with ``dbctx.using``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from app.models import (
    AnalysisJob,
    JobKind,
    JobStatus,
    MapRoster,
    Match,
    MatchKind,
    MatchMap,
    Player,
    Team,
    UpcomingMatch,
    Upload,
)
from app.services import map_pool, mn, player_cards, player_rating, review_pool, team_numbers
from app.services.dbctx import db

# The overview's cards: at most this many, the weightiest first.
INSIGHTS = 4
FORM = 10
TREND = 10
MAP_TREND = 8
POOL_STATUS = {"deep": "strong", "weak": "improve", "thin": "test", "untested": "untested"}


def build(
    team: Team, workspace_id: int, days: int | None, *, scrims: bool, now: datetime | None = None
) -> dict:
    now = now or datetime.now(UTC).replace(tzinfo=None)
    since = now - timedelta(days=days) if days else None
    before = now - timedelta(days=2 * days) if days else None
    kind = None if scrims else MatchKind.OFFICIAL
    maps = team_numbers.team_maps(team.id, since, kind=kind)
    previous = team_numbers.team_maps(team.id, before, since, kind=kind) if days else []
    now_n = team_numbers.numbers(team.id, maps)
    prev_n = team_numbers.numbers(team.id, previous)
    matches = {m.match_id for m in maps}
    updated = max((m.parsed_at for m in maps if m.parsed_at), default=None)
    return {
        "days": days,
        "scrims": scrims,
        "n_matches": len({m.match_id for m in maps if not team_numbers.is_scrim(m)}),
        "n_scrims": len({m.match_id for m in maps if team_numbers.is_scrim(m)}),
        "n_maps": len(maps),
        "n_all_matches": len(matches),
        "updated_at": updated,
        "kpis": {k: {**now_n[k].as_dict(), "prev": prev_n[k].pct} for k in team_numbers.KEYS},
        "insights": insights(team),
        "maps": map_rows(team, maps),
        "form": form(team, kind),
        "trend": trend(team, kind),
        "players": players(team, maps),
        "jobs": jobs(),
        "demos": demos(team, kind),
        "uploads": uploads(workspace_id),
        "upcoming": next_upcoming(team.id, workspace_id, now),
    }


def insights(team: Team) -> list[dict]:
    """The Team's weightiest Strengths and Weaknesses against the Pool, with the
    Rounds they were read from: two of each when there are."""
    seen: dict[tuple, dict] = {}
    for map_name in map_pool.active_duty():
        for line in review_pool.team_lines(team, map_name, set()):
            where = None if line["scope"] == "all_maps" else map_name
            # One card per idea and Side: the Map where it weighs most.
            key = (line["key"], line["side"])
            if key not in seen or line["weight"] > seen[key]["weight"]:
                seen[key] = {**line, "map": where}
    lines = sorted(seen.values(), key=lambda x: -x["weight"])
    good = [x for x in lines if x["good"]][:2]
    bad = [x for x in lines if not x["good"]][: INSIGHTS - len(good)]
    picked = sorted(good + bad, key=lambda x: -x["weight"])[:INSIGHTS]
    names = _names({sid for x in picked for sid, _n in x["players"]})
    return [_insight(x, names) for x in picked]


def _names(steamids: set[str]) -> dict[str, str]:
    ids = [int(s) for s in steamids if s.isdigit()]
    if not ids:
        return {}
    rows = db().execute(select(Player.steamid, Player.name).where(Player.steamid.in_(ids)))
    return {str(sid): name for sid, name in rows}


def _insight(x: dict, names: dict[str, str]) -> dict:
    key, good = x["key"], x["good"]
    role = "my_strong" if good else "my_weak"
    title, counter = mn.ADVICE_TEXT.get((key, role), ("", ""))
    label = mn.SUMMARY_LABEL.get(key) or mn.REVIEW_CODE.get(key, key)
    if not counter and not good:
        counter = mn.SUMMARY_ADVICE.get(key, "")
    # A Weakness well past the bound is a risk; nearer it, something to watch.
    tone = "strength" if good else ("risk" if abs(x["z"]) >= 1.5 else "watch")
    return {
        "key": key,
        "kind": x["kind"],
        "tone": tone,
        "label": label,
        "title": title or label,
        "advice": counter,
        "map": x["map"],
        "map_label": mn.game_map(x["map"]) if x["map"] else None,
        "side": x["side"],
        "value": x["value"],
        "pool": x["mean"],
        "z": x["z"],
        "of": x["of"],
        "n": x["evidence"]["n"],
        "maps": x["evidence"]["maps"],
        "strength": x["evidence"]["strength"],
        "refs": x["evidence"]["refs"],
        "players": [names.get(sid, sid) for sid, _n in x["players"]],
    }


def map_rows(team: Team, maps: list[MatchMap]) -> list[dict]:
    """Each Active Map (and any other played in the window): its record in the
    window, the pool's verdict over all its Maps, and its last few round shares."""
    pool = {r["map"]: r for r in map_pool.team_pool(team)["rows"]}
    grouped = team_numbers.by_map(team.id, maps)
    every = team_numbers.team_maps(team.id, kind=MatchKind.OFFICIAL)
    shares = team_numbers.round_shares(team.id, every)
    last = team_numbers.by_map(team.id, every)
    rows = []
    for name in list(map_pool.active_duty()) + sorted(set(grouped) - set(map_pool.active_duty())):
        played = grouped.get(name, [])
        n = team_numbers.numbers(team.id, played)
        p = pool.get(name) or {}
        rows.append(
            {
                "map": name,
                "label": mn.game_map(name),
                "active": name in map_pool.active_duty(),
                "played": len(played),
                "won": n["maps"].won,
                "win": n["maps"].pct,
                "t": n["rounds_t"].pct,
                "ct": n["rounds_ct"].pct,
                "pistol": n["pistol"].pct,
                "trend": [
                    round(shares[m.id], 3)
                    for m in last.get(name, [])[-MAP_TREND:]
                    if m.id in shares
                ],
                "status": POOL_STATUS.get(p.get("status", "untested"), "untested"),
                "shrunk": p.get("shrunk"),
            }
        )
    return rows


def _matches(team: Team, kind: str | None, limit: int) -> list[Match]:
    q = (
        select(Match)
        .where(
            or_(Match.team1_id == team.id, Match.team2_id == team.id),
            Match.team1_score.is_not(None),
            Match.team2_score.is_not(None),
        )
        .options(joinedload(Match.team1), joinedload(Match.team2))
        .order_by(Match.played_at.desc())
        .limit(limit)
    )
    if kind:
        q = q.where(Match.kind == kind)
    return list(db().scalars(q).unique())


def form(team: Team, kind: str | None) -> list[dict]:
    """The last results, oldest first, from the Matches' own scores (parsed or not)."""
    out = []
    for m in reversed(_matches(team, kind, FORM)):
        ours, theirs = (
            (m.team1_score, m.team2_score)
            if m.team1_id == team.id
            else (m.team2_score, m.team1_score)
        )
        opp = m.team2 if m.team1_id == team.id else m.team1
        out.append(
            {
                "match_id": m.id,
                "played_at": m.played_at,
                "opponent": opp.name if opp else m.opponent_label,
                "ours": ours,
                "theirs": theirs,
                "won": ours > theirs if ours != theirs else None,
                "scrim": m.kind == MatchKind.SCRIM,
            }
        )
    return out


def trend(team: Team, kind: str | None) -> list[dict]:
    """The Team's five's average Player rating on each of its last Match Maps."""
    maps = team_numbers.team_maps(team.id, kind=kind)[-TREND:]
    lines = player_rating.per_map(m.id for m in maps)
    out = []
    for m in maps:
        five = [line for (mm, _pid), (line, tid) in lines.items() if mm == m.id and tid == team.id]
        value = player_rating.team_average(five)
        if value is not None:
            out.append(
                {
                    "match_map_id": m.id,
                    "played_at": m.match.played_at,
                    "map": team_numbers.map_name(m),
                    "rating": round(value, 3),
                }
            )
    return out


def current_five(team: Team) -> list[Player]:
    """Who played the Team's most recent parsed Match Map."""
    latest = db().scalar(
        select(MatchMap.id)
        .join(Match, Match.id == MatchMap.match_id)
        .join(MapRoster, MapRoster.match_map_id == MatchMap.id)
        .where(MapRoster.team_id == team.id, MatchMap.parsed_at.is_not(None))
        .order_by(Match.played_at.desc(), MatchMap.map_number.desc())
        .limit(1)
    )
    if latest is None:
        return []
    return list(
        db().scalars(
            select(Player)
            .join(MapRoster, MapRoster.player_id == Player.id)
            .where(MapRoster.match_map_id == latest, MapRoster.team_id == team.id)
            .order_by(Player.name)
        )
    )


def players(team: Team, maps: list[MatchMap]) -> list[dict]:
    """The current five over the window: rating, ADR, KAST, and the one line the
    Reviews settle about each (a Weakness first, else a tendency, else Swing)."""
    five = current_five(team)
    totals = player_rating.per_player((m.id for m in maps), team.id)
    cards = player_cards.lines(team, [p.id for p in five])
    out = []
    for p in five:
        line = totals.get(p.id)
        out.append(
            {
                "steamid": str(p.steamid),
                "name": p.name,
                "rating": round(line.rating, 2) if line and line.rating is not None else None,
                "adr": round(line.adr, 1) if line and line.adr is not None else None,
                "kast": round(line.kast, 1) if line and line.kast is not None else None,
                "maps": line.maps if line else 0,
                "note": _note(cards.get(p.id)),
            }
        )
    return out


def _note(card: dict | None) -> dict | None:
    if not card:
        return None
    if card["weaknesses"]:
        w = card["weaknesses"][0]
        return {
            "good": False,
            "text": f"{w['label']}: {w['per24']}/24 (бусад {w['pool_per24']}/24)",
        }
    if card["tendencies"]:
        t = card["tendencies"][0]
        return {"good": True, "text": f"{t['label']}: {t['per24']}/24 (бусад {t['pool_per24']}/24)"}
    swing = card.get("swing")
    if swing and swing["clear"]:
        return {"good": swing["per_round"] > 0, "text": f"Swing/раунд {swing['per_round']:+.3f}"}
    return None


def jobs() -> list[dict]:
    """What the worker is on and what waits, then the last few that ended."""
    session = db()
    live = list(
        session.scalars(
            select(AnalysisJob)
            .where(AnalysisJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
            .order_by(AnalysisJob.id.desc())
            .limit(5)
        )
    )
    ended = list(
        session.scalars(
            select(AnalysisJob)
            .where(AnalysisJob.status.not_in([JobStatus.QUEUED, JobStatus.RUNNING]))
            .order_by(AnalysisJob.id.desc())
            .limit(max(0, 5 - len(live)))
        )
    )
    out = []
    for j in live + ended:
        label = f"{j.my_team_name} vs {j.opponent_name}" if j.kind == JobKind.SCOUT else j.kind
        out.append(
            {
                "public_id": str(j.public_id),
                "kind": j.kind,
                "label": label,
                "status": j.status,
                "stage": j.stage,
                "progress": j.progress,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
                "error": j.error[:200],
            }
        )
    return out


def demos(team: Team, kind: str | None) -> list[dict]:
    """The Team's latest Match Maps and where each stands, newest first, with the
    Workspace's uploads still on the way."""
    q = (
        select(MatchMap)
        .join(Match, Match.id == MatchMap.match_id)
        .where(or_(MatchMap.team1_id == team.id, MatchMap.team2_id == team.id))
        .options(
            joinedload(MatchMap.match),
            joinedload(MatchMap.game_map),
            joinedload(MatchMap.team1),
            joinedload(MatchMap.team2),
        )  # fmt: skip
        .order_by(Match.played_at.desc(), MatchMap.map_number)
        .limit(8)
    )
    if kind:
        q = q.where(Match.kind == kind)
    out = []
    for m in db().scalars(q).unique():
        ours, theirs = team_numbers.score_of(team.id, m)
        opp = team_numbers.opponent_of(team.id, m)
        out.append(
            {
                "match_id": m.match_id,
                "map_number": m.map_number,
                "played_at": m.match.played_at,
                "opponent": opp.name if opp else m.match.opponent_label,
                "map": mn.game_map(team_numbers.map_name(m)),
                "ours": ours,
                "theirs": theirs,
                "kind": m.match.kind,
                "parsed": m.parsed_at is not None,
            }
        )
    return out


def uploads(workspace_id: int) -> list[dict]:
    rows = db().scalars(
        select(Upload)
        .where(Upload.workspace_id == workspace_id)
        .order_by(Upload.id.desc())
        .limit(5)
    )
    return [
        {
            "id": u.id,
            "filename": u.filename,
            "kind": u.kind,
            "status": u.status,
            "played_on": u.played_on,
            "error": u.error[:200],
        }  # fmt: skip
        for u in rows
    ]


def next_upcoming(team_id: int, workspace_id: int, now: datetime) -> UpcomingMatch | None:
    """The my team's next Upcoming match; one that began less than 6 hours ago
    is still the next (it may be on)."""
    return db().scalar(
        select(UpcomingMatch)
        .where(
            UpcomingMatch.workspace_id == workspace_id,
            UpcomingMatch.team_id == team_id,
            UpcomingMatch.starts_at >= now - timedelta(hours=6),
        )
        .order_by(UpcomingMatch.starts_at)
        .limit(1)
    )
