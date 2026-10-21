"""Detectors the hand-built Round of test_review shows once it is bent a little
(docs/plans/07 RV-3): each test changes one thing about that Round and checks
the Finding it should make, and that the Round without the change has none."""

import pytest

from tests import test_review as base
from tests.test_review import _codes, _review, inferno  # noqa: F401  (fixture)


@pytest.fixture
def bent(monkeypatch):
    """Change the Round's module-level facts for one test."""

    def apply(**changes):
        for name, value in changes.items():
            monkeypatch.setitem(getattr(base, name), *value)

    return apply


def test_the_round_as_built_has_none_of_them(db, inferno):  # noqa: F811
    codes = _codes(_review(db, inferno))
    assert not {"team_flash", "team_flashed_death", "saw_first_lost"} & set(codes)


def test_a_long_team_flash_is_a_finding(db, inferno, bent):  # noqa: F811
    bent(BLIND=(22, 4.5))  # b1's own flash holds b2 blind 4.5 s
    found = _codes(_review(db, inferno))["team_flash"]
    assert found[0]["sids"][:2] == ["21", "22"]


def test_dying_blind_from_a_teammates_flash_is_a_mistake(db, inferno, bent):  # noqa: F811
    # b2 stays blind past the moment a2 kills him (10 s from the flash at 1640).
    bent(BLIND=(22, 10.0))
    codes = _codes(_review(db, inferno))
    death = codes["team_flashed_death"][0]
    assert death["sids"][:2] == ["21", "22"] and death["swing"] < 0


def test_seeing_an_enemy_first_and_losing_the_duel_needs_sightings(db, inferno):  # noqa: F811
    """b1 has a2 in view 1.5 s before a2 kills him, and a2 never saw b1 first."""
    lost = _codes(_review(db, inferno, sightings=True))["saw_first_lost"][0]
    assert lost["sids"][:2] == ["21", "12"] and lost["facts"]["lead"] > 0


def test_a_t_who_stands_apart_most_rounds_lurks():
    """RV-12: three T; one is 2000 units from the others 30 s into 8 of 10 Rounds."""
    from types import SimpleNamespace

    import numpy as np

    from app.services import review

    def track(x):
        ticks = np.array([0, 10_000], dtype=np.int64)
        flat = np.array([x, x], dtype=float)
        zero = np.zeros(2)
        return review.Track(ticks, flat, zero, zero, np.array([100, 100]), zero, zero,
                            ["A", "A"], side="t")  # fmt: skip

    rounds, tracks = [], {}
    for n in range(1, 11):
        rounds.append(SimpleNamespace(number=n, freeze_end_tick=0, end_tick=9_000))
        far = 2000.0 if n <= 8 else 100.0
        tracks[n] = {"1": track(0.0), "2": track(50.0), "3": track(far)}
    inputs = SimpleNamespace(rounds=rounds, tracks=tracks, player_rounds={}, rate=64)
    assert review._lurkers(inputs) == {"3"}
    # Fewer than six T Rounds says nothing.
    inputs.rounds = rounds[:5]
    assert review._lurkers(inputs) == set()
