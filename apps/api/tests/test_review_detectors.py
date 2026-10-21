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


def _bare_round(tracks, sides, *, won, plant=None, site=""):
    """A Round Review with only what the RV-12 timing detectors read: ten ticks a
    second, site A at the origin and B 3000 units east."""
    from types import SimpleNamespace

    from app.services import review

    r = object.__new__(review._RoundReview)
    r.i = SimpleNamespace(sites={"A": (0.0, 0.0, 0.0), "B": (3000.0, 0.0, 0.0)},
                          map_name="de_mirage", callout=lambda pos: "")  # fmt: skip
    r.rnd = SimpleNamespace(winner_side=won, bomb_site=site, ct_team_id=1, t_team_id=2)
    r.n, r.rate, r.start, r.end = 1, 10, 0, 1150
    r.tracks, r.side, r.kills, r.plant, r.findings = tracks, sides, [], plant, []
    return r


def _walk(*legs, side):
    """A Track standing at each (from tick, x, y) in turn."""
    import numpy as np

    from app.services import review

    ticks, xs, ys = (np.array(column, dtype=float) for column in zip(*legs, strict=True))
    zero = np.zeros(len(legs))
    hp = np.full(len(legs), 100)
    return review.Track(ticks.astype(np.int64), xs, ys, zero, hp, zero, zero, [""] * len(legs),
                        side=side)  # fmt: skip


@pytest.mark.parametrize(("arrive", "late"), [(1000, True), (600, False)])
def test_reaching_a_site_with_the_clock_nearly_out_is_a_late_execute(monkeypatch, arrive, late):
    """Two Ts reach A 100 s in (15 s left), one CT alive, and lose; at 60 s in it is no Finding."""
    from app.services import review, winprob

    monkeypatch.setattr(review._RoundReview, "state", lambda self, alive, tick: winprob.State(
        ct_alive=1, t_alive=2, ct_equip=4000, t_equip=8000, planted=False,
        seconds_left=winprob.ROUND_SECONDS - tick / self.rate, map_name="de_mirage"))  # fmt: skip
    tracks = {
        "t1": _walk((0, 1500, 2000), (arrive, 0, 0), side="t"),
        "t2": _walk((0, 1500, 2100), (arrive, 50, 0), side="t"),
        "c1": _walk((0, 0, 300), side="ct"),
    }
    r = _bare_round(tracks, {"t1": "t", "t2": "t", "c1": "ct"}, won="ct")
    r.late_execute()
    found = [f for f in r.findings if f["code"] == "late_execute"]
    assert bool(found) == late
    if late:
        f = found[0]
        assert f["sids"] == ["t1", "t2"] and f["facts"]["site"] == "A"
        assert f["facts"]["left"] == 15.0 and f["swing"] <= 0


@pytest.mark.parametrize(("leaves", "early"), [(650, True), (300, False), (None, False)])
def test_leaving_the_site_the_ts_then_hit_is_an_early_rotate(leaves, early):
    """c1 holds A 20 s in and is near B 15 s before the Ts reach A (80 s) and plant;
    gone 50 s before, it was the setup; staying, nothing."""
    c1 = [(0, 100, 0), (leaves, 2800, 0)] if leaves else [(0, 100, 0)]
    tracks = {
        "c1": _walk(*c1, side="ct"),
        "t1": _walk((0, 1500, 3000), (800, 0, 0), side="t"),
    }
    r = _bare_round(tracks, {"c1": "ct", "t1": "t"}, won="t", plant=900, site="A")
    r.early_rotate()
    found = [f for f in r.findings if f["code"] == "early_rotate"]
    assert bool(found) == early
    if early:
        assert found[0]["sids"] == ["c1"] and found[0]["facts"]["lead"] == 15.0
