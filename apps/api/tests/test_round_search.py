"""The Round search (docs/plans/09 VIZ-7)."""

from app.services import replay, round_search


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
    }
