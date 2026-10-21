"""Who holds which spot: a Team's five slots on a Map and Side (docs/plans/04 PL-4).

Every Round in which all five of the Team stood alive 20 s after freeze end (the
Setup snapshot) gives five positions. The Team's slots are the five places its
Players fill Round after Round, found the way Bialkowski et al. assign roles in a
formation: start from k-means++ over every position, then repeat, in each Round
matching its five to the five slots with the Hungarian algorithm (by distance,
height counted :data:`Z_WEIGHT` times so floors stay apart) and moving each slot
to the middle of what was matched to it. Each slot is named by the Spot most of
its positions stand in and says which Players filled it how often, so "who
anchors B on Nuke" is a share of Rounds, not a guess from one demo.
"""

from __future__ import annotations

from collections import Counter

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

from app.services import spots

FIVE = 5
MIN_ROUNDS = 8
ITERATIONS = 20
Z_WEIGHT = 2.0
SEED = 7
MIN_SHARE = 0.1  # a Player in fewer of a slot's Rounds than this is not named
LEAN_ORDER = {"A": 0, "mid": 1, "B": 2, "": 3}


def _start(points: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """k-means++: spread the first five slots over the positions."""
    chosen = [points[rng.integers(len(points))]]
    for _ in range(FIVE - 1):
        d = cdist(points, np.array(chosen)).min(axis=1) ** 2
        chosen.append(points[rng.choice(len(points), p=d / d.sum())] if d.sum() else points[0])
    return np.array(chosen)


def fit(rounds: list[list[tuple]]) -> tuple[np.ndarray, list[np.ndarray]]:
    """The five slots and, per Round, which slot each of its five took.

    ``rounds`` holds five ``(x, y, z)`` per Round."""
    per_round = [np.array([[x, y, (z or 0.0) * Z_WEIGHT] for x, y, z in five]) for five in rounds]
    centres = _start(np.vstack(per_round), np.random.default_rng(SEED))
    taken: list[np.ndarray] = []
    for _ in range(ITERATIONS):
        taken = []
        for points in per_round:
            rows, cols = linear_sum_assignment(cdist(points, centres))
            slot = np.empty(FIVE, dtype=int)
            slot[rows] = cols
            taken.append(slot)
        moved = np.array([
            np.vstack([p[s == j] for p, s in zip(per_round, taken, strict=True)]).mean(axis=0)
            for j in range(FIVE)
        ])  # fmt: skip
        if np.allclose(moved, centres, atol=1.0):
            break
        centres = moved
    centres[:, 2] /= Z_WEIGHT
    return centres, taken


def team_slots(
    map_name: str, setups: list[list[tuple]], names: dict[int, str], lean
) -> list[dict] | None:
    """A Team's slots on one Side from its Rounds' Setups, each a list of five
    ``(player_id, place, x, y, z)``; None with fewer than :data:`MIN_ROUNDS`.
    ``lean`` says A, B or mid for a position."""
    usable = [five for five in setups if len(five) == FIVE and all(p[2] is not None for p in five)]
    if len(usable) < MIN_ROUNDS:
        return None
    centres, taken = fit([[(x, y, z) for _pid, _place, x, y, z in five] for five in usable])
    out = []
    for j, (cx, cy, cz) in enumerate(centres):
        who: Counter = Counter()
        where: Counter = Counter()
        for five, slot in zip(usable, taken, strict=True):
            pid, place, x, y, z = five[int(np.flatnonzero(slot == j)[0])]
            who[pid] += 1
            where[spots.spot_at(map_name, x, y, z or 0.0, place) or spots.callout_label(place)] += 1
        n = len(usable)
        name, held = where.most_common(1)[0] if where else ("", 0)
        out.append({
            "name": name,
            "lean": lean((cx, cy, cz)),
            "at": [round(float(cx), 1), round(float(cy), 1)],
            "here": round(held / n, 2),
            "players": [{"player_id": pid, "name": names.get(pid, "?"), "share": round(c / n, 2)}
                        for pid, c in who.most_common() if c / n >= MIN_SHARE],
        })  # fmt: skip
    out.sort(key=lambda s: (LEAN_ORDER.get(s["lean"], 3), s["name"]))
    return out
