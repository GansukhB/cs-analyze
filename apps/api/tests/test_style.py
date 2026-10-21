# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""A Team's style on a Map against every Team's (docs/plans/05 TM-5)."""

from app.services import dbctx, style
from tests.test_gameplan import league, memory_cache  # noqa: F401


def _metric(out, side, key):
    found = next(s for s in out["sides"] if s["side"] == side)
    return next(m for m in found["metrics"] if m["key"] == key)


def test_a_teams_style_is_read_off_its_rounds_and_ranked(db, league, memory_cache):
    with dbctx.using(db):
        out = style.team(league["a"].id, "de_mirage")
    # Every Round's first kill is the CT's, 10 s in: an early pick each time.
    pick = _metric(out, "ct", "early_pick")
    assert pick["value"] == 100.0 and pick["teams"] == 3 and pick["pct"] == 50
    contact = _metric(out, "t", "contact")
    assert contact["value"] == 10.0 and contact["unit"] == "s"
    # Alpha's T Rounds are 7-12 of its two Maps: a plant in 9 and 12, 9.4 s in.
    early = _metric(out, "t", "early_plant")
    assert early["value"] == round(100 * 4 / 12, 1) and not early["thin"]


def test_the_team_page_and_the_game_plan_ask_for_it(client, auth, db, league, memory_cache):
    a, b = league["a"], league["b"]
    view = client.get(f"/teams/{a.id}/style", headers=auth).json()
    assert view["maps"] == ["de_mirage"] and view["style"]["map"] == "de_mirage"
    both = client.get(f"/gameplan/{a.id}/vs/{b.id}/style/de_mirage", headers=auth).json()
    assert both["mine"]["sides"] and both["theirs"]["sides"]


def test_lurks_and_rotations_read_from_the_round_tokens():
    """TM-5 schema 2, on hand-made tokens: places A1, B1, Mid1."""
    from app.services import style

    toward = {"A": {"A1"}, "B": {"B1"}, "mid": {"Mid1"}}
    lurk = {"places": ["A1", "B1", "Mid1"], "t": [[30, 0, 1], [30, 1, 3]], "ct": []}
    stack = {"places": ["A1", "B1", "Mid1"], "t": [[30, 0, 2], [30, 1, 3]], "ct": []}
    assert style._lurked(lurk, toward) and not style._lurked(stack, toward)
    # One CT at A from second 11 (after the opening at 10), a second one at 15.
    ct = {"places": ["A1", "B1"], "t": [],
          "ct": [[11, 0, 1], [12, 0, 1], [15, 0, 2]]}  # fmt: skip
    assert style._rotated(ct, {"A1"}, 10) == 5.0
    assert style._rotated(ct, {"B1"}, 10) is None
