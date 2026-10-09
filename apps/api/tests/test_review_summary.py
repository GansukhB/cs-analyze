"""The Summary on hand-built Reviews: what a number needs before it says
anything, what makes a Pattern, and what becomes a Focus point."""

import pytest

from app.services import review_summary as summary
from tests.test_review import _review, inferno  # noqa: F401 - the fixture

ALPHA, BRAVO = 1, 2


def _round(n, alpha_side="ct", alpha_won=True, alpha_buy="full", bravo_buy="full",
           alpha_opens=True, start=0.5, plant=False):  # fmt: skip
    """One stored Round of Alpha (a1, a2) against Bravo (b1, b2). ``start`` is
    Alpha's Win probability at freeze end."""
    bravo_side = "t" if alpha_side == "ct" else "ct"
    sides = {"a1": alpha_side, "a2": alpha_side, "b1": bravo_side, "b2": bravo_side}
    killer, victim = ("a1", "b1") if alpha_opens else ("b1", "a1")
    ct_start = start if alpha_side == "ct" else 1 - start
    d_ct = 0.2 if sides[killer] == "ct" else -0.2
    events = [{"t": 10.0, "kind": "kill", "sid": killer, "victim": victim, "d_ct": d_ct}]
    if plant:
        events.append({"t": 40.0, "kind": "plant", "sid": "a1" if alpha_side == "t" else "b1",
                       "d_ct": -0.3})  # fmt: skip
    winner = alpha_side if alpha_won else bravo_side
    return {
        "n": n, "winner_side": winner, "winner_team_id": ALPHA if alpha_won else BRAVO,
        "ct_team_id": ALPHA if alpha_side == "ct" else BRAVO,
        "t_team_id": ALPHA if alpha_side == "t" else BRAVO,
        "reason": "t_killed" if winner == "ct" else "ct_killed", "site": "",
        "ct_buy": alpha_buy if alpha_side == "ct" else bravo_buy,
        "t_buy": alpha_buy if alpha_side == "t" else bravo_buy,
        "seconds": 60.0, "wp": [[0.0, ct_start], [60.0, 1.0 if winner == "ct" else 0.0]],
        "events": events, "swing": {}, "sides": sides, "decider": None,
        "kills": [{"t": 10.0, "a": killer, "v": victim, "traded": False, "opening": True,
                   "weapon": "ak47", "hs": False}],
    }  # fmt: skip


def _finding(n, code, sid="a1", side="ct", swing=-0.1, kind="mistake"):
    return {"id": f"r{n}-{code}", "kind": kind, "code": code, "round": n, "t": 20.0,
            "side": side, "team_id": ALPHA, "sids": [sid], "swing": swing,
            "facts": {"spot": "Banana"}}  # fmt: skip


def _who(sid):
    return sid or "?"


def _stored(rounds, findings=()):
    return {"rounds": rounds, "findings": list(findings), "players": []}


def _keys(items):
    return [i["key"] for i in items]


def test_force_buys_lost_cost_what_they_promised_and_are_a_focus_point():
    rounds = [_round(1, alpha_buy="pistol", bravo_buy="pistol")]
    rounds += [_round(n, alpha_won=False, alpha_buy="force", start=0.3) for n in (2, 3, 4)]
    rounds += [_round(n) for n in range(5, 9)]
    s = summary.team_summary(_stored(rounds), ALPHA, "all", _who)
    force = next(i for i in s["problems"] if i["key"] == "force")
    assert force["weight"] == pytest.approx(0.9)  # three Rounds that each promised 30%
    assert force["text"].startswith("Force buy-ын 0/3")
    assert [r["round"] for r in force["refs"]] == [2, 3, 4]
    assert "force" in _keys(s["focus"]) and force["advice"]
    numbers = {n["key"]: n for n in s["numbers"]}
    assert numbers["force"]["value"] == "0/3" and numbers["force"]["tone"] == "bad"
    assert numbers["pistol"]["tone"] == "good"  # the one pistol was won
    assert "pistol" in _keys(s["strengths"])


def test_a_number_needs_enough_rounds_and_half_as_many_on_one_side():
    # Alpha opens 4 of 5: too few duels over the Map (6), enough on CT alone (3).
    rounds = [_round(n, alpha_opens=n != 5) for n in range(1, 6)]
    rounds += [_round(n, alpha_side="t", alpha_opens=False) for n in (6, 7)]
    over_map = summary.team_summary(_stored(rounds), ALPHA, "all", _who)
    on_ct = summary.team_summary(_stored(rounds), ALPHA, "ct", _who)
    assert "opening" not in _keys(over_map["strengths"] + over_map["problems"])  # 4/7
    assert "opening" in _keys(on_ct["strengths"])
    assert on_ct["rounds"] == 5 and all(n["key"] != "t" for n in on_ct["numbers"])


def test_a_pattern_is_more_than_most_teams_do():
    rounds = [_round(n) for n in range(1, 25)]
    # Three lost guns in 24 Rounds is common (P75 is 11); three moving duels is not.
    findings = [_finding(n, "lost_weapon_save") for n in (1, 2, 3)]
    findings += [_finding(n, "moving_shots", sid="a2" if n == 6 else "a1") for n in (4, 5, 6)]
    s = summary.team_summary(_stored(rounds, findings), ALPHA, "all", _who)
    keys = _keys(s["problems"])
    assert "moving_shots" in keys and "lost_weapon_save" not in keys
    moving = next(i for i in s["problems"] if i["key"] == "moving_shots")
    assert moving["count"] == 3 and moving["players"][0] == {"sid": "a1", "n": 2}
    assert moving["spots"] == [{"name": "Banana", "n": 3}]
    assert "a1 2" in moving["text"] and "Banana" in moving["text"]


def test_a_lost_round_names_its_costliest_mistake_as_the_focus():
    r = _round(1, alpha_won=False, alpha_opens=False)
    findings = [_finding(1, "died_in_advantage", swing=-0.3), _finding(1, "awp_miss", swing=-0.1)]
    words = {f["id"]: {"title": f"a1 — {f['code']}"} for f in findings}
    alpha, bravo = summary.round_teams(r, findings, words, _who, map_number=2)
    assert alpha["team_id"] == ALPHA and not alpha["won"]
    assert [b["finding"] for b in alpha["bad"][:2]] == ["r1-died_in_advantage", "r1-awp_miss"]
    assert alpha["bad"][2]["label"] == "Opening" and alpha["bad"][2]["map_number"] == 2
    assert alpha["focus"]["finding"] == "r1-died_in_advantage" and alpha["focus"]["advice"]
    assert bravo["won"] and bravo["focus"] is None
    assert bravo["good"][0]["text"] == "Opening: b1 → a1"
    assert bravo["line"].startswith("T · full buy — CT-г бүгдийг нь хөнөөж хожсон")


def test_a_match_summary_keeps_what_shows_on_two_maps(client, auth, db, inferno):  # noqa: F811
    _review(db, inferno)
    res = client.get(f"/matches/{inferno['match'].id}/summary", headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert [m["reviewed"] for m in body["maps"]] == [True]
    assert {s["team_id"] for s in body["summaries"]} == {t["id"] for t in body["teams"]}
    # One Map: nothing can repeat across Maps yet.
    assert all(s["strengths"] == [] and s["problems"] == [] for s in body["summaries"])
    review = client.get(f"/matches/{inferno['match'].id}/maps/1/review", headers=auth).json()
    assert len(review["rounds"][0]["teams"]) == 2
    assert set(review["summary"]) == {"all", "ct", "t"}


def test_across_maps_the_weights_add_up():
    one = summary.team_summary(
        _stored([_round(n, alpha_won=False, alpha_buy="force", start=0.3) for n in (1, 2, 3)]),
        ALPHA, "all", _who, map_number=1,
    )  # fmt: skip
    two = summary.team_summary(
        _stored([_round(n, alpha_won=False, alpha_buy="force", start=0.2) for n in (1, 2, 3)]),
        ALPHA, "all", _who, map_number=2,
    )  # fmt: skip
    maps = [{"map_number": 1, "summary": [one], "players": []},
            {"map_number": 2, "summary": [two], "players": []}]  # fmt: skip
    (alpha,) = summary.match_summary(maps, [ALPHA], {1: "Inferno", 2: "Nuke"})
    force = next(i for i in alpha["problems"] if i["key"] == "force")
    assert force["maps"] == [1, 2] and force["weight"] == pytest.approx(1.5)
    assert "Inferno ба Nuke-д давтагдсан алдаа" in force["text"]
    assert {r["map_number"] for r in force["refs"]} == {1, 2}
    assert alpha["focus"][0]["key"] == "force"


def test_the_assistant_reads_the_match_summary(db, inferno):  # noqa: F811
    from app.services import assistant, dbctx

    _review(db, inferno)
    with dbctx.using(db):
        out = assistant._tool_match_summary(inferno["match"].id)
        review = assistant._tool_match_review(inferno["match"].id)
    assert out["maps"][0]["reviewed"] is True and len(out["teams"]) == 2
    assert {s["team"] for s in review["summary"]} == {"Alpha", "Bravo"}
