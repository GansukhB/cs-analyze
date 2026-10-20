"""Valve's standings read, and the Rating replayed over them (DATA-2, FC-1, FC-5)."""

from datetime import date

import pytest

from app.models import SeriesResult, VrsStanding
from app.services import rating, vrs_import

ROSTER = "Annihilation, Bart4k, bexyz, controlez, Cozen"
HEAD = "| Match Played | Match ID | Date | Opponent | W/L | Age Weight | Event Weight | "
HEAD += "Bounty Collected | Opponent Network | LAN Wins | H2H Adj. | Roster |"


def _row(played, match_id, day, opponent, wl, lan):
    cells = [played, match_id, day, opponent, wl, "1.000", "-", "-", "-", lan, "0", ROSTER]
    return "| " + " | ".join(str(c) for c in cells) + " |"


DETAILS = "\n".join(
    [
        "### Roster Details<br />",
        "Team Name: The Huns<br />",
        f"Roster: {ROSTER}<br />",
        "Global Rank: [122](../../standings_global_2026_10_05.md)<br />",
        "<br />",
        "Region: [Asia]( ../../standings_asia_2026_10_05.md)<br />",
        "Regional Rank: [11]( ../../standings_asia_2026_10_05.md)<br />",
        "<br />",
        "Final Rank Value:  943.8<br />",
        "",
        HEAD,
        "| -: | -: | :- | :- | :- | :- | :- | :- | :- | :- | -: | :- |",
        _row(37, 16, "2026-10-04", "Chinggis Warriors", "L", "-"),
        _row(36, 17, "2026-10-04", "5star", "W", "1 (1.000)"),
        "",
        "#### Bounty Offered<br />",
    ]
)


def test_a_details_page_is_read():
    d = vrs_import.parse_details(DETAILS)
    assert (d.team, d.global_rank, d.region, d.regional_rank, d.points) == (
        "The Huns", 122, "Asia", 11, 943.8,
    )  # fmt: skip
    assert d.roster == ["Annihilation", "Bart4k", "bexyz", "controlez", "Cozen"]
    assert [(m[0], m[2], m[3], m[4]) for m in d.matches] == [
        (16, "Chinggis Warriors", False, False),
        (17, "5star", True, True),
    ]


def test_a_series_seen_from_both_sides_is_stored_once(db, tmp_path):
    folder = tmp_path / "live" / "2026" / "details" / "2026_10_05"
    folder.mkdir(parents=True)
    (folder / "0122--the_huns.md").write_text(DETAILS)
    # 5star's page shows the same series (Match ID 17) from its side: a loss.
    lines = DETAILS.replace("Team Name: The Huns", "Team Name: 5star").splitlines()
    lines = [line for line in lines if "Chinggis" not in line]
    lines = [line.replace("| 5star | W |", "| The Huns | L |") for line in lines]
    other = "\n".join(lines).replace("Global Rank: [122]", "Global Rank: [80]")
    (folder / "0080--5star.md").write_text(other)
    out = vrs_import.import_root(db, tmp_path, log=lambda _: None)
    assert out["standings"] == 2
    rows = db.query(SeriesResult).order_by(SeriesResult.team_b).all()
    vs_5star = [r for r in rows if {r.team_a, r.team_b} == {"5star", "The Huns"}]
    assert len(vs_5star) == 1 and vs_5star[0].lan is True
    s = vs_5star[0]
    assert s.a_won == (s.team_a == "The Huns")  # The Huns won it
    # Idempotent.
    assert vrs_import.import_root(db, tmp_path, log=lambda _: None)["added"] == 0
    assert db.query(VrsStanding).count() == 2


def _series(*rows):
    roster = {"A": ["a1", "a2", "a3", "a4", "a5"], "B": ["b1", "b2", "b3", "b4", "b5"]}
    return [(d, x, y, won, roster.get(x, []), roster.get(y, [])) for d, x, y, won in rows]


def test_a_winner_gains_what_the_loser_drops():
    snap = rating.replay(
        _series((date(2026, 1, 1), "A", "B", True)), rating._Vrs([]), rating.Params(unranked=1000)
    )
    a, b = snap.teams["a"].rating, snap.teams["b"].rating
    assert a > 1000 > b and a - 1000 == pytest.approx(1000 - b)
    assert snap.predictions[0][1] == pytest.approx(0.5)


def test_a_new_core_starts_from_where_its_players_stood():
    series = _series(*[(date(2026, 1, d), "A", "B", True) for d in range(1, 11)])
    # Team C fields four of A's players: it starts near A's Rating, not from scratch.
    series.append((date(2026, 2, 1), "C", "B", True, ["a1", "a2", "a3", "a4", "x"], []))
    snap = rating.replay(series, rating._Vrs([]), rating.Params(unranked=800))
    assert snap.predictions[-1][1] > 0.7
    assert abs(snap.teams["c"].rating - snap.teams["a"].rating) < 30


def test_scores_are_proper():
    s = rating.score([(date(2026, 1, 1), 0.8, 1), (date(2026, 1, 2), 0.3, 0)])
    assert s["n"] == 2 and s["accuracy"] == 1.0 and s["brier"] == pytest.approx((0.04 + 0.09) / 2)


def test_committed_params_load():
    p = rating.params()
    assert p.k > 0 and 0.5 < p.calibration < 1.5
