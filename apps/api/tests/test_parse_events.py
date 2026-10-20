"""Schema 14's reads (docs/plans/02 DATA-5): each grenade's throw from its
trajectory, with where the thrower stood and aimed."""

from types import SimpleNamespace

import polars as pl

from app.services import analysis_store, demo_parser

SID = 76561198000000001


def _trajectory(rows):
    return pl.DataFrame(
        rows,
        schema={"round_num": pl.UInt32, "entity_id": pl.Int32, "grenade_type": pl.String,
                "thrower_steamid": pl.UInt64, "tick": pl.Int32, "X": pl.Float32,
                "Y": pl.Float32, "Z": pl.Float32},
        orient="row",
    )  # fmt: skip


def test_a_returning_entity_id_is_a_new_grenade():
    rows = [
        (1, 7, "CSmokeGrenadeProjectile", SID, 100, None, None, None),  # not located yet
        (1, 7, "CSmokeGrenadeProjectile", SID, 101, 10.0, 20.0, 30.0),
        (1, 7, "CSmokeGrenadeProjectile", SID, 102, 11.0, 21.0, 31.0),
        (1, 7, "CSmokeGrenadeProjectile", SID, 400, 50.0, 60.0, 70.0),  # the id came back
        (1, 9, "CDecoyProjectile", SID, 200, 1.0, 1.0, 1.0),  # no GrenadeType
    ]
    starts = demo_parser.projectile_starts(_trajectory(rows))
    assert starts.select("tick", "kind", "X").rows() == [(101, "smoke", 10.0), (400, "smoke", 50.0)]


def _grenade(kind, start=None, pop=None):
    return {"type": kind, "start_tick": start, "throw_tick": pop, "_steamid": SID, "_number": 1}


def test_each_grenade_takes_its_own_throw_with_the_stand_and_the_aim():
    trajectory = _trajectory([
        (1, 7, "CSmokeGrenadeProjectile", SID, 100, 0.0, 0.0, 0.0),
        (1, 8, "CSmokeGrenadeProjectile", SID, 300, 0.0, 0.0, 0.0),
        (1, 9, "CFlashbangProjectile", SID, 500, 0.0, 0.0, 0.0),
    ])  # fmt: skip
    ticks = pl.DataFrame(
        {"steamid": [SID] * 3, "tick": [100, 300, 500], "X": [1.0, 2.0, 3.0],
         "Y": [4.0, 5.0, 6.0], "Z": [7.0, 8.0, 9.0], "yaw": [90.0, 180.0, 270.0],
         "place": ["Mid", "Window", "Ramp"]},
        schema_overrides={"steamid": pl.UInt64},
    )  # fmt: skip
    throws = pl.DataFrame({"steamid": [SID], "tick": [301], "pitch": [-40.0]},
                          schema_overrides={"steamid": pl.UInt64})  # fmt: skip
    aim = pl.DataFrame({"steamid": [SID] * 2, "tick": [104, 302], "pitch": [-10.0, -20.0]},
                       schema_overrides={"steamid": pl.UInt64})  # fmt: skip
    parsed = SimpleNamespace(grenades=trajectory, ticks=ticks, throws=throws, aim=aim, tickrate=64)
    second, first = _grenade("smoke", start=420), _grenade("smoke", start=230)
    flash = _grenade("flash", pop=600)
    late = _grenade("he", pop=900)  # no HE was thrown
    matched = analysis_store._attach_throws([second, first, flash, late], parsed)
    assert len(matched) == 3 and "thrown_tick" not in late
    assert (first["thrown_tick"], first["thrown_place"], first["thrown_yaw"]) == (100, "Mid", 90.0)
    assert (second["thrown_tick"], second["thrown_place"]) == (300, "Window")
    # grenade_thrown's exact pitch first, else the aim grid's within 8 ticks.
    assert second["thrown_pitch"] == -40.0 and first["thrown_pitch"] == -10.0
    assert flash["thrown_tick"] == 500 and flash["thrown_pitch"] is None
