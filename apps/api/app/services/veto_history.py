"""A Team's Veto history (CONTEXT.md: Veto, Tell): what it bans first, bans,
picks and leaves over, Bo1 and Bo3 apart, since the Active Duty Maps last
changed (a new pool reshuffles every ban and pick).

Only HLTV Matches carry a Veto, and the session's scope decides which Matches a
request sees, as everywhere. A step belongs to a Team when the page's Team is
our row, has its HLTV id, or carries its name: our ``teams`` rows have
duplicates, so the name keeps a Team's history whole (as ``rating`` does).

A Veto Tell is a choice the Team makes the same way in at least half its Vetoes
of one format, over five or more, and at least as often as three Teams in four
of the Pool make theirs (the same rule the Round Tells follow, :mod:`tells`): a
permaban most Teams have is still one to plan the Veto around.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select

from app.models import Match, MatchVeto, Team, VetoAction
from app.services import patches
from app.services.dbctx import db, memo

MIN_VETOES = 5
TELL_SHARE = 0.5
POOL_MIN_TEAMS = 3
RECENT = 8
FORMATS = (1, 3, 5)


@dataclass
class _Veto:
    match_id: int
    hltv_id: int | None
    played_at: datetime | None
    best_of: int | None
    team1_id: int | None
    team2_id: int | None
    steps: list = field(default_factory=list)  # (step, action, map, team_id, hltv_id, name)


def _since(since: date | None) -> date:
    return since or patches.pool_changed()


def _vetoes(since: date) -> list[_Veto]:
    """Every Veto the session sees, played on or after ``since``, oldest first."""

    def compute():
        rows = db().execute(
            select(
                Match.id, Match.hltv_id, Match.played_at, Match.best_of, Match.team1_id,
                Match.team2_id, MatchVeto.step, MatchVeto.action, MatchVeto.map,
                MatchVeto.team_id, MatchVeto.team_hltv_id, MatchVeto.team_name,
            )
            .join(MatchVeto, MatchVeto.match_id == Match.id)
            .where(Match.played_at >= datetime.combine(since, datetime.min.time()))
            .order_by(Match.played_at, Match.id, MatchVeto.step)
        ).all()  # fmt: skip
        out: dict[int, _Veto] = {}
        for r in rows:
            v = out.get(r.id)
            if v is None:
                v = out[r.id] = _Veto(
                    r.id, r.hltv_id, r.played_at, r.best_of, r.team1_id, r.team2_id
                )
            v.steps.append((r.step, r.action, r.map, r.team_id, r.team_hltv_id, r.team_name))
        for v in out.values():
            if v.best_of is None:
                v.best_of = _format_from_steps(v.steps)
        return list(out.values())

    return memo(("veto_rows", since.isoformat()), compute)


def _format_from_steps(steps: list) -> int | None:
    """Best-of from the steps when the page gave no format line: the Maps picked
    plus the decider."""
    picks = sum(1 for s in steps if s[1] == VetoAction.PICK)
    left = any(s[1] == VetoAction.DECIDER for s in steps)
    n = picks + (1 if left else 0)
    return n if n in FORMATS else None


class _Who:
    """Tells whether a step is a Team's: by row, HLTV id or name."""

    def __init__(self, team: Team):
        self.id = team.id
        self.hltv_id = team.hltv_id
        self.name = team.name.casefold()

    def __call__(self, step) -> bool:
        _n, _a, _m, team_id, hltv_id, name = step
        if team_id is not None and team_id == self.id:
            return True
        if self.hltv_id is not None and hltv_id == self.hltv_id:
            return True
        return bool(name) and name.casefold() == self.name


def team_key(step) -> str | None:
    """A step's Team, as the Pool groups them: HLTV id, else the name."""
    _n, action, _m, _team_id, hltv_id, name = step
    if action == VetoAction.DECIDER:
        return None
    return f"h{hltv_id}" if hltv_id is not None else (f"n{name.casefold()}" if name else None)


def _choices(own: list) -> dict[str, str | None]:
    """The Team's first ban and its picks in one Veto (steps already its own)."""
    bans = [s[2] for s in own if s[1] == VetoAction.BAN]
    picks = [s[2] for s in own if s[1] == VetoAction.PICK]
    return {"first_ban": bans[0] if bans else None, "pick": picks[0] if picks else None}


def _opponent_name(v: _Veto, mine) -> str:
    for s in v.steps:
        if s[1] != VetoAction.DECIDER and not mine(s):
            return s[5]
    return ""


def team_vetoes(team: Team, since: date | None = None) -> list[dict]:
    """The Team's Vetoes since the pool changed, newest first, each step marked."""
    mine = _Who(team)
    out = []
    for v in reversed(_vetoes(_since(since))):
        if not any(mine(s) for s in v.steps):
            continue
        own = [s for s in v.steps if mine(s)]
        first = min(v.steps, key=lambda s: s[0])
        out.append(
            {
                "match_id": v.match_id,
                "hltv_id": v.hltv_id,
                "played_at": v.played_at.date().isoformat() if v.played_at else None,
                "best_of": v.best_of,
                "opponent": _opponent_name(v, mine),
                "started": mine(first),
                "steps": [
                    {"step": s[0], "action": s[1], "map": s[2], "mine": mine(s)}
                    for s in sorted(v.steps)
                ],
                **_choices(own),
            }
        )
    return out


def _spread(counts: Counter) -> tuple[str | None, float | None, int]:
    n = sum(counts.values())
    if not n:
        return None, None, 0
    top, k = counts.most_common(1)[0]
    return top, k / n, n


def pool_bar(best_of: int, point: str, since: date | None = None) -> float | None:
    """The 75th percentile of every Team's top-choice share at one Veto point, over
    the Teams with five Vetoes or more of that format; None with fewer than three."""
    day = _since(since)

    def compute():
        by_team: dict[str, Counter] = defaultdict(Counter)
        for v in _vetoes(day):
            if v.best_of != best_of:
                continue
            per: dict[str, list] = defaultdict(list)
            for s in v.steps:
                if (k := team_key(s)) is not None:
                    per[k].append(s)
            for k, own in per.items():
                choice = _choices(own)[point]
                if choice:
                    by_team[k][choice] += 1
        shares = sorted(
            top / n
            for c in by_team.values()
            if (n := sum(c.values())) >= MIN_VETOES
            for top in [c.most_common(1)[0][1]]
        )
        if len(shares) < POOL_MIN_TEAMS:
            return None
        return shares[int(0.75 * (len(shares) - 1))]

    return memo(("veto_pool_bar", best_of, point, day.isoformat()), compute)


def summary(team: Team, since: date | None = None) -> dict:
    """Per format: how often each Map was banned first, banned, picked and left
    over in the Team's Vetoes, its Veto Tells, and the latest Vetoes."""
    day = _since(since)
    listed = team_vetoes(team, day)
    formats = {}
    for best_of in FORMATS:
        these = [v for v in listed if v["best_of"] == best_of]
        if not these:
            continue
        first_ban, banned, picked, left = Counter(), Counter(), Counter(), Counter()
        for v in these:
            if v["first_ban"]:
                first_ban[v["first_ban"]] += 1
            for s in v["steps"]:
                if s["action"] == VetoAction.DECIDER:
                    left[s["map"]] += 1
                elif s["mine"] and s["action"] == VetoAction.BAN:
                    banned[s["map"]] += 1
                elif s["mine"] and s["action"] == VetoAction.PICK:
                    picked[s["map"]] += 1
        maps = sorted(
            set(first_ban) | set(banned) | set(picked) | set(left),
            key=lambda m: (-banned[m] + picked[m], m),
        )
        formats[f"bo{best_of}"] = {
            "best_of": best_of,
            "vetoes": len(these),
            "maps": [
                {
                    "map": m,
                    "first_ban": first_ban[m],
                    "banned": banned[m],
                    "picked": picked[m],
                    "left": left[m],
                }
                for m in maps
            ],
            "tells": tells(these, best_of, day),
        }
    return {
        "since": day.isoformat(),
        "vetoes": len(listed),
        "formats": formats,
        "recent": listed[:RECENT],
    }


def tells(vetoes: list[dict], best_of: int, since: date) -> list[dict]:
    """The Team's Veto Tells in one format: its first ban and (past Bo1) its pick."""
    out = []
    points = ("first_ban",) if best_of == 1 else ("first_ban", "pick")
    for point in points:
        top, share, n = _spread(Counter(v[point] for v in vetoes if v[point]))
        if top is None:
            continue
        bar = pool_bar(best_of, point, since)
        tell = n >= MIN_VETOES and share >= TELL_SHARE and (bar is None or share >= bar)
        out.append(
            {
                "point": point,
                "best_of": best_of,
                "top": top,
                "n": round(share * n),
                "of": n,
                "share": round(share, 3),
                "pool_p75": round(bar, 3) if bar is not None else None,
                "tell": tell,
            }
        )
    return out


def every_veto() -> list[_Veto]:
    """Every stored Veto the session sees, whatever its pool, oldest first."""
    return _vetoes(date(2000, 1, 1))


def habit(team: Team, best_of: int, since: date | None = None) -> dict:
    """The Team's bans and picks over its Vetoes of one format since the pool
    changed: ``{"ban": {map: n}, "pick": {map: n}, "vetoes": n}``."""
    mine = _Who(team)
    out = {"ban": Counter(), "pick": Counter(), "vetoes": 0}
    for v in _vetoes(_since(since)):
        if v.best_of != best_of or not any(mine(s) for s in v.steps):
            continue
        out["vetoes"] += 1
        for s in v.steps:
            if mine(s) and s[1] in ("ban", "pick"):
                out[s[1]][s[2]] += 1
    return out
