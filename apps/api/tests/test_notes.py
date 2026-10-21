# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""Review notes, Finding disputes and Playlists (docs/plans/07 RV-7)."""

from sqlalchemy import select

from app.models import Match
from tests.test_gameplan import league, memory_cache  # noqa: F401
from tests.test_me import player_login  # noqa: F401


def _match(db, home, away):
    return db.scalar(select(Match).where(Match.team1_id == home.id, Match.team2_id == away.id))


def test_a_note_reaches_the_player_it_names_and_a_dispute_does_not(
    client, db, auth, league, player_login
):
    them, me = player_login
    match = _match(db, league["a"], league["b"])
    url = f"/matches/{match.id}/maps/1/notes"
    note = {"round": 3, "t": 41.5, "sids": [str(me.steamid)], "text": "Утаагаа эрт", "tag": "util"}
    assert client.post(url, json=note, headers=auth).status_code == 201
    dispute = {"kind": "dispute", "round": 3, "code": "untraded", "reason": "lurk"}
    assert client.post(url, json=dispute, headers=auth).status_code == 201
    bad = {"kind": "dispute", "round": 3, "code": "untraded", "reason": "nope"}
    assert client.post(url, json=bad, headers=auth).status_code == 400
    assert client.post(url, json=note, headers=them).status_code == 403

    kinds = sorted(n["kind"] for n in client.get(url, headers=auth).json()["notes"])
    assert kinds == ["dispute", "note"]
    mine = client.get(url, headers=them).json()["notes"]
    assert [n["text"] for n in mine] == ["Утаагаа эрт"] and mine[0]["tag"] == "util"
    assert [n["round"] for n in client.get("/me/notes", headers=them).json()] == [3]

    rates = client.get("/workspace/disputes", headers=auth).json()
    assert rates[0]["code"] == "untraded" and rates[0]["reasons"] == {"lurk": 1}


def test_a_note_can_be_only_a_drawing_on_the_replay(client, db, auth, league):
    """VIZ-8: an arrow and a word, in world units, kept with the Note."""
    match = _match(db, league["a"], league["b"])
    url = f"/matches/{match.id}/maps/1/notes"
    marks = [
        {"kind": "arrow", "points": [[-1200.5, 300.0], [-900.0, 640.0]]},
        {"kind": "text", "points": [[-500.0, 100.0]], "text": "flash энд"},
    ]
    made = client.post(url, json={"round": 4, "t": 22.0, "drawing": marks}, headers=auth)
    assert made.status_code == 201, made.text
    back = client.get(url, headers=auth).json()["notes"][0]
    assert back["text"] == "" and back["drawing"][0]["points"][1] == [-900.0, 640.0]
    assert back["drawing"][1]["text"] == "flash энд" and back["drawing"][0]["text"] == ""
    assert client.post(url, json={"round": 4}, headers=auth).status_code == 400
    many = {"round": 4, "drawing": [marks[0]] * 13}
    assert client.post(url, json=many, headers=auth).status_code == 422
    three = {"round": 4, "drawing": [{"kind": "arrow", "points": [[0, 0], [1, 1], [2, 2]]}]}
    assert client.post(url, json=three, headers=auth).status_code == 422


def test_a_clip_of_the_notes_moment_is_kept_and_played_back(client, db, auth, league, player_login):
    """VIZ-13: WebM only; the Player the note names plays it, another gets nothing."""
    them, me = player_login
    match = _match(db, league["a"], league["b"])
    url = f"/matches/{match.id}/maps/1/notes"
    named = client.post(url, json={"round": 2, "t": 9.0, "sids": [str(me.steamid)], "text": "x"},
                        headers=auth).json()  # fmt: skip
    other = client.post(url, json={"round": 2, "t": 9.0, "text": "y"}, headers=auth).json()
    webm = b"\x1aE\xdf\xa3" + b"\x00" * 64
    clip = {"data": ("clip.webm", webm, "video/webm")}
    assert client.put(f"/notes/{named['id']}/clip", files=clip, headers=auth).status_code == 204
    assert client.put(f"/notes/{other['id']}/clip", files=clip, headers=auth).status_code == 204
    gif = {"data": ("x.gif", b"GIF89a", "image/gif")}
    assert client.put(f"/notes/{named['id']}/clip", files=gif, headers=auth).status_code == 400
    assert client.put(f"/notes/{named['id']}/clip", files=clip, headers=them).status_code == 403
    back = client.get(f"/notes/{named['id']}/clip", headers=them)
    assert back.status_code == 200 and back.content == webm
    assert back.headers["content-type"] == "video/webm"
    assert client.get(f"/notes/{other['id']}/clip", headers=them).status_code == 404
    listed = {n["id"]: n["has_clip"] for n in client.get(url, headers=auth).json()["notes"]}
    assert listed[named["id"]] and listed[other["id"]]


def test_a_shared_playlist_opens_its_rounds_to_the_players(client, db, auth, league, player_login):
    them, _me = player_login
    elsewhere = _match(db, league["b"], league["c"])  # A0 never played it
    assert client.get(f"/matches/{elsewhere.id}", headers=them).status_code == 404
    body = {
        "title": "Bravo-гийн B rush",
        "items": [{"match_id": elsewhere.id, "map_number": 1, "round": 4, "text": "5 хүн B"}],
    }
    made = client.post("/playlists", json=body, headers=auth)
    assert made.status_code == 201, made.text
    pid = made.json()["id"]
    assert made.json()["items"][0]["label"] == "Bravo vs Charlie · Mirage"
    assert client.get("/playlists", headers=them).json() == []
    assert client.get(f"/playlists/{pid}", headers=them).status_code == 404

    client.put(f"/playlists/{pid}", json={**body, "shared": True}, headers=auth)
    assert [p["id"] for p in client.get("/playlists", headers=them).json()] == [pid]
    assert client.get(f"/playlists/{pid}", headers=them).json()["items"][0]["round"] == 4
    assert client.get(f"/matches/{elsewhere.id}", headers=them).status_code == 200
    assert client.post("/playlists", json=body, headers=them).status_code == 403
    missing = {"title": "x", "items": [{"match_id": 999, "map_number": 1, "round": 1}]}
    assert client.post("/playlists", json=missing, headers=auth).status_code == 404
