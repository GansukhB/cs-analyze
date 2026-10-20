"""Win probability v2 (docs/plans/07 RV-4): fitted on synthetic Rounds, it finds
the health it was given and reports its calibration."""

import math
import random

import pytest

from app.services import winprob


def _samples(n_rounds: int = 1500, seed: int = 3) -> list[winprob.Sample]:
    rng = random.Random(seed)
    out = []
    for r in range(n_rounds):
        ct, t = rng.randint(1, 5), rng.randint(1, 5)
        ct_hp, t_hp = rng.uniform(20, 100) * ct, rng.uniform(20, 100) * t
        z = 0.9 * (ct - t) + 1.5 * (ct_hp / ct - t_hp / t) / 100.0
        won = rng.random() < 1 / (1 + math.exp(-z))
        state = winprob.State(ct, t, 4000.0 * ct, 4000.0 * t, False, rng.uniform(10, 110),
                              ct_hp=ct_hp, t_hp=t_hp, ct_buy="full", t_buy="full")  # fmt: skip
        out.append(winprob.Sample(state, won, 1.0, r // 20))
    return out


def test_v2_finds_the_health_and_reports_its_calibration():
    samples = _samples()
    spec = winprob.fit(samples, folds=3)
    assert spec["features"] == 2 and spec["pre"]["hp"] > 0.5
    pre = spec["metrics"]["pre"]
    assert {"brier", "auc", "ece", "reliability", "by_clock"} <= set(pre)
    assert 0.6 < pre["auc"] <= 1.0 and pre["ece"] < 0.1
    assert sum(b[2] for b in pre["reliability"]) == pytest.approx(1.0, abs=1e-3)
    v1 = winprob.fit(samples, folds=3, version=1)
    assert "hp" not in v1["pre"]
    assert pre["cv_logloss"] < v1["metrics"]["pre"]["cv_logloss"]


def test_a_version_1_model_still_reads_a_version_2_state(monkeypatch):
    spec = {"version": "x", "maps": [], "pre": {"bias": 0.0, "diff": 1.0}, "post": {}}
    monkeypatch.setattr(winprob, "model", lambda: spec)
    state = winprob.State(3, 2, 12000.0, 8000.0, False, 60.0, ct_hp=300.0, t_hp=50.0, last=1)
    assert winprob.ct_win(state) == pytest.approx(1 / (1 + math.exp(-1.0)))


def test_the_defuse_race_is_capped():
    post = winprob.State(2, 2, 0.0, 0.0, True, 30.0, race=-80.0)
    assert winprob.features(post, [])["race"] == -winprob.RACE_CAP
