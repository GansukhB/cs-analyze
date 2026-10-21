"""A Team's five slots 20 s in, Round by Round (docs/plans/04 PL-4)."""

import numpy as np

from app.services import slots

SPOTS = {"A": (0.0, 0.0), "Mid": (1500.0, 0.0), "B": (3000.0, 0.0), "Long": (0.0, 1500.0),
         "Ramp": (3000.0, 1500.0)}  # fmt: skip


def _rounds(n=12, swap_every=4):
    """Players 1-5 each hold one spot; every fourth Round players 4 and 5 swap."""
    rng = np.random.default_rng(1)
    order = list(SPOTS)
    out = []
    for i in range(n):
        held = dict(zip(range(1, 6), order, strict=True))
        if i % swap_every == 0:
            held[4], held[5] = held[5], held[4]
        five = []
        for pid, place in held.items():
            x, y = SPOTS[place]
            five.append((pid, place, x + rng.normal(0, 60), y + rng.normal(0, 60), 0.0))
        out.append(five)
    return out


def test_each_spot_is_a_slot_and_says_who_holds_it():
    names = {i: f"p{i}" for i in range(1, 6)}
    found = slots.team_slots("de_nowhere", _rounds(), names, lambda p: "")
    by_name = {s["name"]: s for s in found}
    assert set(by_name) == set(SPOTS) and all(s["here"] == 1.0 for s in found)
    assert by_name["A"]["players"] == [{"player_id": 1, "name": "p1", "share": 1.0}]
    # Players 4 and 5 swap a third of the time: each slot names both.
    long = {p["name"]: p["share"] for p in by_name["Long"]["players"]}
    assert long == {"p4": 0.75, "p5": 0.25}


def test_too_few_full_rounds_say_nothing():
    rounds = _rounds(n=7)
    assert slots.team_slots("de_nowhere", rounds, {}, lambda p: "") is None
    rounds = _rounds(n=12)
    for five in rounds[:5]:
        five.pop()  # a death before 20 s: four left
    assert slots.team_slots("de_nowhere", rounds, {}, lambda p: "") is None
