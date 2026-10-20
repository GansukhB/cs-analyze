# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""Briefings: a Game Plan's lines frozen with notes, shared with the Players (WS-5)."""

from app.models import Briefing, User, UserRole
from app.security import create_access_token, hash_password
from app.services import briefings
from tests.test_gameplan import _map, league, memory_cache  # noqa: F401


def _first_path(panel: dict) -> str:
    for i, _p in enumerate(panel.get("plan") or []):
        return f"plan.{i}"
    for side in panel["advice"]["sides"]:
        for role in ("levers", "cautions"):
            if side[role]:
                return f"advice.{side['side']}.{role}.0"
    for section in panel["sections"]:
        if section["habits"]:
            return f"sections.{section['key']}.0"
    for i, _p in enumerate(panel.get("players") or []):
        return f"players.{i}"
    raise AssertionError("the Playbook has no line to pick")


def _make(client, auth, league, **extra):
    a, b = league["a"], league["b"]
    panel = client.get(f"/gameplan/{a.id}/vs/{b.id}/playbook/de_mirage", headers=auth).json()
    path = _first_path(panel["data"])
    body = {
        "my_team_id": a.id,
        "opponent_id": b.id,
        "title": "Bravo-гийн эсрэг",
        "note": "Mirage-аа эхэлж сонгоно.",
        "stamp": panel["stamp"],
        "maps": [{"map": "de_mirage", "note": "A-гаа хамгаал", "picks": [path]}],
        **extra,
    }
    return client.post("/briefings", json=body, headers=auth), panel, path


def test_a_briefing_freezes_the_picked_lines(client, db, auth, league):
    made, panel, path = _make(client, auth, league)
    assert made.status_code == 201, made.text
    body = made.json()
    item = body["content"]["maps"][0]["items"][0]
    assert item == briefings.freeze(panel["data"], path)
    assert body["content"]["note"] and body["content"]["lineups"]["mine"]
    assert "forecast" not in body["content"] and body["shared_at"] is None
    again = client.get(f"/briefings/{body['id']}", headers=auth).json()
    assert again["content"]["maps"] == body["content"]["maps"]


def test_a_stale_page_or_a_wrong_line_is_refused(client, auth, league):
    stale, _panel, _path = _make(client, auth, league, stamp="old")
    assert stale.status_code == 409
    a, b = league["a"], league["b"]
    wrong = client.post(
        "/briefings",
        json={"my_team_id": a.id, "opponent_id": b.id, "title": "x",
              "maps": [{"map": "de_mirage", "picks": ["sections.nope.9"]}]},
        headers=auth,
    )  # fmt: skip
    assert wrong.status_code == 400


def test_players_read_it_once_shared(client, db, auth, league, workspace):
    player = league["players"][league["a"].id][0]
    login = User(username="A0", password_hash=hash_password("x" * 12), workspace=workspace,
                 role=UserRole.PLAYER, player_id=player.id)  # fmt: skip
    db.add(login)
    db.commit()
    them = {"Authorization": f"Bearer {create_access_token(login.id)}"}
    made, _panel, _path = _make(client, auth, league, include_forecast=True)
    bid = made.json()["id"]
    assert "forecast" in made.json()["content"]
    assert client.get("/briefings", headers=them).json()["briefings"] == []
    assert client.get(f"/briefings/{bid}", headers=them).status_code == 404
    assert client.post(f"/briefings/{bid}/share", headers=auth).json()["shared_at"]
    assert [b["id"] for b in client.get("/briefings", headers=them).json()["briefings"]] == [bid]
    assert client.get(f"/briefings/{bid}", headers=them).status_code == 200
    assert client.post(f"/briefings/{bid}/share", headers=them).status_code == 403
    assert client.delete(f"/briefings/{bid}", headers=auth).status_code == 204
    assert db.query(Briefing).count() == 0
