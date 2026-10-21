# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""A Team's utility on a Map and Side (docs/plans/09 VIZ-10)."""

from sqlalchemy import select

from app.models import GrenadeThrow, Match, MatchMap, Round
from tests.test_gameplan import league, memory_cache  # noqa: F401


def test_the_same_smoke_thrown_twice_is_a_lineup(client, db, auth, league):
    a, b = league["a"], league["b"]
    match = db.scalar(select(Match).where(Match.team1_id == a.id, Match.team2_id == b.id))
    mm = db.scalar(select(MatchMap).where(MatchMap.match_id == match.id))
    rounds = db.scalars(select(Round).where(Round.match_map_id == mm.id, Round.t_team_id == b.id))
    for i, r in enumerate(list(rounds)[:3]):
        db.add(GrenadeThrow(
            round_id=r.id, entity_id=900 + i, type="smoke", thrower_side="t",
            start_tick=r.freeze_end_tick + 640, x=-300.0 + i, y=400.0, z=0.0, place="TopofMid",
            thrown_tick=r.freeze_end_tick + 400, thrown_x=1000.0 + i, thrown_y=-200.0,
            thrown_z=0.0, thrown_pitch=-30.0, thrown_yaw=170.0, thrown_place="TSpawn",
        ))  # fmt: skip
    db.commit()
    url = f"/gameplan/{a.id}/vs/{b.id}/utility/de_mirage?side=t"
    body = client.get(url, headers=auth).json()
    assert body["team"] == "Bravo" and len(body["throws"]) == 3
    (lineup,) = body["lineups"]
    assert (lineup["type"], lineup["throws"], lineup["from_place"], lineup["to_place"]) == (
        "smoke", 3, "TSpawn", "TopofMid",
    )  # fmt: skip
    assert lineup["t"] == 10.0 and lineup["setpos"].startswith("setpos 1001.0 -200.0 0.0")
    mine = client.get(url + "&whose=mine", headers=auth).json()
    assert mine["team"] == "Alpha" and mine["throws"] == []
    assert client.get(url.replace("side=t", "side=x"), headers=auth).status_code == 422
