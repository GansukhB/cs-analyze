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
    assert not {"team_flash", "team_flashed_death", "saw_first_lost", "unfinished",
                "blind_unpunished"} & set(codes)  # fmt: skip


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
    sites = {"A": (0.0, 0.0, 0.0), "B": (3000.0, 0.0, 0.0)}
    r.i = SimpleNamespace(sites=sites, map_name="de_mirage", callout=lambda pos: "",
                          usual_on_site={})  # fmt: skip
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


def _late_round(*, reason, kit=False, plant=500):
    """Two Ts against one CT; the Ts die 10 and 32 s after a plant at 50 s, the
    bomb goes off at 90 s, and the CT stands 230 units (one second) from it."""
    tracks = {
        "c1": _walk((0, 230, 0), side="ct"),
        "t1": _walk((0, 0, 100), side="t"),
        "t2": _walk((0, 0, -100), side="t"),
    }
    r = _bare_round(tracks, {"c1": "ct", "t1": "t", "t2": "t"},
                    won="t" if reason == "bomb_exploded" else "ct", plant=plant)  # fmt: skip
    r.rnd.end_reason, r.end = reason, 900
    r.kit, r.bomb_pos = ({"c1"} if kit else set()), (0.0, 0.0, 0.0)
    r.kills = [
        {"victim": "t1", "tick": 600, "credits": {"t1": -0.2}},
        {"victim": "t2", "tick": 820, "credits": {"t2": -0.3}},
    ]
    return r


def test_the_ts_running_out_of_time_alive_is_the_teams_mistake():
    r = _late_round(reason="time_ran_out", plant=None)
    r.kills = []
    r.team_mistakes()
    (f,) = [f for f in r.findings if f["code"] == "time_out"]
    assert sorted(f["sids"]) == ["t1", "t2"] and f["facts"] == {"side": "t", "ts": 2, "cts": 1}
    done = _late_round(reason="t_killed", plant=None)
    done.team_mistakes()
    assert not done.findings


@pytest.mark.parametrize("kit", [False, True])
def test_eight_seconds_left_is_a_kit_short_or_a_defuse_missed(kit):
    """8 s left and one to walk: with a kit the defuse fitted and nobody went;
    without one it never could, and the kit was the Mistake."""
    r = _late_round(reason="bomb_exploded", kit=kit)
    r.team_mistakes()
    r.defuse_chance()
    codes = {f["code"]: f for f in r.findings}
    assert ("kitless" in codes) is not kit and ("defuse_chance" in codes) is kit
    if kit:
        assert codes["defuse_chance"]["facts"] == {"left": 8.0, "need": 6.0, "kit": True}
    else:
        assert codes["kitless"]["facts"]["left"] == 8.0 and codes["kitless"]["sids"] == ["c1"]


@pytest.mark.parametrize(("peak", "found"), [(0.9, True), (0.7, False)])
def test_a_round_won_on_paper_and_lost_is_an_advantage_lost(peak, found):
    """The Ts reach their peak 30 s in, then both die and the CT wins."""
    r = _late_round(reason="t_killed", plant=None)
    r.wp = [(0.0, 0.5), (30.0, 1 - peak), (60.0, 0.9)]
    r.advantage_lost(r.kills)
    lost = [f for f in r.findings if f["code"] == "advantage_lost"]
    assert bool(lost) == found
    if found:
        assert lost[0]["sids"] == ["t1", "t2"] and lost[0]["swing"] == -0.9
        assert lost[0]["facts"]["men"] == [2, 1] and lost[0]["side"] == "t"


def test_an_enemy_hurt_and_left_alive_who_then_kills_is_unfinished(db, inferno):  # noqa: F811
    """a1 puts 60 into b2 at 1600 and leaves him on 40; b2 kills a1 at 1700."""
    import polars as pl

    def hurt(frames):
        row = {"tick": 1600, "attacker_steamid": 11, "victim_steamid": 22, "attacker_side": "ct",
               "victim_side": "t", "weapon": "m4a1", "dmg_health_real": 60, "health": 40,
               "round_num": 1}  # fmt: skip
        frames["damages"] = pl.concat(
            [frames["damages"], pl.DataFrame([row], schema=frames["damages"].schema)]
        )

    f = _codes(_review(db, inferno, tweak=hurt))["unfinished"][0]
    assert f["sids"] == ["11", "22"] and f["facts"]["dealt"] == 60 and f["facts"]["hp"] == 40
    assert f["facts"]["victims"] == ["11"] and f["swing"] < 0


def test_a_blinded_enemy_left_alive_is_a_flash_unpunished(db, inferno, bent):  # noqa: F811
    """b1's flash holds a1 2.5 s; with his death moved past it, nobody punished it."""
    import polars as pl

    def later(frames):
        frames["kills"] = frames["kills"].with_columns(
            pl.when(pl.col("victim_steamid") == 11)
            .then(1900)
            .otherwise(pl.col("tick"))
            .alias("tick")
        )

    bent(DIES=(11, 1900))
    f = _codes(_review(db, inferno, tweak=later))["blind_unpunished"][0]
    assert f["sids"][1] == "11" and f["facts"]["thrower"] == "21"
    assert f["facts"]["enemies"] == [{"sid": "11", "seconds": 2.5}]


def test_the_rounds_first_kill_for_the_side_that_won_is_an_entry(db, inferno, bent):  # noqa: F811
    """With a1's death taken out, a2's kill on b2 opens the Round, and the CTs win it."""
    import polars as pl

    def a1_lives(frames):
        frames["kills"] = frames["kills"].filter(pl.col("victim_steamid") != 11)

    bent(DIES=(11, 10**9))
    codes = _codes(_review(db, inferno, tweak=a1_lives))
    entry = codes["entry"][0]
    assert entry["sids"][0] == "12" and entry["swing"] >= 0.12
    assert "clutch" not in codes  # a1 is alive: no clutch


def test_he_damage_that_lets_a_teammate_finish_is_a_utility_kill(db, inferno):  # noqa: F811
    """a1's HE puts 40 into b1 at 1500; a2 kills b1 at 2000, 8 s later."""
    import polars as pl

    def he(frames):
        row = {"tick": 1500, "attacker_steamid": 11, "victim_steamid": 21, "attacker_side": "ct",
               "victim_side": "t", "weapon": "hegrenade", "dmg_health_real": 40, "health": 60,
               "round_num": 1}  # fmt: skip
        more = pl.DataFrame([row], schema=frames["damages"].schema)
        frames["damages"] = pl.concat([frames["damages"], more])
        b1 = pl.col("victim_steamid") == 21
        frames["kills"] = frames["kills"].with_columns(
            pl.when(b1).then(2000).otherwise(pl.col("tick")).alias("tick")
        )

    f = _codes(_review(db, inferno, tweak=he))["nade_damage_kill"][0]
    assert f["sids"] == ["11", "12", "21"] and f["facts"]["nade"] == "he"
    assert f["facts"]["dealt"] == 40 and f["facts"]["killer"] == "12"


@pytest.mark.parametrize(
    ("held_by", "won", "found"), [(3, "ct", True), (2, "ct", False), (3, "t", False)]
)
def test_ts_walking_into_a_stack_and_the_cts_who_read_it(held_by, won, found):
    """Three CTs hold A (the other two at B) when two Ts reach A at 80 s."""
    tracks = {
        f"c{i}": _walk((0, 100 * i if i <= held_by else 3000, 200), side="ct") for i in range(1, 6)
    }
    tracks |= {"t1": _walk((0, 1500, 3000), (800, 0, 0), side="t"),
               "t2": _walk((0, 1500, 3100), (800, 50, 0), side="t")}  # fmt: skip
    sides = {sid: ("ct" if sid.startswith("c") else "t") for sid in tracks}
    r = _bare_round(tracks, sides, won=won)
    r.stack()
    codes = {f["code"]: f for f in r.findings}
    assert ("stack_read" in codes) is found and ("into_stack" in codes) is found
    if found:
        assert codes["stack_read"]["sids"] == ["c1", "c2", "c3"]
        facts = codes["into_stack"]["facts"]
        assert facts == {"side": "t", "site": "A", "cts": 3, "ts": 2, "t": 80.0}
        # A Team that keeps three on A as its setup (Nuke) has not stacked it.
        r = _bare_round(tracks, sides, won=won)
        r.rnd.ct_team_id, r.i.usual_on_site = 1, {(1, "A"): 3.0}
        r.stack()
        assert not r.findings
