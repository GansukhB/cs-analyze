"""Between Maps (docs/plans/06 GP-4): what the opponent did differently on the
Map they just played, against their other Maps."""

from app.services import between
from app.services.review_pool import Tally


def _tally(mm, side, rounds, *, openings=(), forces=0, untraded=0, swings=None) -> Tally:
    t = Tally(mm=mm, match=mm, num=1, map="de_mirage", team=8, side=side, sight=True)
    t.rounds = list(range(1, rounds + 1))
    t.events["opening"] = [(n, won, "1", 0.1) for n, won in enumerate(openings, 1)]
    t.events["force"] = [(n, False, None, 1.0) for n in range(2, 2 + forces)]
    t.codes["untraded"] = [(n, 10.0, "1", -0.1, "") for n in range(1, untraded + 1)]
    for sid, values in (swings or {}).items():
        t.players[sid] = list(enumerate(values, 1))
    return t


def _usual(n_maps=6):
    """Six usual Maps on T: half the openings won, two forces, two untraded deaths."""
    return [
        _tally(
            mm,
            "t",
            12,
            openings=[True, False] * 6,
            forces=2,
            untraded=2,
            swings={"1": [0.0, 0.02] * 6},
        )  # fmt: skip
        for mm in range(10, 10 + n_maps)
    ]


def test_a_map_like_their_usual_says_nothing():
    here = [_tally(1, "t", 12, openings=[True, False] * 6, forces=2, untraded=2)]
    assert between._rate_lines(here, _usual()) == []
    assert between._code_lines(here, _usual()) == []


def test_what_they_did_differently_is_said_with_its_usual():
    here = [_tally(1, "t", 12, openings=[True] * 11 + [False], forces=0, untraded=9)]
    rates = {(x["key"], x["more"]) for x in between._rate_lines(here, _usual())}
    assert ("opening", True) in rates and ("force_share", False) in rates
    (untraded,) = [x for x in between._code_lines(here, _usual()) if x["key"] == "untraded"]
    assert untraded["k"] == 9 and untraded["usual"] == round(2 / 12, 3) and not untraded["good"]


def test_a_player_hot_on_the_map_just_played():
    here = [_tally(1, "t", 12, swings={"1": [0.08] * 12})]
    (p,) = between._players(here, _usual(), {"1": "910"})
    assert p["name"] == "910" and p["hot"] and not p["cold"] and p["here"] == 0.08


def test_findings_are_counted_by_the_rounds_they_fell_in():
    # Four untraded deaths in each of five Rounds: five Rounds of twelve, not twenty.
    here = [_tally(1, "t", 12)]
    here[0].codes["untraded"] = [(n, 10.0, "1", -0.1, "") for n in range(1, 6) for _ in range(4)]
    (untraded,) = [x for x in between._code_lines(here, _usual()) if x["key"] == "untraded"]
    assert untraded["k"] == 5 and untraded["n"] == 12
