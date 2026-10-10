"""Levers and Cautions: the Reviews cut into tallies, judged against the Pool,
paired across facing Sides, worded, and lifted into the action list."""

import pytest
from sqlalchemy.orm import sessionmaker

from app import tasks
from app.routers import gameplan as gameplan_router
from app.services import gameplan_view, levers, mn, review, review_pool
from tests.test_gameplan import league  # noqa: F401 -- the shared three-team fixture
from tests.test_review_summary import ALPHA, BRAVO, _finding, _round, _stored


@pytest.fixture(autouse=True)
def memory_cache(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(gameplan_router, "_cache_get", lambda key: store.get(key))
    monkeypatch.setattr(
        gameplan_router, "_cache_set", lambda key, value: store.__setitem__(key, value)
    )


META = {"mm": 7, "match": 70, "num": 1, "map": "de_inferno"}


def _tally(team, side, *, map_name="de_inferno", mm=1, rounds=12, events=None, codes=None):
    t = review_pool.Tally(mm=mm, match=mm * 10, num=1, map=map_name, team=team, side=side,
                          sight=False, rounds=list(range(1, rounds + 1)))  # fmt: skip
    for key, rows in (events or {}).items():
        t.events[key] = rows
    for code, rows in (codes or {}).items():
        t.codes[code] = rows
    return t


def _post_plant(won: int, of: int) -> list[tuple]:
    return [(n, n <= won, None, 1.0) for n in range(1, of + 1)]


def _data(tallies) -> review_pool.Data:
    by_team: dict = {}
    for t in tallies:
        by_team.setdefault(t.team, []).append(t)
    pools, player_pools = review_pool._pools(by_team)
    return review_pool.Data("s", tallies, by_team, {}, pools, player_pools, {})


# --------------------------------------------------------------- tallies ---
def test_a_review_is_cut_per_team_and_side():
    rounds = [
        _round(1, alpha_buy="pistol", bravo_buy="pistol"),
        _round(2, alpha_opens=False, alpha_won=False, plant=True, alpha_side="ct"),
        _round(3, alpha_side="t", plant=True, alpha_buy="force", bravo_buy="full"),
    ]
    findings = [_finding(2, "awp_miss", side="ct"), _finding(3, "entry", side="t", swing=0.2)]
    tallies = {(t.team, t.side): t for t in review_pool._cut(_stored(rounds, findings), META)}
    assert set(tallies) == {(ALPHA, "ct"), (ALPHA, "t"), (BRAVO, "ct"), (BRAVO, "t")}
    alpha_ct = tallies[(ALPHA, "ct")]
    assert alpha_ct.rounds == [1, 2]
    # Round 1 Alpha opened, Round 2 Bravo did: one won and one lost opening.
    assert [(n, hit) for n, hit, *_ in alpha_ct.events["opening"]] == [(1, True), (2, False)]
    assert [n for n, *_ in alpha_ct.events["pistol"]] == [1]
    assert [(n, hit) for n, hit, *_ in alpha_ct.events["retake"]] == [(2, False)]
    assert [f[0] for f in alpha_ct.codes["awp_miss"]] == [2]
    alpha_t = tallies[(ALPHA, "t")]
    assert [(n, hit) for n, hit, *_ in alpha_t.events["post_plant"]] == [(3, True)]
    assert [n for n, *_ in alpha_t.events["force"]] == [3]
    assert alpha_t.codes["entry"][0][4] == "Banana"
    # A death is a trade chance for the side that died: Bravo's T lost b1 in Round 1.
    assert [(n, hit) for n, hit, *_ in tallies[(BRAVO, "t")].events["trade"]] == [(1, False)]


def test_rounds_without_teams_make_no_tally():
    r = _round(1)
    r["ct_team_id"] = r["t_team_id"] = None
    assert review_pool._cut(_stored([r]), META) == []


# ----------------------------------------------------------- the judgement ---
def test_a_small_sample_is_pulled_toward_the_pool():
    spread = review_pool._spread("rate", [(0.2, 40), (0.5, 40), (0.8, 40), (0.5, 40)])
    small, _ = review_pool._z(spread, 0.0, 5)
    large, _ = review_pool._z(spread, 0.0, 400)
    assert abs(small) < abs(large)
    assert review_pool._reliability(spread, 5) < review_pool.MIN_RELIABILITY
    assert review_pool._reliability(spread, 400) > 0.9
    # What chance alone explains is not counted as the Pool's spread.
    noisy = review_pool._spread("rate", [(0.0, 3), (0.67, 3), (0.33, 3), (1.0, 3)])
    assert noisy["sd"] < 0.4


def test_a_weak_post_plant_is_a_weakness_on_its_map_and_else_across_all_maps(monkeypatch):
    pool = [
        _tally(team, "t", mm=team * 10 + i, map_name=name, rounds=24,
               events={"post_plant": _post_plant(won, 20)})
        for team, won in ((2, 15), (3, 16), (4, 14), (5, 17))
        for i, name in enumerate(("de_inferno", "de_mirage"))
    ]  # fmt: skip
    weak = [
        _tally(1, "t", mm=101, events={"post_plant": _post_plant(4, 20)}),
        _tally(1, "t", mm=102, events={"post_plant": _post_plant(5, 20)}),
        _tally(1, "t", mm=103, map_name="de_mirage", events={"post_plant": _post_plant(1, 3)}),
    ]
    monkeypatch.setattr(review_pool, "data", lambda: _data(pool + weak))
    team = type("T", (), {"id": 1})()
    on_inferno = review_pool.team_lines(team, "de_inferno", h2h={101})
    line = next(x for x in on_inferno if x["key"] == "post_plant")
    assert line["good"] is False and line["scope"] == "map" and line["side"] == "t"
    assert line["evidence"]["n"] == 31 and line["evidence"]["maps"] == 2
    assert line["evidence"]["h2h"] == 16 and line["evidence"]["strength"] == "medium"
    # Three plants on Mirage say nothing: all the Team's Maps speak instead.
    on_mirage = review_pool.team_lines(team, "de_mirage", h2h=set())
    line = next(x for x in on_mirage if x["key"] == "post_plant")
    assert line["scope"] == "all_maps" and not line["good"]
    assert review_pool.score(team, "post_plant", "de_inferno", "t") < -1


# --------------------------------------------------------------- pairing ---
def _line(key, side, good, weight=0.3, kind="rate"):
    evidence = {"n": 6, "of": 20, "maps": 3, "h2h": 0, "strength": "medium", "refs": []}
    return {"key": key, "kind": kind, "good": good, "side": side, "value": 0.5, "mean": 0.6,
            "z": -1.0, "weight": weight, "players": [], "spots": [], "scope": "map",
            "evidence": evidence}  # fmt: skip


def _fixture(monkeypatch, mine, theirs, scores=None):
    my_team, opponent = type("T", (), {"id": 1})(), type("T", (), {"id": 2})()
    monkeypatch.setattr(levers.mapstrategy, "maps_in_window", lambda *a, **k: [])
    monkeypatch.setattr(
        review_pool, "team_lines", lambda team, *_a: list(mine if team.id == 1 else theirs)
    )
    monkeypatch.setattr(review_pool, "player_lines", lambda *_a: [])
    monkeypatch.setattr(
        review_pool, "score", lambda team, key, m, side: (scores or {}).get((team.id, key, side))
    )
    monkeypatch.setattr(levers, "limits", lambda *_a: [{"kind": "no_their_data"}])
    monkeypatch.setattr(levers, "memo", lambda key, compute: compute())
    return levers.build(my_team, opponent, "de_inferno")


def test_my_strength_meeting_their_weakness_comes_first(monkeypatch):
    mine = [_line("post_plant", "t", True, 0.2), _line("force", "t", True, 0.9)]
    theirs = [_line("retake", "ct", False, 0.2)]
    built = _fixture(monkeypatch, mine, theirs)
    first, second = built["columns"]["t"]["levers"]
    assert first["pair"] and first["mine"]["key"] == "post_plant"
    assert first["theirs"]["key"] == "retake"
    assert not second["pair"] and second["mine"]["key"] == "force"
    assert built["limits"] == [{"kind": "no_their_data"}]


def test_their_weakness_is_no_lever_when_we_are_weak_at_using_it(monkeypatch):
    theirs = [_line("post_plant", "t", False, 0.8), _line("opening", "t", False, 0.3)]
    built = _fixture(monkeypatch, [], theirs, scores={(1, "retake", "ct"): -0.9})
    # Our weak retake takes away «let them plant, then retake»; the opening stays.
    assert [e["theirs"]["key"] for e in built["columns"]["ct"]["levers"]] == ["opening"]


def test_their_strength_against_my_weakness_is_the_first_caution(monkeypatch):
    mine = [_line("retake", "ct", False, 0.1), _line("awp_miss", "ct", False, 0.5, "code")]
    theirs = [_line("post_plant", "t", True, 0.1)]
    cautions = _fixture(monkeypatch, mine, theirs)["columns"]["ct"]["cautions"]
    assert cautions[0]["pair"] and cautions[0]["role"] == "caution"
    assert cautions[1]["mine"]["key"] == "awp_miss"


# ---------------------------------------------------------------- wording ---
def test_a_pair_is_worded_with_both_facts_and_proofs():
    entry = levers._entry(
        "lever", "t", _line("post_plant", "t", True, 0.4), _line("retake", "ct", False, 0.3)
    )
    worded = mn.advice(entry, "Bravo", lambda sid: "")
    assert worded["title"] == mn.ADVICE_PAIR[("post_plant", "retake", "lever")][0]
    assert worded["facts"][0].startswith("Манай T · Plant-ын дараах хожил 50% (Pool 60%)")
    assert worded["facts"][1].startswith("Bravo CT · Retake хожил")
    assert [p["label"] for p in worded["proofs"]] == ["Манай", "Bravo"]
    assert worded["weight_label"] == "≈ 0.7 раунд/хагас"


def test_my_weakness_borrows_the_summary_advice():
    entry = levers._entry("caution", "ct", _line("awp_miss", "ct", False, 0.02, "code"), None)
    worded = mn.advice(entry, "Bravo", lambda sid: "")
    assert worded["counter"] == mn.SUMMARY_ADVICE["awp_miss"]
    assert worded["weight_label"] == "< 0.1 раунд/хагас"


def test_the_first_lever_and_caution_of_a_likely_map_follow_the_veto(monkeypatch):
    raw = [{"kind": "kill_first"}, {"kind": "ban"}, {"kind": "duel_hole"}, {"kind": "caveat"}]
    monkeypatch.setattr(mn, "actions", lambda items: [{"what": a["kind"]} for a in items])
    monkeypatch.setattr(levers, "build", lambda mine, theirs, m: m)
    monkeypatch.setattr(
        levers, "top", lambda m, said: ({"m": m, "r": "lever"}, {"m": m, "r": "caution"})
    )
    monkeypatch.setattr(levers, "identity", lambda e: (e["m"], e["r"]))
    monkeypatch.setattr(mn, "advice_action", lambda e, label, team: {"what": f"{label}:{e['r']}"})
    maps = [{"map": "de_nuke", "call": "ban", "label": "Nuke"},
            {"map": "de_inferno", "call": "pick", "label": "Inferno"}]  # fmt: skip
    team = type("T", (), {"name": "Bravo"})()
    out = gameplan_view._todo_actions(raw, maps, team, team)
    assert [a["what"] for a in out] == [
        "kill_first", "ban", "Inferno:lever", "Inferno:caution", "duel_hole", "caveat",
    ]  # fmt: skip


# ------------------------------------------------------- the stale Reviews ---
def test_the_refresh_rebuilds_each_stale_review_and_holds_after_a_failure(
    monkeypatch,
    engine,
    db,
    league,  # noqa: F811
):
    maps = [m.id for m in db.query(review_pool.MatchMap).order_by("id")]
    monkeypatch.setattr(tasks, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    monkeypatch.setattr(review_pool, "stale_ids", lambda: maps)
    built = []
    monkeypatch.setattr(
        review, "rebuild", lambda s, mm: built.append(mm.id) or (None if mm.id == maps[0] else {})
    )
    held = []
    monkeypatch.setattr(review_pool, "release_refresh", lambda hold=0: held.append(hold))
    assert tasks.refresh_reviews() == {"rebuilt": len(maps) - 1, "failed": 1}
    assert built == maps and held == [review_pool.REFRESH_RETRY_SECONDS]


def test_opening_a_game_plan_asks_for_a_review_refresh(client, auth, league, review_refreshes):  # noqa: F811
    a, b = league["a"].id, league["b"].id
    assert client.get(f"/gameplan/{a}/vs/{b}", headers=auth).status_code == 200
    assert review_refreshes == [{}]
    body = client.get(f"/gameplan/{a}/vs/{b}/playbook/de_mirage", headers=auth).json()["data"]
    # No Reviews stored: no Lever or Caution, only what the maps tab already warns of.
    assert [s["label"] for s in body["advice"]["sides"]] == ["Манай CT", "Манай T"]
    assert all(not s["levers"] and not s["cautions"] for s in body["advice"]["sides"])


def test_a_map_ranks_its_own_numbers_first_and_says_a_shared_one_once():
    everywhere = {**_line("trade", "t", False, 0.5), "scope": "all_maps"}
    here = _line("opening", "t", False, 0.45)
    built = {
        "columns": {
            "ct": {"levers": sorted([levers._entry("lever", "ct", None, everywhere),
                                     levers._entry("lever", "ct", None, here)],
                                    key=levers._order), "cautions": []},
            "t": {"levers": [], "cautions": []},
        }
    }  # fmt: skip
    first, _caution = levers.top(built)
    assert first["theirs"]["key"] == "opening"  # 0.45 here beats 0.5 read off every Map
    again, _ = levers.top(built, said={levers.identity(first)})
    assert again["theirs"]["key"] == "trade"


def test_a_tendency_the_map_contradicts_says_nothing():
    pool = {"mean": 0.5, "sd": 0.05, "n": 10, "kind": "rate", "per_round": 0.0}
    # Strong across all Maps, weak on this one's few events: no line.
    assert review_pool.estimate((0.25, 4), (0.62, 400), pool, pool) is None
    # The same tendency with nothing on this Map carries the line, marked as such.
    est = review_pool.estimate(None, (0.62, 400), pool, pool)
    assert est.scope == "all_maps" and est.z > 0.8 and est.everywhere is None
    # A Map's Pool with no spread left after chance borrows the all-Maps spread.
    flat = {**pool, "sd": 0.001}
    assert review_pool.estimate((0.55, 30), (0.5, 400), flat, pool).z < 1
