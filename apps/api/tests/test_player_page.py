"""A Player's page (PL-2), on the hand-built Review Round."""

from tests.test_review import _review, inferno  # noqa: F401  (fixture)


def test_a_players_page_has_his_form_numbers_and_findings(client, auth, db, inferno):  # noqa: F811
    _review(db, inferno)
    res = client.get("/players/12", headers=auth)
    assert res.status_code == 200
    page = res.json()
    assert page["player"] == {"steamid": "12", "name": "a2", "aliases": []}
    assert [t["name"] for t in page["teams"]] == ["Alpha"]
    (form,) = page["form"]
    assert form["opponent"] == "Bravo" and form["map"] == "de_inferno"
    # a2 won the Round 1v2: a positive Swing, and a clutch among his Findings.
    assert form["swing_per_round"] > 0
    assert any(f["code"] == "clutch" and f["kind"] == "key_play" for f in page["findings"])
    assert page["rounds_reviewed"] == 1


def test_an_unknown_player_is_404(client, auth):
    assert client.get("/players/999", headers=auth).status_code == 404


def test_a_steam_id_beyond_javascript_integers_is_read_exactly(client, auth, db):
    from app.models import Player

    db.add(Player(steamid=76561198441362330, name="Bart4k"))
    db.commit()
    page = client.get("/players/76561198441362330", headers=auth).json()
    assert page["player"]["steamid"] == "76561198441362330"
    assert client.get("/players/not-a-number", headers=auth).status_code == 422
