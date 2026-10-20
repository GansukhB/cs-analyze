"""The shared small-sample statistics (app/services/stats.py)."""

import pytest

from app.services import stats


def test_a_prior_is_as_strong_as_the_pool_agrees():
    # Ten Teams that all retake about 24%: their spread is chance, so the prior is
    # as strong as the floor on a true spread allows.
    alike = stats.beta_prior([(2, 9), (3, 12), (2, 8), (2, 10), (3, 11)] * 2)
    assert alike.mean == pytest.approx(0.24)
    assert alike.strength == pytest.approx(0.24 * 0.76 / stats.MIN_SPREAD**2 - 1)
    # Teams far apart: a weak prior, so a Team's own events decide.
    apart = stats.beta_prior([(1, 20), (18, 20), (2, 20), (17, 20)])
    assert apart.strength < 5
    assert stats.beta_prior([(3, 10)]) is None


def test_two_of_nine_retakes_is_not_a_weakness_when_everyone_is_low():
    prior = stats.beta_prior([(2, 9), (3, 12), (2, 8), (2, 10), (3, 11), (1, 7), (4, 13)])
    two_of_nine = stats.shrink(2, 9, prior)
    assert not two_of_nine.clear()
    # Zero of twenty-five against a Pool near 24% is.
    assert stats.shrink(0, 25, prior).clear() and not stats.shrink(0, 25, prior).above


def test_eight_plants_split_six_two_is_not_a_site_habit():
    prior = stats.beta_prior([(10, 20), (11, 20), (9, 20), (12, 20), (8, 20)])  # Pool ~50% A
    assert not stats.shrink(6, 8, prior).clear()
    assert stats.shrink(19, 20, prior).clear()


def test_rounds_of_one_map_count_for_less():
    assert stats.effective_n(24, 24) == pytest.approx(24 / (1 + 23 * stats.ROUND_CORRELATION))
    assert stats.effective_n(12, 12) == pytest.approx(6.6, abs=0.1)
    assert stats.effective_n(0, 24) == 0


def test_recency_halves_at_the_half_life():
    assert stats.recency(0, 90) == 1 and stats.recency(90, 90) == pytest.approx(0.5)


def test_benjamini_hochberg_keeps_the_strong_ones():
    assert stats.bh([0.001, 0.02, 0.04, 0.5], q=0.1) == [True, True, True, False]
    assert stats.bh([0.2, 0.3], q=0.1) == [False, False]


def test_bootstrap_by_group():
    maps = [[1, 1, 0], [1, 0, 0], [1, 1, 1], [0, 0, 1]]
    low, high = stats.bootstrap(maps, lambda gs: sum(sum(g) for g in gs) / sum(len(g) for g in gs))
    assert 0.2 < low < 0.6 < high < 0.95


def test_a_stratified_gap_beats_chance_only_when_it_is_there():
    # Within each stratum the flagged rows lose far more often: a real gap.
    rows = [(s, i % 4 == 0, (i % 4 != 0) or i % 8 == 0) for s in ("ct", "t") for i in range(80)]
    gap, p, n = stats.stratified_gap(rows, draws=500)
    assert n == 40 and gap == pytest.approx(0.5) and p < 0.01
    # Same success rate for both: no gap, and chance explains it.
    flat = [(s, i % 2 == 0, i % 3 == 0) for s in ("ct", "t") for i in range(60)]
    gap, p, _n = stats.stratified_gap(flat, draws=500)
    assert abs(gap) < 0.1 and p > 0.2
    # A stratum with only flagged rows says nothing.
    assert stats.stratified_gap([("x", True, False)] * 5)[2] == 0
