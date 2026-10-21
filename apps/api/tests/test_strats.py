# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""The Stratbook (docs/plans/08 SB-1, SB-7)."""

from sqlalchemy import select

from app.models import Match, WorkspaceTeam
from tests.test_gameplan import league, memory_cache  # noqa: F401
from tests.test_me import player_login  # noqa: F401


def _ours(db, workspace, team):
    db.add(WorkspaceTeam(workspace_id=workspace.id, team_id=team.id))
    db.commit()


def _body(team_id, **extra):
    return {
        "team_id": team_id, "map_name": "de_mirage", "side": "t", "name": "B split",
        "kind": "execute", "description": "Apps + short",
        "roles": [{"slot": 1, "role": "entry", "does": "first into B"}],
        "grenades": [{"slot": 2, "type": "smoke", "place": "Market", "at": 18.0}],
        **extra,
    }  # fmt: skip


def test_staff_write_strats_and_players_read_only_what_is_shared(
    client, db, auth, user, workspace, league, player_login
):
    them, _me = player_login
    a = league["a"]
    _ours(db, workspace, a)
    made = client.post("/strats", json=_body(a.id), headers=auth)
    assert made.status_code == 201, made.text
    sid = made.json()["id"]
    assert made.json()["grenades"][0]["place"] == "Market" and made.json()["can_edit"]
    assert client.post("/strats", json=_body(league["b"].id), headers=auth).status_code == 400
    # A draft for Staff only: the Player login sees nothing, can write nothing.
    assert client.get("/strats", headers=them).json() == []
    assert client.get(f"/strats/{sid}", headers=them).status_code == 404
    assert client.post("/strats", json=_body(a.id), headers=them).status_code == 403
    edit = _body(a.id, status="active", visibility="team", name="B split 2")
    shared = client.put(f"/strats/{sid}", headers=auth, json=edit)
    assert shared.json()["versions"] == 1
    read = client.get(f"/strats/{sid}", headers=them).json()
    assert read["name"] == "B split 2" and read["can_edit"] is False
    assert client.post(f"/strats/{sid}/print", headers=them).status_code == 204
    log = [e["action"] for e in client.get(f"/strats/{sid}/events", headers=auth).json()]
    assert log[:2] == ["print", "view"] and "share" in log and log[-1] == "edit"
    versions = client.get(f"/strats/{sid}/versions", headers=auth).json()
    assert versions[0]["payload"]["name"] == "B split"


def test_an_example_round_links_the_strat_to_a_match(client, db, auth, workspace, league):
    a, b = league["a"], league["b"]
    _ours(db, workspace, a)
    sid = client.post("/strats", json=_body(a.id), headers=auth).json()["id"]
    match = db.scalar(select(Match).where(Match.team1_id == a.id, Match.team2_id == b.id))
    out = client.post(f"/strats/{sid}/examples", headers=auth,
                      json={"match_id": match.id, "map_number": 1, "round": 9})  # fmt: skip
    example = out.json()["examples_list"][0]
    assert (example["match_id"], example["round"]) == (match.id, 9)
    assert "Alpha vs Bravo" in example["label"]
    again = client.post(f"/strats/{sid}/examples", headers=auth,
                        json={"match_id": match.id, "map_number": 1, "round": 9})  # fmt: skip
    assert again.json()["examples"] == 1
    gone = client.delete(f"/strats/{sid}/examples/{example['id']}", headers=auth)
    assert gone.json()["examples"] == 0
    rows = client.get("/strats?map_name=de_mirage", headers=auth).json()
    assert [r["id"] for r in rows] == [sid]


def test_a_set_play_becomes_a_strat_with_its_rounds(client, db, auth, workspace, league):
    """SB-2: the Rounds a Set play was found in come with it; one not visible is left out."""
    a, b = league["a"], league["b"]
    _ours(db, workspace, a)
    match = db.scalar(select(Match).where(Match.team1_id == a.id, Match.team2_id == b.id))
    refs = [{"match_id": match.id, "map_number": 1, "round": n} for n in (3, 6, 6)]
    refs.append({"match_id": 999999, "map_number": 1, "round": 1})
    made = client.post("/strats", headers=auth, json=_body(a.id, examples=refs)).json()
    assert [e["round"] for e in made["examples_list"]] == [3, 6]
    assert {e["source"] for e in made["examples_list"]} == {"setplay"}


def test_rounds_that_played_a_strat_are_found_and_counted(client, db, auth, workspace, league):
    """SB-4: Alpha's T Rounds 7-9 against Bravo threw its two grenades on time."""
    from app.models import GrenadeThrow, MatchMap, Round

    a, b = league["a"], league["b"]
    _ours(db, workspace, a)
    match = db.scalar(select(Match).where(Match.team1_id == a.id, Match.team2_id == b.id))
    mm = db.scalar(select(MatchMap).where(MatchMap.match_id == match.id))
    for r in db.scalars(
        select(Round).where(Round.match_map_id == mm.id, Round.number.in_((7, 8, 9)))
    ):
        for i, (kind, secs) in enumerate((("smoke", 15.0), ("inferno", 18.5))):
            landed = r.freeze_end_tick + int(secs * 64)
            db.add(GrenadeThrow(round_id=r.id, entity_id=500 + i, type=kind, thrower_side="t",
                                start_tick=landed, place="BombsiteA"))  # fmt: skip
    db.commit()
    nades = [{"type": "smoke", "place": "BombsiteA", "at": 16.0},
             {"type": "inferno", "place": "BombsiteA", "at": 20.0}]  # fmt: skip
    sid = client.post("/strats", headers=auth, json=_body(a.id, grenades=nades)).json()["id"]
    found = client.post(f"/strats/{sid}/match", headers=auth).json()
    assert sorted(e["round"] for e in found["examples_list"]) == [7, 8, 9]
    report = found["report"]
    assert report["played"] == 3 and report["pending"] == 3
    assert report["official"]["played"] == 3 and report["low"] <= 100 * report["won"] / 3
    first = found["examples_list"][0]
    after = client.post(f"/strats/{sid}/examples/{first['id']}/confirm", headers=auth).json()
    assert after["report"]["pending"] == 2
    second = after["examples_list"][1]
    dropped = client.delete(f"/strats/{sid}/examples/{second['id']}", headers=auth).json()
    assert dropped["report"]["played"] == 2
    again = client.post(f"/strats/{sid}/match", headers=auth).json()
    assert again["report"]["played"] == 2  # a dismissed Round is not found again
    client.put(f"/strats/{sid}", headers=auth, json=_body(a.id, grenades=nades, status="active"))
    cover = client.get(f"/strats/coverage/{a.id}", headers=auth).json()
    assert cover["de_mirage"]["active"] == 1


def test_a_strat_is_searched_in_every_other_teams_rounds(client, db, auth, workspace, league):
    """SB-5: Bravo's T Rounds 1-3 against Alpha threw Alpha's Strat's two grenades."""
    from app.models import GrenadeThrow, MatchMap, Round

    a, b = league["a"], league["b"]
    _ours(db, workspace, a)
    match = db.scalar(select(Match).where(Match.team1_id == a.id, Match.team2_id == b.id))
    mm = db.scalar(select(MatchMap).where(MatchMap.match_id == match.id))
    bravo_t = db.scalars(select(Round).where(Round.match_map_id == mm.id, Round.t_team_id == b.id))
    for r in list(bravo_t)[:3]:
        for i, (kind, secs) in enumerate((("smoke", 15.0), ("inferno", 18.5))):
            landed = r.freeze_end_tick + int(secs * 64)
            db.add(GrenadeThrow(round_id=r.id, entity_id=700 + i, type=kind, thrower_side="t",
                                start_tick=landed, place="BombsiteA"))  # fmt: skip
    db.commit()
    nades = [{"type": "smoke", "place": "BombsiteA", "at": 16.0},
             {"type": "inferno", "place": "BombsiteA", "at": 20.0}]  # fmt: skip
    sid = client.post("/strats", headers=auth, json=_body(a.id, grenades=nades)).json()["id"]
    found = client.get(f"/strats/{sid}/elsewhere", headers=auth).json()
    assert found["rounds"] == 3 and [t["team"] for t in found["teams"]] == ["Bravo"]
    assert found["teams"][0]["low"] <= found["won"] / 3 <= found["teams"][0]["high"]
    assert len(found["refs"]) == 3
    # Alpha's own Rounds are the Strat's report, never "elsewhere".
    assert client.post(f"/strats/{sid}/match", headers=auth).json()["report"]["played"] == 0
