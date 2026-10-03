"""The Playbook: habits found on hand-built rounds, and the tab that shows them."""

from collections import defaultdict

import pytest

from app.routers import gameplan as gameplan_router
from app.services import playbook
from tests.test_gameplan import league  # noqa: F401 -- the shared three-team fixture


@pytest.fixture(autouse=True)
def memory_cache(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(gameplan_router, "_cache_get", lambda key: store.get(key))
    monkeypatch.setattr(
        gameplan_router, "_cache_set", lambda key, value: store.__setitem__(key, value)
    )


def _round(rid, map_id, number, *, plant=None, site="", winner=None, h2h=False, buy="full"):
    return playbook._Round(
        id=rid,
        match_map_id=map_id,
        match_id=map_id,
        map_number=1,
        number=number,
        tickrate=64,
        freeze_end=1000,
        end=9000,
        plant=plant,
        site=site,
        winner=winner,
        ct_team=2,
        t_team=1,
        ct_buy="full",
        t_buy=buy,
        h2h=h2h,
    )


def _detail(grenades=None) -> playbook._Detail:
    return playbook._Detail(defaultdict(list), defaultdict(list), grenades or {}, {}, {})


def _at(secs: float) -> int:
    return 1000 + round(secs * 64)


def test_strength_follows_how_many_maps_the_rounds_came_from():
    rounds = [_round(i, map_id, i) for i, map_id in enumerate((1, 1, 2, 3, 4, 4))]
    assert playbook._evidence(rounds[:2], 10)["strength"] == "weak"
    assert playbook._evidence(rounds[:4], 10)["strength"] == "medium"
    evidence = playbook._evidence(rounds, 10)
    assert evidence["strength"] == "strong" and evidence["maps"] == 4 and evidence["n"] == 6


def test_a_set_play_needs_the_same_grenades_at_the_same_time():
    rounds, grenades = [], {}
    for i in range(7):
        rounds.append(_round(i, i // 2, i + 2, plant=_at(60), site="A" if i < 5 else "B", winner=1))
        late = 20 if i == 6 else 0  # the seventh round smokes mid 20 s later: not the same play
        grenades[i] = [
            ("smoke", "t", _at(6 + late), "TopofMid"),
            ("inferno", "t", _at(9), "Middle"),
            ("smoke", "ct", _at(5), "Jungle"),
        ]
    plays = playbook.set_plays(1, rounds, "t", _detail(grenades))
    assert len(plays) == 1
    play = plays[0]
    assert [(g["type"], g["place"], g["at"]) for g in play["grenades"]] == [
        ("smoke", "TopofMid", 6.0),
        ("inferno", "Middle", 9.0),
    ]
    assert play["evidence"]["n"] == 6 and play["planted"] == {"A": 5, "B": 1}
    assert play["target"] == "A" and play["won"] == 6


def test_too_few_rounds_is_never_a_habit():
    rounds = [_round(i, i, 2, plant=_at(30), site="B") for i in range(3)]
    assert playbook.plant_habits(1, rounds) == []
    rounds.append(_round(3, 3, 2, plant=_at(30), site="B"))
    kinds = {h["kind"]: h for h in playbook.plant_habits(1, rounds)}
    assert kinds["site"]["site"] == "B" and kinds["rush"]["evidence"]["n"] == 4


def test_economy_reads_forces_and_the_round_after_a_lost_pistol():
    rounds = []
    for m in range(5):
        rounds.append(_round(m * 10, m, 1, winner=2, buy="pistol"))
        rounds.append(_round(m * 10 + 1, m, 2, winner=1, buy="force"))
        rounds.append(_round(m * 10 + 2, m, 3, winner=2, buy="eco" if m == 0 else "full"))
    out = playbook.economy(1, rounds)
    assert out["buys"]["force"] == {"n": 5, "won": 5} and out["after_pistol_loss"] == {"force": 5}
    kinds = {h["kind"]: h for h in out["habits"]}
    assert kinds["forces"]["evidence"]["of"] == 6 and kinds["after_pistol_loss"]["buy"] == "force"
    assert playbook.economy(1, [_round(1, 1, 2, buy="")]) == {"known": False, "habits": []}


def test_lean_needs_both_sites():
    sites = {"A": (1000.0, 0.0, 0.0), "B": (-1000.0, 0.0, 0.0)}
    assert playbook.lean((900, 0, 0), sites) == "A"
    assert playbook.lean((-950, 50, 0), sites) == "B"
    assert playbook.lean((0, 0, 0), sites) == "mid"
    assert playbook.lean((900, 0, 0), {"A": sites["A"]}) == ""


def test_todo_lists_maps_and_each_map_has_a_playbook(client, auth, league):  # noqa: F811
    a, b = league["a"].id, league["b"].id
    todo = client.get(f"/gameplan/{a}/vs/{b}/s/todo", headers=auth).json()["data"]
    assert todo["actions"] and [m["map"] for m in todo["maps"]] == ["de_mirage"]
    assert todo["maps"][0]["label"] == "Mirage" and todo["maps"][0]["h2h"] == 1

    res = client.get(f"/gameplan/{a}/vs/{b}/playbook/de_mirage", headers=auth)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["cached"] is False
    data = body["data"]
    assert data["label"] == "Mirage" and data["sample"]["theirs"]["maps"] == 2
    # Bravo planted A in each of its four T rounds that planted, over two maps.
    their_t = data["sections"][0]["habits"]
    site = next(h for h in their_t if h["kind"] == "site")
    assert "A цэгт" in site["title"] and site["evidence"]["strength"] == "medium"
    assert site["evidence"]["refs"][0] == {
        "match": site["evidence"]["refs"][0]["match"],
        "map": 1,
        "round": 3,
    }
    # Twelve-round maps: one pistol each, no second half pistol.
    assert not data["economy"]["known"] and len(data["pistols"]) == 2
    assert data["pistols"][0]["next"] == "дараагийн раунд: хожигдсон"
    again = client.get(f"/gameplan/{a}/vs/{b}/playbook/de_mirage", headers=auth).json()
    assert again["cached"] is True
    assert client.get(f"/gameplan/{a}/vs/{b}/playbook/mirage", headers=auth).status_code == 404
