"""The management summary of a my team (v2 screen 10).

For a period (a month, a quarter or a year) against the one before it: the Map
record and Matches played, the VRS standing, practice hours from the Practice
schedule, how many of its Matches' Maps were parsed; the last six months' win
share beside their practice hours; its record by the opponent's current tier;
each Player's share of the Team's positive Swing with his monthly Player rating
and its spread; the Team goals; and the risks and openings the overview's cards
name. The form index is where the Team's Rating stands among every Team still
playing (0-100). Read from stored rows only; bind a session with ``dbctx.using``.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_, select

from app.models import (
    GoalStatus,
    Match,
    MatchKind,
    MatchMap,
    PracticeBlock,
    Team,
    TeamGoal,
)
from app.services import (
    player_rating,
    review_pool,
    team_goals,
    team_numbers,
    team_overview,
    team_strength,
)
from app.services.dbctx import db

PERIODS = {"m": 30, "q": 91, "y": 365}
MONTHS = 6
SPARK_MONTHS = 5
PRACTICE_KINDS = ("scrim", "drill", "review")


def _month_start(d: date, back: int = 0) -> date:
    y, m = d.year, d.month - back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def build(team: Team, workspace_id: int, period: str, today: date | None = None) -> dict:
    today = today or datetime.now(UTC).date()
    days = PERIODS[period]
    now = datetime.combine(today + timedelta(days=1), datetime.min.time())
    since = now - timedelta(days=days)
    before = since - timedelta(days=days)
    official = MatchKind.OFFICIAL
    maps = team_numbers.team_maps(team.id, since, now, kind=official)
    prev = team_numbers.team_maps(team.id, before, since, kind=official)
    n_now, n_prev = team_numbers.numbers(team.id, maps), team_numbers.numbers(team.id, prev)
    strength = team_strength.build(team)
    form_index = None
    if strength and strength.get("rank") and strength.get("ranked"):
        ranked = max(1, strength["ranked"] - 1)
        form_index = round(100 * (1 - (strength["rank"] - 1) / ranked))
    hours = _hours(team, workspace_id, since.date(), now.date())
    return {
        "period": period,
        "days": days,
        "since": since.date(),
        "summary": _summary(team, maps, prev, n_now, n_prev),
        "form_index": form_index,
        "rating": strength.get("rating") if strength else None,
        "rank": strength.get("rank") if strength else None,
        "ranked": strength.get("ranked") if strength else None,
        "kpis": {
            "maps": {**n_now["maps"].as_dict(), "prev": n_prev["maps"].pct},
            "matches": _record(team, since, now),
            "vrs": team_goals.vrs(team),
            "hours": hours,
            "parsed": _parsed(team, since, now),
        },
        "months": _months(team, workspace_id, today),
        "tiers": strength.get("tiers", []) if strength else [],
        "players": _players(team, maps, today),
        "goals": _goals(team, workspace_id),
        "risks": _risks(team),
    }


def _record(team: Team, since: datetime, until: datetime) -> dict:
    rows = db().scalars(
        select(Match).where(
            or_(Match.team1_id == team.id, Match.team2_id == team.id),
            Match.kind == MatchKind.OFFICIAL,
            Match.played_at >= since,
            Match.played_at < until,
            Match.team1_score.is_not(None),
        )
    )
    won = lost = 0
    for m in rows:
        ours, theirs = (
            (m.team1_score, m.team2_score)
            if m.team1_id == team.id
            else (m.team2_score, m.team1_score)
        )
        if ours is None or theirs is None or ours == theirs:
            continue
        won += ours > theirs
        lost += ours < theirs
    return {"won": won, "lost": lost}


def _parsed(team: Team, since: datetime, until: datetime) -> dict:
    """Of the Maps its official Matches in the period played, how many were parsed."""
    rows = (
        db()
        .execute(
            select(MatchMap.parsed_at)
            .join(Match, Match.id == MatchMap.match_id)
            .where(
                or_(Match.team1_id == team.id, Match.team2_id == team.id),
                Match.kind == MatchKind.OFFICIAL,
                Match.played_at >= since,
                Match.played_at < until,
            )
        )
        .all()
    )
    return {"parsed": sum(1 for (p,) in rows if p is not None), "of": len(rows)}


def _blocks(team: Team, workspace_id: int, start: date, end: date) -> list[PracticeBlock]:
    return list(
        db().scalars(
            select(PracticeBlock).where(
                PracticeBlock.workspace_id == workspace_id,
                PracticeBlock.team_id == team.id,
                PracticeBlock.day >= start,
                PracticeBlock.day < end,
            )
        )
    )


def _hours(team: Team, workspace_id: int, start: date, end: date) -> dict:
    from app.services.practice import hours

    out = {k: 0.0 for k in PRACTICE_KINDS}
    for b in _blocks(team, workspace_id, start, end):
        if b.kind in out:
            out[b.kind] += hours(b)
    return {**{k: round(v, 1) for k, v in out.items()}, "total": round(sum(out.values()), 1)}


def _months(team: Team, workspace_id: int, today: date) -> list[dict]:
    """The last six months: the Map record and the practice hours of each."""
    out = []
    for back in range(MONTHS - 1, -1, -1):
        start = _month_start(today, back)
        end = _month_start(today, back - 1) if back else _month_start(today, -1)
        maps = team_numbers.team_maps(
            team.id,
            datetime.combine(start, datetime.min.time()),
            datetime.combine(end, datetime.min.time()),
            kind=MatchKind.OFFICIAL,
        )
        n = team_numbers.numbers(team.id, maps)["maps"]
        out.append(
            {
                "month": start,
                "maps": n.of,
                "won": n.won,
                "pct": n.pct,
                "hours": _hours(team, workspace_id, start, end)["total"],
            }
        )
    return out


def _players(team: Team, maps: list[MatchMap], today: date) -> list[dict]:
    """The five: their share of the Team's positive Swing in the period, their
    Player rating month by month and its spread over their Maps."""
    five = team_overview.current_five(team)
    if not five:
        return []
    ids = {m.id for m in maps}
    sids = {str(p.steamid): p for p in five}
    positive: dict[str, float] = defaultdict(float)
    for t in review_pool.data().by_team.get(team.id, []):
        if t.mm not in ids:
            continue
        for sid, rows in t.players.items():
            if sid in sids:
                positive[sid] += sum(s for _n, s in rows if s > 0)
    total = sum(positive.values())
    lines = player_rating.per_map(m.id for m in maps)
    spark_start = _month_start(today, SPARK_MONTHS - 1)
    every = team_numbers.team_maps(
        team.id, datetime.combine(spark_start, datetime.min.time()), kind=MatchKind.OFFICIAL
    )
    monthly = player_rating.per_map(m.id for m in every)
    month_of = {
        m.id: date(m.match.played_at.year, m.match.played_at.month, 1)
        for m in every
        if m.match.played_at
    }
    out = []
    for sid, p in sids.items():
        per_map = [
            line.rating
            for (mm, pid), (line, tid) in lines.items()
            if pid == p.id and tid == team.id and line.rating is not None
        ]
        by_month: dict[date, player_rating.Line] = defaultdict(player_rating.Line)
        for (mm, pid), (line, tid) in monthly.items():
            if pid == p.id and tid == team.id and mm in month_of:
                by_month[month_of[mm]].merge(line)
        spark = [
            round(by_month[_month_start(today, back)].rating, 3)
            if _month_start(today, back) in by_month
            and by_month[_month_start(today, back)].rating is not None
            else None
            for back in range(SPARK_MONTHS - 1, -1, -1)
        ]
        out.append(
            {
                "steamid": sid,
                "name": p.name,
                "share": round(100.0 * positive[sid] / total, 1) if total else None,
                "rating": round(statistics.mean(per_map), 2) if per_map else None,
                "sigma": round(statistics.pstdev(per_map), 2) if len(per_map) >= 3 else None,
                "maps": len(per_map),
                "spark": spark,
            }
        )
    out.sort(key=lambda r: -(r["share"] or 0))
    return out


def _goals(team: Team, workspace_id: int) -> list[dict]:
    goals = db().scalars(
        select(TeamGoal)
        .where(
            TeamGoal.workspace_id == workspace_id,
            TeamGoal.team_id == team.id,
            TeamGoal.status == GoalStatus.ACTIVE,
        )
        .order_by(TeamGoal.due_on)
    )
    return [team_goals.read(g, team) for g in goals]


def _risks(team: Team) -> list[dict]:
    """The overview's weightiest Weaknesses as risks and Strengths as openings."""
    out = []
    for x in team_overview.insights(team):
        where = x["map_label"] or "Бүх Map"
        value = f"{round(100 * x['value'])}%" if x["kind"] == "rate" else f"{x['value']:.1f}/24"
        pool = f"{round(100 * x['pool'])}%" if x["kind"] == "rate" else f"{x['pool']:.1f}/24"
        out.append(
            {
                "kind": "opening" if x["tone"] == "strength" else "risk",
                "tone": x["tone"],
                "text": f"{where} {x['side'].upper()}: {x['label']} {value} (бусад {pool}). "
                f"{x['advice']}".strip(),
            }
        )
    return out


def _summary(team, maps, prev, n_now, n_prev) -> dict:
    """One sentence's facts: the Map share now against the period before, and the
    Active Map the pool calls weakest."""
    from app.services import map_pool

    weak = [r for r in map_pool.team_pool(team)["rows"] if r["active"] and r["status"] == "weak"]
    weakest = min(weak, key=lambda r: r["shrunk"] or 100) if weak else None
    return {
        "now": n_now["maps"].pct,
        "prev": n_prev["maps"].pct,
        "maps": n_now["maps"].of,
        "prev_maps": n_prev["maps"].of,
        "weakest": weakest["label"] if weakest else None,
        "weakest_share": weakest["shrunk"] if weakest else None,
    }
