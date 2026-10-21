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


def test_a_role_kpi_is_called_only_on_enough_evidence():
    from app.services import roles

    cohort = {
        "kpis": {"opening_win_pct": {"mean": 50.0, "sd": 8.0, "n": 6}},
        "rates": {
            "opening_win_pct": [(x, 40.0, pid) for pid, x in enumerate((18, 20, 22, 19, 21))]
        },
    }
    few = {"rounds": 24, "opening_attempts": 5, "opening_win_pct": 100.0}
    many = {"rounds": 480, "opening_attempts": 200, "opening_win_pct": 72.0}
    stat = cohort["kpis"]["opening_win_pct"]
    assert roles._judge(few, "opening_win_pct", stat, cohort, None)["verdict"] == "par"
    judged = roles._judge(many, "opening_win_pct", stat, cohort, None)
    assert judged["verdict"] == "above" and judged["shrunk"] < 72.0


def test_a_card_says_only_what_passed():
    from app.services import mn

    proven = [
        {"side": "ct", "kpi": "adr", "label": "ADR", "shrunk": 82.318, "cohort_mean": 74.78,
         "verdict": "above"},
    ]  # fmt: skip
    reviewed = {
        "maps": 12,
        "swing": {"per_round": -0.021, "low": -0.035, "high": -0.004, "clear": True},
        "weaknesses": [{"label": "Trade-гүй", "per24": 3.1, "pool_per24": 2.6, "count": 40}],
        "tendencies": [{"label": "Entry", "per24": 2.2, "pool_per24": 1.5, "count": 30}],
    }
    out = mn.card_lines(proven, reviewed)
    assert out["strengths"] == ["CT: ADR 82.3 (үүргийн жишиг 74.8)"]
    assert out["weaknesses"][0].endswith("бусдаас доогуур") and len(out["weaknesses"]) == 2
    assert out["tendencies"][0].startswith("Entry: 24 раундад 2.2")


def test_a_head_to_head_drop_is_called_only_past_chance():
    from app.services import gameplan

    own = {"t_win_pct": 55.0, "t_rounds": 600, "maps": 50, "rounds": 1200}
    big = {"t_win_pct": 30.0, "t_rounds": 120, "maps": 10, "rounds": 240}
    few = {"t_win_pct": 30.0, "t_rounds": 6, "maps": 1, "rounds": 12}
    assert gameplan._delta_test("t_win_pct", own, big)["clear"]
    assert not gameplan._delta_test("t_win_pct", own, few)["enough"]
    small = {"t_win_pct": 52.0, "t_rounds": 120, "maps": 10, "rounds": 240}
    assert not gameplan._delta_test("t_win_pct", own, small)["clear"]
    adr_own, adr_vs = {"adr": 80.0, "rounds": 1200}, {"adr": 60.0, "rounds": 96}
    assert gameplan._delta_test("adr", adr_own, adr_vs)["clear"]


def test_the_forecasts_reliability_by_band_of_our_chance():
    """FC-4: graded series per band, with the share won and its Wilson range."""
    from app.services import forecast_store

    calls = [(0.7, True), (0.72, True), (0.68, False), (0.5, True), (0.3, False)]
    bands = {b["lo"]: b for b in forecast_store.reliability(calls)}
    assert set(bands) == {0.0, 0.45, 0.65}
    top = bands[0.65]
    assert (top["n"], top["won"], top["mean_p"]) == (3, 2, 0.7)
    assert top["low"] < 2 / 3 < top["high"]
    assert stats.wilson(0, 0) == (0.0, 1.0)
    low, high = stats.wilson(50, 100)
    assert round(low, 2) == 0.44 and round(high, 2) == 0.56


def test_a_round_is_pistol_match_point_close_or_other():
    """PL-10's kinds of Round, from the score before it."""
    from app.services import pressure

    assert pressure._kind(1, 0, 0) == "pistol" and pressure._kind(13, 6, 6) == "pistol"
    assert (
        pressure._kind(20, 12, 7) == "match_point" and pressure._kind(24, 11, 12) == "match_point"
    )
    assert pressure._kind(21, 10, 10) == "close" and pressure._kind(19, 9, 9) == "close"
    assert pressure._kind(18, 9, 8) == "other" and pressure._kind(20, 12, 5) == "match_point"
    assert pressure._kind(28, 14, 13) == "close"  # overtime: no match point counted


def test_a_buy_decision_is_worth_the_rounds_it_wins_over_two():
    """TM-8: spots after a pistol lost and after a full buy lost, and their worth."""
    from types import SimpleNamespace as R

    from app.services import economy_model

    def rnd(n, winner, ct_buy, t_buy):
        return R(match_map_id=1, number=n, winner_team_id=winner, ct_team_id=10, t_team_id=20,
                 ct_buy=ct_buy, t_buy=t_buy)  # fmt: skip

    rows = [
        rnd(1, 10, "pistol", "pistol"),  # 20 loses the pistol
        rnd(2, 20, "full", "force"),  # 20 forces and wins it
        rnd(3, 10, "full", "eco"),
        rnd(4, 20, "full", "full"),  # 10 loses a full buy
        rnd(5, 10, "eco", "full"),  # 10 saves, then wins 5
        rnd(6, 20, "full", "full"),
    ]
    spots = economy_model._spots(rows)
    assert ("after_pistol_loss", 20, "force", 1) in spots
    assert ("after_full_loss", 10, "eco", 1) in spots
    assert all(s[2] in economy_model.CHOICES for s in spots)


def test_a_streaks_next_round_is_set_against_its_buys():
    """TM-11: Team 10 wins Rounds 2-4, then plays Round 5 with the other side's timeout."""
    from types import SimpleNamespace as R

    from app.services import momentum

    def rnd(n, winner, ct_to=None, t_to=None):
        return R(match_map_id=1, number=n, winner_team_id=winner, ct_team_id=10, t_team_id=20,
                 ct_buy="full", t_buy="full", ct_timeout=ct_to, t_timeout=t_to)  # fmt: skip

    rows = [rnd(1, 20), rnd(2, 10), rnd(3, 10), rnd(4, 10), rnd(5, 10, t_to=True), rnd(6, 20)]
    cases = momentum._situations(rows, momentum._pairs(rows))
    assert [(c["streak"], c["won"], c["timeout"]) for c in cases] == [(3, True, True),
                                                                      (4, False, None)]  # fmt: skip
    # full v full on CT: 4 of 6 won by CT here, pulled toward 50% by 10 pseudo-Rounds.
    assert round(cases[0]["expected"], 3) == round((4 + 5) / (6 + 10), 3)
    row = momentum._row("all", cases)
    assert row["n"] == 2 and row["observed"] == 0.5 and row["low"] < row["residual"] < row["high"]
