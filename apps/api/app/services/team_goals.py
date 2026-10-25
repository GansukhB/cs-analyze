"""Team goals (CONTEXT.md): one team number, on a my team's official Matches
only (grilling Q3), optionally one Map and Side, from a baseline to a target.

Progress is read since the goal started, never typed in: the share with an 80%
Wilson range, called reached once the range's worse end is past the target and
close while the range takes it in, as a Development goal is. The VRS regional rank is read
from the latest monthly snapshot and has no range. Bind a session with
``dbctx.using``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from app.models import MatchKind, Team, TeamGoal, VrsStanding
from app.services import stats, team_numbers, team_overview
from app.services.dbctx import db

# key -> (label, which way is better, unit)
KPIS: dict[str, tuple[str, str, str]] = {
    "maps": ("Map хожил", "higher", "%"),
    "rounds": ("Round хожил", "higher", "%"),
    "pistol": ("Pistol хожил", "higher", "%"),
    "opening": ("Opening duel хожил", "higher", "%"),
    "trade": ("Trade хийгдсэн үхэл", "higher", "%"),
    "post_plant": ("Plant-ын дараах хожил", "higher", "%"),
    "retake": ("Retake хожил", "higher", "%"),
    "force": ("Force buy хожил", "higher", "%"),
    "vrs": ("VRS бүсийн байр", "lower", ""),
}
BASELINE_DAYS = 90


def kpis() -> list[dict]:
    return [{"kpi": k, "label": v[0], "better": v[1], "unit": v[2]} for k, v in KPIS.items()]


def vrs(team: Team) -> dict | None:
    """The Team's latest VRS row; where one snapshot has two Teams by its id,
    the one whose roster holds most of its current five."""
    session = db()
    latest = session.scalar(
        select(VrsStanding.snapshot)
        .where(VrsStanding.team_id == team.id)
        .order_by(VrsStanding.snapshot.desc())
        .limit(1)
    )
    if latest is None:
        return None
    rows = list(
        session.scalars(
            select(VrsStanding).where(
                VrsStanding.team_id == team.id, VrsStanding.snapshot == latest
            )
        )
    )
    five = {p.name.casefold() for p in team_overview.current_five(team)}

    def overlap(row: VrsStanding) -> int:
        return sum(1 for n in row.roster or [] if str(n).casefold() in five)

    row = max(rows, key=lambda r: (overlap(r), -(r.regional_rank or 9999)))
    return {"snapshot": row.snapshot, "global": row.global_rank, "region": row.region,
            "regional": row.regional_rank, "points": row.points}  # fmt: skip


def measure(
    team: Team, kpi: str, map_name: str, side: str, since: date, until: date | None
) -> dict:
    """The number over the Team's official Match Maps in [since, until)."""
    if kpi == "vrs":
        v = vrs(team)
        return {"value": float(v["regional"]) if v and v["regional"] else None, "of": 0,
                "low": None, "high": None}  # fmt: skip
    start = datetime.combine(since, time.min)
    end = datetime.combine(until, time.min) if until else None
    maps = team_numbers.team_maps(team.id, start, end, kind=MatchKind.OFFICIAL)
    if map_name:
        maps = [m for m in maps if team_numbers.map_name(m) == map_name]
    key = f"rounds_{side}" if kpi == "rounds" and side else kpi
    count = team_numbers.numbers(team.id, maps, side or None)[key]
    if not count.of:
        return {"value": None, "of": 0, "low": None, "high": None}
    low, high = stats.wilson(count.won, count.of)
    return {"value": count.pct, "of": count.of, "low": round(100 * low, 1),
            "high": round(100 * high, 1)}  # fmt: skip


def progress(goal: TeamGoal, team: Team, today: date | None = None) -> dict:
    today = today or date.today()
    _label, better, _unit = KPIS.get(goal.kpi, ("", "higher", ""))
    now = measure(team, goal.kpi, goal.map, goal.side, goal.start_on, None)
    value = now["value"]
    # As a Development goal reads (development.progress): reached when even the
    # range's worse end is past the target, close when the range takes it in.
    if value is None:
        verdict = "no_data"
    else:
        lower = better == "lower"

        def past(v: float) -> bool:
            return v <= goal.target if lower else v >= goal.target

        worst = now["high"] if lower else now["low"]
        best = now["low"] if lower else now["high"]
        if past(value if worst is None else worst):
            verdict = "reached"
        elif best is not None and past(best):
            verdict = "close"
        else:
            verdict = "not_yet"
    return {**now, "verdict": verdict, "overdue": today > goal.due_on and verdict != "reached"}


def baseline(team: Team, kpi: str, map_name: str, side: str, start: date) -> float | None:
    """The number over the 90 days before the goal starts."""
    return measure(team, kpi, map_name, side, start - timedelta(days=BASELINE_DAYS), start)["value"]


def read(goal: TeamGoal, team: Team) -> dict:
    label, better, unit = KPIS.get(goal.kpi, (goal.kpi, "higher", ""))
    return {
        "id": goal.id,
        "kpi": goal.kpi,
        "label": label,
        "better": better,
        "unit": unit,
        "map": goal.map,
        "side": goal.side,
        "title": goal.title,
        "notes": goal.notes,
        "baseline": goal.baseline,
        "target": goal.target,
        "start_on": goal.start_on,
        "due_on": goal.due_on,
        "status": goal.status,
        "progress": progress(goal, team),
    }
