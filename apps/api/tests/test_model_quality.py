"""The committed models still beat their baselines (docs/plans/11 OPS-9).

Refitting writes the metrics next to the parameters (``rating_params.json``,
``winprob.json``); a refit that does worse than the simple rule it replaces
fails CI here instead of reaching the pages.
"""

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "app" / "data"


def test_the_rating_beats_valves_points_and_a_coin():
    found = json.loads((DATA / "rating_params.json").read_text())
    test, baselines = found["test"], found["baselines"]
    assert test["log_loss"] < baselines["vrs_points"]["log_loss"] < baselines["coin"]["log_loss"]
    assert found["vs_vrs_points"]["low"] > 0  # the gain's interval clears zero
    # Its 60% calls come true about 60% of the time.
    for band in found["reliability"]:
        if band["n"] >= 200:
            assert band["low"] - 0.05 <= (band["lo"] + band["hi"]) / 2 <= band["high"] + 0.05


def test_the_win_probability_beats_the_man_count_alone():
    found = json.loads((DATA / "winprob.json").read_text())
    for phase in ("pre", "post"):
        m = found["metrics"][phase]
        assert m["cv_logloss"] < m["cv_logloss_man_count_only"]
        assert m["ece"] < 0.03 and m["auc"] > 0.8
