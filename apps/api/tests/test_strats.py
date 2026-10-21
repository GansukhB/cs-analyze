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
