# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""The lineup library (docs/plans/08 SB-3)."""

from sqlalchemy import select

from app.models import GrenadeThrow, Round
from tests.test_gameplan import league, memory_cache  # noqa: F401


def test_three_throws_from_one_spot_to_one_landing_are_a_lineup(
    client, auth, db, league, memory_cache
):
    rounds = db.scalars(select(Round).order_by(Round.id)).all()[:4]
    for i, r in enumerate(rounds):
        far = i == 3  # the fourth lands elsewhere: not part of it
        db.add(GrenadeThrow(
            round_id=r.id, entity_id=100 + i, type="smoke", thrower_side="t",
            throw_tick=r.freeze_end_tick + 500, start_tick=r.freeze_end_tick + 500,
            thrown_tick=r.freeze_end_tick + 300, thrown_x=1000.0 + i, thrown_y=40.0,
            thrown_z=-168.0,
            thrown_pitch=-42.0, thrown_yaw=-160.0, thrown_place="TSpawn",
            x=-300.0 if not far else 900.0, y=-500.0, z=-100.0, place="TopofMid",
        ))  # fmt: skip
    db.commit()
    out = client.get("/lineups/de_mirage", headers=auth)
    assert out.status_code == 200, out.text
    [lineup] = out.json()
    assert (lineup["type"], lineup["throws"], lineup["from"], lineup["to"]) == (
        "smoke", 3, "TSpawn", "TopofMid",
    )  # fmt: skip
    assert lineup["setpos"] == "setpos 1001.0 40.0 -168.0;setang -42.00 -160.00 0"
    assert lineup["flight"] == round(200 / 64, 1)
    assert client.get("/lineups/de_mirage?type=flash", headers=auth).json() == []
