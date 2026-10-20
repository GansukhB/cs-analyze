"""Development plans (CONTEXT.md: Development plan; docs/plans/07 RV-9).

A goal names one KPI of a Player: a Finding's rate per 24 Rounds (from the
stored Reviews) or one of his round numbers (opening duels won, deaths traded,
KAST, ADR). :func:`measure` reads it over any dates from his Match Maps and,
being his own development, his Scrims too (docs/adr/0010), with an 80% range
from resampling whole Match Maps, so a lucky night doesn't move a goal.
:func:`suggest` proposes goals from the Findings he gets clearly more often than
every reviewed Player, the current rate as the baseline and the Pool's as the
target; Staff choose.
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from app.models import (
    DevelopmentGoal,
    GoalStatus,
    MapRoster,
    Match,
    MatchMap,
    MatchMapReview,
    Player,
    PlayerRound,
    Round,
)
from app.services import mn, player_cards, review, review_pool, scope, stats
from app.services.dbctx import count_if, db, total

PER_ROUNDS = 24
BASELINE_DAYS = 90
BLOCK_DAYS = 28  # a goal's default length: four weeks
SUGGEST = 3
SUGGEST_MIN_EVENTS = 3
SUGGEST_OVER = 1.2  # his rate this far above every Player's before it is suggested

ROUND_KPIS = {
    "opening_win_pct": ("Opening duel хожсон", "higher", "%"),
    "traded_death_pct": ("Trade хийгдсэн үхэл", "higher", "%"),
    "kast_pct": ("KAST", "higher", "%"),
    "adr": ("ADR", "higher", ""),
}


def kpis() -> dict[str, dict]:
    """Every KPI a goal can name: label, which way is better, unit."""
    out = {
        code: {
            "label": mn.REVIEW_CODE.get(code, code),
            "better": "lower" if kind in ("mistake", "missed_chance") else "higher",
            "unit": "/24",
            "kind": "finding",
        }
        for code, kind in review.CODE_KIND.items()
    }
    for key, (label, better, unit) in ROUND_KPIS.items():
        out[key] = {"label": label, "better": better, "unit": unit, "kind": "round"}
    return out


def _maps(player: Player, since: date | None, until: date | None) -> list[MatchMap]:
    session = db()
    scope.allow_scrims(session)  # his Scrims are his own development
    query = (
        select(MatchMap)
        .join(MapRoster, MapRoster.match_map_id == MatchMap.id)
        .join(Match, Match.id == MatchMap.match_id)
        .where(MapRoster.player_id == player.id, MatchMap.parsed_at.is_not(None))
    )
    if since:
        query = query.where(Match.played_at >= datetime.combine(since, time.min))
    if until:
        query = query.where(Match.played_at < datetime.combine(until + timedelta(days=1), time.min))
    return list(session.scalars(query))


def _per_map_findings(player: Player, maps: list[MatchMap]) -> dict[int, tuple[Counter, int]]:
    """match_map id -> (his Findings by code, his Rounds), from Reviews at this version."""
    sid = str(player.steamid)
    out = {}
    for mm_id, payload in db().execute(
        select(MatchMapReview.match_map_id, MatchMapReview.payload).where(
            MatchMapReview.match_map_id.in_([m.id for m in maps]),
            MatchMapReview.version == review.version(),
        )
    ):
        stored = json.loads(gzip.decompress(payload))
        rounds = sum(1 for r in stored.get("rounds") or [] if sid in (r.get("sides") or {}))
        codes = Counter(
            f["code"] for f in stored.get("findings") or [] if (f.get("sids") or [None])[0] == sid
        )
        out[mm_id] = (codes, rounds)
    return out


def _per_map_rounds(player: Player, maps: list[MatchMap]) -> dict[int, dict]:
    rows = db().execute(
        select(
            Round.match_map_id,
            count_if(PlayerRound.id.is_not(None)),
            count_if(PlayerRound.opening_kill),
            count_if(PlayerRound.opening_death),
            count_if(PlayerRound.traded),
            total(PlayerRound.deaths),
            count_if(PlayerRound.kast),
            total(PlayerRound.damage),
        )
        .join(Round, Round.id == PlayerRound.round_id)
        .where(PlayerRound.player_id == player.id, Round.match_map_id.in_([m.id for m in maps]))
        .group_by(Round.match_map_id)
    )
    return {
        mm: {"rounds": int(n or 0), "ok": int(ok or 0), "od": int(od or 0), "traded": int(tr or 0),
             "deaths": int(de or 0), "kast": int(ka or 0), "damage": int(dmg or 0)}
        for mm, n, ok, od, tr, de, ka, dmg in rows
    }  # fmt: skip


def _ratio(groups: list[tuple[float, float]], scale: float) -> float | None:
    num, den = sum(g[0] for g in groups), sum(g[1] for g in groups)
    return scale * num / den if den else None


def measure(player: Player, kpi: str, since: date | None, until: date | None = None) -> dict:
    """``{value, low, high, maps, rounds, events}`` for one KPI over these dates."""
    spec = kpis().get(kpi)
    maps = _maps(player, since, until)
    empty = {"value": None, "low": None, "high": None, "maps": 0, "rounds": 0, "events": 0}
    if spec is None or not maps:
        return empty
    if spec["kind"] == "finding":
        per = _per_map_findings(player, maps)
        groups = [(codes.get(kpi, 0), rounds) for codes, rounds in per.values() if rounds]
        scale = PER_ROUNDS
    else:
        per = _per_map_rounds(player, maps)
        num, den, scale = {
            "opening_win_pct": ("ok", None, 100.0),
            "traded_death_pct": ("traded", "deaths", 100.0),
            "kast_pct": ("kast", "rounds", 100.0),
            "adr": ("damage", "rounds", 1.0),
        }[kpi]
        groups = [
            (row[num], (row["ok"] + row["od"]) if den is None else row[den]) for row in per.values()
        ]
        groups = [g for g in groups if g[1]]
    if not groups:
        return empty
    value = _ratio(groups, scale)
    low, high = stats.bootstrap(groups, lambda sample: _ratio(sample, scale) or 0.0, draws=400)
    return {
        "value": round(value, 2),
        "low": round(low, 2),
        "high": round(high, 2),
        "maps": len(groups),
        "rounds": sum(r.get("rounds", 0) for r in per.values())
        if spec["kind"] == "round"
        else sum(g[1] for g in groups),
        "events": int(sum(g[0] for g in groups)) if spec["kind"] == "finding" else None,
    }


def progress(goal: DevelopmentGoal, player: Player, today: date | None = None) -> dict:
    """Where the goal stands since it started: reached when even the range's
    worse end is past the target, close when the range takes it in."""
    spec = kpis().get(goal.kpi) or {"better": "higher"}
    now = measure(player, goal.kpi, goal.start_on, today)
    value, low, high = now["value"], now["low"], now["high"]
    verdict = "no_data"
    if value is not None:
        lower = spec["better"] == "lower"
        worst = high if lower else low
        met = (lambda v: v <= goal.target) if lower else (lambda v: v >= goal.target)
        if met(worst):
            verdict = "reached"
        elif met(value) or (low <= goal.target <= high):
            verdict = "close"
        else:
            verdict = "not_yet"
    return {**now, "verdict": verdict}


def _pool_per24() -> dict[str, float]:
    """Every reviewed Player's rate of each code per 24 Rounds (official Matches)."""
    data = review_pool.data()
    rounds = sum(len(v) for t in data.tallies for v in t.players.values())
    counts: Counter = Counter()
    for t in data.tallies:
        for code, events in t.codes.items():
            counts[code] += sum(1 for e in events if e[2])
    return {code: PER_ROUNDS * n / rounds for code, n in counts.items()} if rounds else {}


def suggest(player: Player, today: date | None = None) -> list[dict]:
    """Goals worth setting: his Mistakes and Missed chances well above every
    Player's rate over the last :data:`BASELINE_DAYS`, the costliest first."""
    today = today or date.today()
    since = today - timedelta(days=BASELINE_DAYS)
    maps = _maps(player, since, today)
    if not maps:
        return []
    per = _per_map_findings(player, maps)
    rounds = sum(r for _c, r in per.values())
    codes: Counter = Counter()
    for c, _r in per.values():
        codes.update(c)
    pool = _pool_per24()
    priors, _seen = player_cards._pool_rates()
    n_eff = stats.effective_n(rounds, player_cards.review_pool_rounds_per_map())
    out = []
    for code, n in codes.items():
        if review.CODE_KIND.get(code) not in ("mistake", "missed_chance") or n < SUGGEST_MIN_EVENTS:
            continue
        his = PER_ROUNDS * n / rounds if rounds else 0.0
        theirs = pool.get(code)
        prior = stats.beta_prior(priors.get(code) or [])
        if theirs is None or prior is None or his < SUGGEST_OVER * theirs:
            continue
        # The same test as the Player cards (PL-7): clearly his, not a bad month.
        post = stats.shrink(n, n_eff, prior)
        if not (post.clear() and post.above):
            continue
        out.append(
            {
                "kpi": code,
                "label": mn.REVIEW_CODE.get(code, code),
                "baseline": round(his, 2),
                "target": round(theirs, 2),
                "events": n,
                "rounds": rounds,
                "over": round(his / theirs, 2) if theirs else None,
                # Findings a goal at the Pool's rate would save over these Rounds.
                "excess": round(n - theirs * rounds / PER_ROUNDS, 1),
            }
        )
    out.sort(key=lambda s: -s["excess"])
    return out[:SUGGEST]


def default_dates(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    return today, today + timedelta(days=BLOCK_DAYS)


def by_player(workspace_id: int, player_id: int) -> list[DevelopmentGoal]:
    return list(
        db().scalars(
            select(DevelopmentGoal)
            .where(
                DevelopmentGoal.workspace_id == workspace_id,
                DevelopmentGoal.player_id == player_id,
            )
            .order_by(DevelopmentGoal.status != GoalStatus.ACTIVE, DevelopmentGoal.due_on)
        )
    )
