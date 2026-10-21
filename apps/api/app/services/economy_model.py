"""What a buy decision is worth, read off every Team's Rounds (docs/plans/05 TM-8).

The full model of the plan (money Round by Round, a dynamic programme over
MR12's scores) waits for more data; this is its empirical core. For the spots
where Teams choose, it takes every Pool Round and asks what the choice was worth
over that Round and the next (:data:`HORIZON`): the Rounds a Team won, on
average, when it forced and when it saved. A Team's habit is then set beside
the better choice, and only a gap past :data:`MIN_GAP` Rounds with
:data:`MIN_SPOTS` of the Team's own spots is said (TM-8's "Optimal Spending
Error", measured rather than simulated).

Spots: the 2nd Round after a pistol lost (force, or save), and a Round after a
lost full buy (force, or save).
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from app.models import Round
from app.services import pool_cache
from app.services.analysis_store import PISTOL_ROUNDS
from app.services.dbctx import db

ECONOMY_SCHEMA = 1
HORIZON = 2  # this Round and the next
CHOICES = ("force", "eco")
MIN_POOL = 30  # Pool spots behind a choice before its worth is said
MIN_SPOTS = 4
MIN_GAP = 0.15  # Rounds over the two
SPOTS = ("after_pistol_loss", "after_full_loss")


def _spots(rows) -> list[tuple[str, int, str, int]]:
    """``(spot, team, choice, Rounds won of the next HORIZON)`` for every Team
    in every Match Map. ``rows`` are Rounds in order."""
    by_map: dict[int, dict[int, tuple]] = defaultdict(dict)
    for r in rows:
        by_map[r.match_map_id][r.number] = r
    out = []
    for rounds in by_map.values():
        for n, r in rounds.items():
            prev = rounds.get(n - 1)
            if prev is None or prev.winner_team_id is None:
                continue
            nxt = [rounds.get(n + k) for k in range(HORIZON)]
            if not all(nxt):
                continue
            for team, buy, prev_buy in (
                (r.ct_team_id, r.ct_buy, _buy(prev, r.ct_team_id)),
                (r.t_team_id, r.t_buy, _buy(prev, r.t_team_id)),
            ):
                if not team or buy not in CHOICES or prev.winner_team_id == team:
                    continue
                if prev.number in PISTOL_ROUNDS:
                    spot = "after_pistol_loss"
                elif prev_buy == "full":
                    spot = "after_full_loss"
                else:
                    continue
                won = sum(1 for x in nxt if x.winner_team_id == team)
                out.append((spot, team, buy, won))
    return out


def _buy(r, team: int) -> str:
    return r.ct_buy if r.ct_team_id == team else r.t_buy if r.t_team_id == team else ""


def _rows():
    return db().execute(
        select(Round.match_map_id, Round.number, Round.winner_team_id, Round.ct_team_id,
               Round.t_team_id, Round.ct_buy, Round.t_buy)
        .order_by(Round.match_map_id, Round.number)
    ).all()  # fmt: skip


def pool() -> dict[str, dict[str, list[float]]]:
    """``{spot: {choice: [spots, Rounds won over the horizon]}}`` over every Team."""

    def compute():
        out: dict[str, dict[str, list[float]]] = {s: {c: [0, 0] for c in CHOICES} for s in SPOTS}
        for spot, _team, choice, won in _spots(_rows()):
            out[spot][choice][0] += 1
            out[spot][choice][1] += won
        return out

    key = f"economy:v{ECONOMY_SCHEMA}:{pool_cache.parse_stamp()}"
    return pool_cache.remember(key, compute)


def team(team_id: int, round_rows=None) -> list[dict]:
    """The Team's choice in each spot against what each choice is worth in the Pool,
    said only where its habit costs it :data:`MIN_GAP` Rounds or more."""
    worth = pool()
    mine: dict[str, dict[str, int]] = {s: {c: 0 for c in CHOICES} for s in SPOTS}
    for spot, t, choice, _won in _spots(round_rows if round_rows is not None else _rows()):
        if t == team_id:
            mine[spot][choice] += 1
    out = []
    for spot in SPOTS:
        taken = mine[spot]
        n = sum(taken.values())
        values = {
            c: worth[spot][c][1] / worth[spot][c][0]
            for c in CHOICES
            if worth[spot][c][0] >= MIN_POOL
        }
        if n < MIN_SPOTS or len(values) < len(CHOICES):
            continue
        habit = max(CHOICES, key=lambda c: taken[c])
        best = max(CHOICES, key=lambda c: values[c])
        gap = values[best] - values[habit]
        out.append({
            "spot": spot, "habit": habit, "times": taken[habit], "of": n,
            "best": best, "worth": {c: round(values[c], 2) for c in CHOICES},
            "pool": {c: worth[spot][c][0] for c in CHOICES},
            "gap": round(gap, 2), "costly": habit != best and gap >= MIN_GAP,
        })  # fmt: skip
    return out
