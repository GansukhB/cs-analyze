# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""Staff's notes on a Playbook's habit lines (docs/plans/06 GP-13)."""

from app.services import playbook_notes
from tests.test_briefings import _first_path
from tests.test_gameplan import league, memory_cache  # noqa: F401


def test_a_habit_keeps_its_key_when_only_its_numbers_move():
    a = {"kind": "setup", "side": "ct", "lean": "A", "n": 7, "share": 0.6, "player_id": 12}
    b = {**a, "n": 9, "share": 0.71}
    assert playbook_notes.habit_key(a) == playbook_notes.habit_key(b)
    assert playbook_notes.habit_key(a) != playbook_notes.habit_key({**a, "lean": "B"})
    assert playbook_notes.habit_key(a) != playbook_notes.habit_key({**a, "player_id": 13})
    assert playbook_notes.habit_key({}) == "" and len(playbook_notes.habit_key(a)) == 16


def test_a_note_on_a_line_is_kept_and_goes_into_a_briefing(client, auth, league):
    a, b = league["a"], league["b"]
    panel = client.get(f"/gameplan/{a.id}/vs/{b.id}/playbook/de_mirage", headers=auth).json()
    path = _first_path(panel["data"])
    keys = [h.get("key") for s in panel["data"]["sections"] for h in s["habits"] if h.get("key")]
    assert keys, "the fixture's Playbook has a habit line to note"
    key = keys[0]
    body = {"team_id": b.id, "map_name": "de_mirage", "key": key, "text": "Scrim-д ч харсан"}
    assert client.put("/playbook-notes", headers=auth, json=body).status_code == 204
    read = client.get(f"/playbook-notes?team_id={b.id}&map_name=de_mirage", headers=auth).json()
    assert read[key]["text"] == "Scrim-д ч харсан" and read[key]["by"]
    paths = [f"sections.{s['key']}.{i}" for s in panel["data"]["sections"]
             for i, h in enumerate(s["habits"]) if h.get("key") == key]  # fmt: skip
    made = client.post("/briefings", headers=auth, json={
        "my_team_id": a.id, "opponent_id": b.id, "title": "x", "stamp": panel["stamp"],
        "maps": [{"map": "de_mirage", "picks": paths[:1] or [path]}],
    })  # fmt: skip
    assert made.status_code == 201, made.text
    item = made.json()["content"]["maps"][0]["items"][0]
    assert paths and item["note"] == "Scrim-д ч харсан"
    gone = {**body, "text": ""}
    client.put("/playbook-notes", headers=auth, json=gone)
    assert (
        client.get(f"/playbook-notes?team_id={b.id}&map_name=de_mirage", headers=auth).json() == {}
    )
