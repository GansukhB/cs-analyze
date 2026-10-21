"""Momentum, studied on the Pool only (docs/plans/05 TM-11).

After a Team has won three Rounds or more in a row, does it win the next one
more often than its buy says it should? The expectation is the Pool's rate for
that pair of buys on that Side (most of what looks like momentum is money, as
the research found); the residual is what is left. A streak's next Round is
also split by whether the other Team called a timeout in its freeze time. Never
said of one Team: a Team's few streaks would read as "tilt" from noise.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from app.models import Round
from app.services import pool_cache, stats
from app.services.analysis_store import PISTOL_ROUNDS
from app.services.dbctx import db

MOMENTUM_SCHEMA = 1
STREAK = 3
LONG = 5
PRIOR = 10.0  # pseudo-Rounds of 50% behind each buy pair's rate
GROUPS = {
    "all": f"{STREAK}+ раундын streak-ийн дараах раунд",
    "short": f"{STREAK}–{LONG - 1} раунд",
    "long": f"{LONG}+ раунд",
    "timeout": "Нөгөө баг timeout авсан",
    "no_timeout": "Timeout аваагүй",
}


def _rows():
    return db().execute(
        select(Round.match_map_id, Round.number, Round.winner_team_id, Round.ct_team_id,
               Round.t_team_id, Round.ct_buy, Round.t_buy, Round.ct_timeout, Round.t_timeout)
        .order_by(Round.match_map_id, Round.number)
    ).all()  # fmt: skip


def _pairs(rows) -> dict[tuple, tuple[int, int]]:
    """``{(my buy, their buy, my side): (Rounds, won)}`` over every Team."""
    out: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        if not r.winner_team_id or not r.ct_buy or not r.t_buy:
            continue
        for side, mine, theirs, team in (("ct", r.ct_buy, r.t_buy, r.ct_team_id),
                                         ("t", r.t_buy, r.ct_buy, r.t_team_id)):  # fmt: skip
            cell = out[(mine, theirs, side)]
            cell[0] += 1
            cell[1] += r.winner_team_id == team
    return {k: (n, w) for k, (n, w) in out.items()}


def _situations(rows, pairs) -> list[dict]:
    """Every Round after a streak: who streaked, how long, whether they won it,
    what their buys expected, and whether the other Team called a timeout."""
    out = []
    streak_team, streak = None, 0
    current_map = None
    for r in rows:
        if r.match_map_id != current_map:
            current_map, streak_team, streak = r.match_map_id, None, 0
        if (
            streak >= STREAK and streak_team and r.number not in PISTOL_ROUNDS
            and r.winner_team_id and r.ct_buy and r.t_buy
        ):  # fmt: skip
            side = "ct" if r.ct_team_id == streak_team else "t"
            mine, theirs = (r.ct_buy, r.t_buy) if side == "ct" else (r.t_buy, r.ct_buy)
            n, won = pairs.get((mine, theirs, side), (0, 0))
            expected = (won + PRIOR * 0.5) / (n + PRIOR)
            their_timeout = r.t_timeout if side == "ct" else r.ct_timeout
            out.append({
                "streak": streak, "won": r.winner_team_id == streak_team,
                "expected": expected, "timeout": their_timeout,
            })  # fmt: skip
        if r.winner_team_id:
            if r.winner_team_id == streak_team:
                streak += 1
            else:
                streak_team, streak = r.winner_team_id, 1
    return out


def _row(key: str, cases: list[dict]) -> dict | None:
    if not cases:
        return None
    won = sum(1 for c in cases if c["won"])
    low, high = stats.wilson(won, len(cases))
    expected = sum(c["expected"] for c in cases) / len(cases)
    return {
        "key": key, "label": GROUPS[key], "n": len(cases),
        "observed": round(won / len(cases), 3), "expected": round(expected, 3),
        "residual": round(won / len(cases) - expected, 3),
        "low": round(low - expected, 3), "high": round(high - expected, 3),
    }  # fmt: skip


def study() -> list[dict]:
    """The Pool's streaks against their buys, one row per group."""

    def compute():
        rows = _rows()
        cases = _situations(rows, _pairs(rows))
        groups = {
            "all": cases,
            "short": [c for c in cases if c["streak"] < LONG],
            "long": [c for c in cases if c["streak"] >= LONG],
            "timeout": [c for c in cases if c["timeout"] is True],
            "no_timeout": [c for c in cases if c["timeout"] is False],
        }
        return [r for k, v in groups.items() if (r := _row(k, v))]

    key = f"momentum:v{MOMENTUM_SCHEMA}:{pool_cache.parse_stamp()}"
    return pool_cache.remember(key, compute)
