"""Vetoes read off HLTV's match page, a Team's Veto history and Tells (CONTEXT.md),
the Forecast's opponent leaning on its Vetoes, and Self-scout on v2."""

import datetime as dt
from collections import Counter, defaultdict

import pytest

from app.models import Match, MatchVeto, Team
from app.services import dbctx, forecast, mn, tells, veto, veto_history
from tests.test_v2 import huns  # noqa: F401 -- the shared my team fixture

PAGE = {
    "boxes": [
        "1. Chinggis Warriors removed Anubis\n2. 5star removed Dust2\n"
        "3. Chinggis Warriors picked Ancient\n4. 5star picked Cache\n"
        "5. Chinggis Warriors removed Inferno\n6. 5star removed Mirage\n7. Nuke was left over",
        "Best of 3 (LAN)\n\n* Upper bracket final",
    ],
    "names": ["Chinggis Warriors", "5star"],
    "links": ["/team/12646/chinggis-warriors", "/team/13724/5star"],
}


def test_the_match_page_reads_as_a_veto():
    v = veto.parse(PAGE)
    assert (v.best_of, v.lan) == (3, True)
    assert v.teams == [("Chinggis Warriors", 12646), ("5star", 13724)]
    assert [(s.step, s.action, s.map, s.side) for s in v.steps] == [
        (1, "ban", "de_anubis", 1),
        (2, "ban", "de_dust2", 2),
        (3, "pick", "de_ancient", 1),
        (4, "pick", "de_cache", 2),
        (5, "ban", "de_inferno", 1),
        (6, "ban", "de_mirage", 2),
        (7, "decider", "de_nuke", None),
    ]


def test_an_older_page_writes_the_steps_into_its_format_block():
    old = {
        "boxes": ["Best of 1 (Online)\n\nVeto process:\n1. Spirit removed Nuke\n"
                  "2. NAVI removed Overpass\n3. Mirage was left over"],
        "names": ["Natus Vincere", "Spirit"],
        "links": [],
    }  # fmt: skip
    v = veto.parse(old)
    assert (v.best_of, v.lan) == (1, False)
    # "NAVI" is not the page's name for the Team; a prefix doesn't match it either.
    assert [(s.map, s.side) for s in v.steps] == [
        ("de_nuke", 2),
        ("de_overpass", None),
        ("de_mirage", None),
    ]
    assert veto.parse({"boxes": ["Best of 3 (LAN)"], "names": [], "links": []}).steps == []


def _veto(db, a: Team, b: Team, day: int, steps: list[tuple], best_of=3) -> Match:
    m = Match(team1=a, team2=b, played_at=dt.datetime(2026, 9, day), best_of=best_of)
    db.add(m)
    db.flush()
    for i, (who, action, game_map) in enumerate(steps, start=1):
        team = {"a": a, "b": b}.get(who)
        db.add(
            MatchVeto(
                match_id=m.id,
                step=i,
                action=action,
                map=game_map,
                team_id=team.id if team else None,
                team_name=team.name if team else "",
            )
        )
    return m


POOL = ("de_anubis", "de_mirage", "de_inferno", "de_ancient", "de_cache", "de_dust2", "de_nuke")


def _bo3(first_ban: str, pick: str) -> list[tuple]:
    """``a`` bans ``first_ban`` and picks ``pick``; the rest in pool order."""
    left = [m for m in POOL if m not in (first_ban, pick)]
    return [
        ("a", "ban", first_ban),
        ("b", "ban", left[0]),
        ("a", "pick", pick),
        ("b", "pick", left[1]),
        ("a", "ban", left[2]),
        ("b", "ban", left[3]),
        (None, "decider", left[4]),
    ]


@pytest.fixture
def vetoes(db):
    a, b = Team(name="Alpha", hltv_id=1), Team(name="Bravo", hltv_id=2)
    db.add_all([a, b])
    for day in range(1, 7):
        _veto(db, a, b, day, _bo3("de_nuke" if day < 6 else "de_dust2", "de_mirage"))
    # Before the pool last changed (2026-07-08): never counted.
    old = Match(team1=a, team2=b, played_at=dt.datetime(2026, 6, 1), best_of=3)
    db.add(old)
    db.flush()
    db.add(MatchVeto(match_id=old.id, step=1, action="ban", map="de_train", team_id=a.id))
    db.commit()
    return {"a": a, "b": b}


def test_a_team_veto_history_and_its_tells(db, vetoes):
    with dbctx.using(db):
        out = veto_history.summary(vetoes["a"])
        listed = veto_history.team_vetoes(vetoes["a"])
        habit = veto_history.habit(vetoes["a"], 3)
    assert out["since"] == "2026-07-08" and out["vetoes"] == 6
    bo3 = out["formats"]["bo3"]
    rows = {r["map"]: r for r in bo3["maps"]}
    assert rows["de_nuke"]["first_ban"] == 5 and rows["de_mirage"]["picked"] == 6
    assert "de_train" not in rows
    tells_ = {t["point"]: t for t in bo3["tells"]}
    # Too few Teams for a Pool bar: half or more of five Vetoes or more is a Tell.
    assert tells_["first_ban"]["top"] == "de_nuke" and tells_["first_ban"]["share"] == 0.833
    assert tells_["first_ban"]["tell"] and tells_["pick"]["tell"]
    assert listed[0]["played_at"] == "2026-09-06" and listed[0]["started"]
    assert listed[0]["opponent"] == "Bravo" and listed[0]["first_ban"] == "de_dust2"
    assert habit["vetoes"] == 6 and habit["pick"]["de_mirage"] == 6
    worded = mn.veto_tell(tells_["first_ban"], whose="theirs")
    assert worded["title"] == "Nuke" and "ban" in worded["counter"]


def test_the_forecast_leans_on_their_vetoes(db, vetoes):
    options = ["de_mirage", "de_nuke", "de_inferno"]
    p = dict.fromkeys(options, 0.5)
    share = dict.fromkeys(options, 1 / 3)
    plain = forecast._their_policy(options, "pick", p, share)
    leaned = forecast._their_policy(options, "pick", p, share, {"pick": {"de_mirage": 6}})
    assert plain["de_mirage"] == pytest.approx(1 / 3)
    assert leaned["de_mirage"] == pytest.approx((6 + 4 / 3) / 10)
    assert sum(leaned.values()) == pytest.approx(1)
    with dbctx.using(db):
        check = forecast.check_vetoes()
    # Every step the two Teams took is scored, once each Veto's earlier ones are known.
    assert check["model"]["n"] == check["history"]["n"] == 36
    assert check["history"]["log_loss"] < check["model"]["log_loss"]


def _round(rid, mm, number, *, ct=2, t=1, plant=None, site="", winner=None, ct_buy="full",
           t_buy="full"):  # fmt: skip
    from app.services import playbook

    return playbook._Round(
        id=rid, match_map_id=mm, match_id=mm, map_number=1, number=number, tickrate=64,
        freeze_end=1000, end=9000, plant=plant, site=site, winner=winner, ct_team=ct, t_team=t,
        ct_buy=ct_buy, t_buy=t_buy, h2h=False,
    )  # fmt: skip


SITES = {"A": (1000.0, 0.0, 0.0), "B": (-1000.0, 0.0, 0.0)}


def test_tells_read_each_decision_point(monkeypatch):
    monkeypatch.setattr(tells, "pool_bars", lambda _map: {"attack:t": 0.9})
    rounds, setups = [], defaultdict(list)
    for mm in range(12):
        # Team 1 on T: a lost pistol, then a force; a default A plant in Round 3.
        rounds.append(_round(mm * 10, mm, 1, plant=None, winner=2, t_buy="pistol"))
        rounds.append(_round(mm * 10 + 1, mm, 2, winner=2, t_buy="force"))
        rounds.append(_round(mm * 10 + 2, mm, 3, plant=1000 + 64 * 60, site="A", winner=1))
        # Team 1 on CT in Round 13: two on A, one mid, two on B.
        rounds.append(_round(mm * 10 + 3, mm, 14, ct=1, t=2, winner=1))
        setups[mm * 10 + 3] = [(p, "ct", "", x, 0.0, 0.0)
                               for p, x in enumerate((900, 950, 0, -900, -950))]  # fmt: skip
    found = {(t["point"], t["side"]): t for t in tells.for_team(1, rounds, setups, SITES, "m")}
    assert found[("after_pistol", "t")]["top"] == {"buy": "force"}
    assert found[("after_pistol", "t")]["tell"]  # 12/12, no Pool bar: two in three stands in
    assert found[("pistol", "t")]["top"] == {"site": "none"}
    # 12/12 on A, default; the Pool's bar is 90%, and 100% clears it.
    attack = found[("attack", "t")]
    assert attack["top"] == {"site": "A", "tempo": "default"} and attack["tell"]
    assert attack["won"] == 12 and attack["evidence"]["maps"] == 12
    setup = found[("setup", "ct")]
    assert setup["top"] == {"setup": {"A": 2, "mid": 1, "B": 2}} and setup["tell"]
    worded = mn.tell(setup, whose="theirs")
    assert worded["title"] == "A 2 · төв 1 · B 2" and worded["counter"]
    assert mn.tell(setup, whose="mine")["counter"].startswith("Өрсөлдөгч")


def test_a_pool_bar_above_the_share_is_no_tell(monkeypatch):
    monkeypatch.setattr(tells, "pool_bars", lambda _map: {"attack:t": 0.8})
    rounds = [
        _round(i, i, 3, plant=1000 + 64 * 60, site="A" if i < 7 else "B", winner=1)
        for i in range(10)
    ]
    (attack,) = tells.for_team(1, rounds, {}, SITES, "m")
    assert attack["share"] == 0.7 and not attack["tell"] and attack["pool_p75"] == 0.8
    assert Counter(m["n"] for m in attack["mix"]) == Counter([7, 3])


def test_self_scout_and_the_scouting_vetoes(client, auth, db, huns):  # noqa: F811
    a, b = huns["huns"], huns["spirit"]
    for day in range(1, 3):
        _veto(db, a, b, day, _bo3("de_nuke", "de_anubis"))
    db.commit()
    body = client.get(f"/v2/teams/{a.id}/self-scout", headers=auth).json()
    assert body["map"] == "de_anubis" and body["sample"]["rounds"] == 3
    assert body["vetoes"]["vetoes"] == 2
    (bo3,) = body["vetoes"]["formats"]
    assert bo3["best_of"] == 3 and not any(t["tell"] for t in bo3["tells"])  # two is too few
    scouting = client.get(f"/v2/teams/{a.id}/scouting/{b.id}", headers=auth).json()
    assert scouting["vetoes"]["theirs"]["team"]["name"] == "Spirit"
    assert scouting["vetoes"]["theirs"]["recent"][0]["steps"][1]["mine"] is True
    assert scouting["vetoes"]["theirs"]["recent"][0]["steps"][0]["mine"] is False
    other = client.get(f"/v2/teams/{b.id}/self-scout", headers=auth)
    assert other.status_code == 404  # not a my team


def test_the_buy_after_a_lost_pistol_is_read_over_every_map(monkeypatch):
    monkeypatch.setattr(tells, "pool_bars", lambda m: {} if m else {"after_pistol:t": 0.7})
    on_map = [_round(1, 1, 1, winner=2, t_buy="pistol"), _round(2, 1, 2, winner=2, t_buy="eco")]
    everywhere = list(on_map)
    for mm in range(2, 10):
        everywhere += [
            _round(mm * 10, mm, 1, winner=2, t_buy="pistol"),
            _round(mm * 10 + 1, mm, 2, winner=1, t_buy="force"),
        ]
    found = {t["point"]: t for t in tells.for_team(1, on_map, {}, SITES, "m", every_map=everywhere)}
    after = found["after_pistol"]
    assert after["all_maps"] and after["of"] == 9 and after["top"] == {"buy": "force"}
    assert after["share"] == 0.889 and after["pool_p75"] == 0.7 and after["tell"]
    assert mn.tell(after, whose="theirs")["label"].endswith("бүх Map")
