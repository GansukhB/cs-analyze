"""The Round search (docs/plans/09 VIZ-7)."""

from app.services import replay, round_search
from tests.test_gameplan import league  # noqa: F401  (fixture)


def _payload():
    # Two T at B from second 2 (frame 16); one dies at second 4.
    hp = [100] * 48
    dead = [100] * 32 + [0] * 16
    return {
        "hz": 8, "seconds": 5.9, "places": ["Mid", "B"],
        "players": [
            {"side": "t", "hp": hp, "place": [[0, 0], [16, 1]]},
            {"side": "t", "hp": dead, "place": [[0, 0], [16, 1]]},
            {"side": "ct", "hp": hp, "place": [[0, 1]]},
        ],
    }  # fmt: skip


def test_tokens_count_each_sides_living_players_per_place_each_second():
    t = replay.tokens(_payload())
    at = {(s, t["places"][i]): n for s, i, n in t["t"]}
    assert at[(0, "Mid")] == 2 and at[(2, "B")] == 2 and at[(4, "B")] == 1
    assert (5, "B") in at and (0, "B") not in at
    assert {t["places"][i] for _s, i, _n in t["ct"]} == {"B"}


def test_a_condition_holds_in_its_window_give_or_take_two_seconds():
    t = replay.tokens(_payload())
    assert round_search._holds(t, "t", {"place": "B", "min": 2, "start": 2, "end": 3})
    assert not round_search._holds(t, "t", {"place": "B", "min": 3, "start": 0, "end": 5})
    # Two at B only until second 3: a window at 6-8 reaches back to it.
    assert round_search._holds(t, "t", {"place": "B", "min": 2, "start": 5, "end": 8})
    assert not round_search._holds(t, "t", {"place": "B", "min": 2, "max": 1, "start": 2, "end": 3})
    assert not round_search._holds(t, "t", {"place": "Nowhere", "min": 1})


def test_the_search_answers_with_no_indexed_rounds(client, auth):
    body = {"map_name": "de_mirage", "side": "t", "conditions": [{"place": "B"}]}
    out = client.post("/search/rounds", headers=auth, json=body)
    assert out.status_code == 200 and out.json() == {
        "looked": 0,
        "found": 0,
        "won": 0,
        "rounds": [],
        "heat": None,
    }


def test_a_search_finds_a_round_and_draws_where_its_side_died(client, auth, db, league):  # noqa: F811
    """One indexed Round of the league: two T at B from second 2; its T death heats."""
    import gzip
    import json

    from sqlalchemy import select

    from app.models import MatchMap, ReplayRound, Round

    mm = db.scalars(select(MatchMap).order_by(MatchMap.id)).first()
    rnd = db.scalar(select(Round).where(Round.match_map_id == mm.id, Round.number == 1))
    blob = gzip.compress(json.dumps(replay.tokens(_payload())).encode())
    db.add(ReplayRound(match_map_id=mm.id, number=1, payload=gzip.compress(b"{}"), tokens=blob))
    db.commit()
    body = {"map_name": "de_mirage", "side": "t", "heat": "deaths",
            "conditions": [{"place": "B", "min": 2, "start": 0, "end": 5}]}  # fmt: skip
    out = client.post("/search/rounds", headers=auth, json=body).json()
    assert (out["looked"], out["found"]) == (1, 1) and out["rounds"][0]["round"] == rnd.number
    assert out["heat"]["kind"] == "deaths" and len(out["heat"]["points"]) == 1
    none = client.post("/search/rounds", headers=auth, json={**body, "side": "ct"}).json()
    assert none["found"] == 0 and none["heat"] is None
    places = client.get("/search/places/de_mirage", headers=auth).json()
    assert places == ["B", "Mid"]
