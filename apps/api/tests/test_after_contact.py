# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""What a Team does after the first contact (docs/plans/05 TM-7)."""

from sqlalchemy import select

from app.models import BombEvent, BombEventType, GameMap, MatchMap, Round
from app.services import after_contact
from tests.test_gameplan import league, memory_cache  # noqa: F401


def test_each_opening_branches_into_where_the_bomb_went(client, db, auth, league):
    a = league["a"]
    # Where the sites are: the fixture's openings fall between them.
    rounds = db.scalars(
        select(Round).join(MatchMap).join(GameMap).where(GameMap.name == "de_mirage")
    ).all()
    for rnd, site, x, y in ((rounds[0], "A", -450.0, 280.0), (rounds[1], "B", 10.0, 500.0)):
        db.add(BombEvent(round_id=rnd.id, tick=rnd.freeze_end_tick + 600,
                         event=BombEventType.PLANT, bombsite=site, x=x, y=y, z=0.0))  # fmt: skip
    db.commit()
    body = client.get(f"/teams/{a.id}/after-contact?map=de_mirage", headers=auth).json()
    assert "de_mirage" in body["maps"]
    after = body["after"]
    for side in ("t", "ct"):
        nodes = after[side]["openings"]
        assert nodes and sum(n["n"] for n in nodes) <= after[side]["rounds"]
        for n in nodes:
            assert n["where"] in ("A", "mid", "B")
            assert [b["then"] for b in n["then"]] == ["A", "B", "none"]
            assert sum(b["n"] for b in n["then"]) == n["n"]
            assert sum(b["won"] for b in n["then"]) == n["wins"] <= n["n"]
            assert all(len(b["refs"]) <= min(b["n"], 8) for b in n["then"])
    for r in after["ct"]["retakes"]:
        assert r["situation"] in ("ahead", "even", "behind") and r["won"] <= r["n"]
    unknown = client.get("/teams/999999/after-contact", headers=auth)
    assert unknown.status_code == 404


def test_counting_a_sides_players_at_a_sites_callouts():
    tokens = {"places": ["Apartments", "BombsiteB", "Mid"],
              "ct": [[5, 1, 1], [6, 1, 2], [6, 0, 1], [7, 2, 3]], "t": []}  # fmt: skip
    b = {"Apartments", "BombsiteB"}
    assert after_contact._at(tokens, "ct", 5, b) == 1
    assert after_contact._at(tokens, "ct", 6, b) == 3
    assert after_contact._at(tokens, "ct", 7, b) == 0
    assert after_contact._situation(3, 2) == "ahead" and after_contact._situation(1, 2) == "behind"
