"""Tick Data stored in MySQL, and what is cut from it, on a small synthetic bundle.

The bundle is shaped like awpy's dump (the same tables and columns) but holds two
short rounds on Nuke, so storing, the geometry, the walks, the Replay and the
re-parse path all run in the normal suite without a real demo.
"""

import gzip
import io
import json
import zipfile

import polars as pl
import pytest
from sqlalchemy import select

from app.models import (
    GameMap,
    GrenadeThrow,
    MapRoster,
    Match,
    MatchMap,
    Player,
    PlayerMapRoute,
    ReplayRound,
    Round,
    RoundSnapshot,
    Team,
    TickDataset,
)
from app.models.base import utcnow
from app.services import analysis_store, dbctx, movement, replay, tickdata

SPLIT_Z = -495.0  # Nuke's floor split (radar.CALIBRATION)
PLACES = ["CTSpawn", "Ramp", "Lobby", "Outside", "Silo", "Vents"]


def _ticks() -> pl.DataFrame:
    """Four players over two rounds; each walks three callouts, two of them downstairs."""
    rows = []
    players = [(11, "a1", "Alpha", "ct"), (12, "a2", "Alpha", "ct"),
               (21, "b1", "Bravo", "t"), (22, "b2", "Bravo", "t")]  # fmt: skip
    for number, start in ((1, 1000), (2, 3000)):
        for i, (steamid, name, clan, side) in enumerate(players):
            for k in range(0, 600, 2):
                leg = min(k // 200, 2)
                rows.append({
                    "health": 100, "flash_duration": 0.0,
                    "place": PLACES[(i + leg) % len(PLACES)],
                    "side": side, "team_clan_name": clan,
                    "X": -1000.0 + k * 3 + i * 50, "Y": 200.0 + (k % 97) * 4 + i * 30,
                    "Z": -300.0 if leg == 0 else -720.0, "yaw": 90.0,
                    "tick": start + 200 + k, "steamid": steamid, "name": name,
                    "round_num": number,
                })  # fmt: skip
    return pl.DataFrame(rows, schema_overrides={"steamid": pl.UInt64})


def _economy() -> pl.DataFrame:
    """Alpha full-buys both rounds; Bravo is on pistols in round 1 and saves in round 2."""
    rows = []
    for number in (1, 2):
        for steamid in (11, 12):
            rows.append({"round_num": number, "steamid": steamid, "balance": 1200,
                         "equip_value": 5200, "armor": 100, "helmet": True, "defuser": True,
                         "inventory": ["knife", "USP-S", "M4A1-S", "Smoke Grenade"]})  # fmt: skip
        for steamid in (21, 22):
            rows.append({"round_num": number, "steamid": steamid, "balance": 2400,
                         "equip_value": 200 if number == 2 else 800, "armor": 0, "helmet": False,
                         "defuser": False, "inventory": ["knife_t", "Glock-18"]})  # fmt: skip
    return pl.DataFrame(rows, schema_overrides={"steamid": pl.UInt64})


def _loadout() -> pl.DataFrame:
    """a1 in round 1 on the replay's 8 Hz grid (every 8th tick at 64 tick): an M4A1-S
    in hand with two flashes on him, then a flash out from 1.5 s."""
    rows = []
    for k in range(0, 600, 8):
        rows.append({"round_num": 1, "tick": 1200 + k, "steamid": 11,
                     "held": "Flashbang" if k >= 96 else "M4A1-S",
                     "inventory": ["Karambit", "Flashbang", "USP-S", "M4A1-S", "Flashbang"],
                     "armor": 100, "helmet": True, "defuser": k >= 96,
                     "balance": 1200})  # fmt: skip
    return pl.DataFrame(rows, schema_overrides={"steamid": pl.UInt64})


def _bundle(
    with_detonations: bool = True, with_economy: bool = True, with_loadout: bool = True
) -> bytes:
    frames = {
        "ticks": _ticks(),
        "rounds": pl.DataFrame(
            {
                "round_num": [1, 2],
                "start": [1000, 3000],
                "freeze_end": [1200, 3200],
                "end": [1900, 3900],
                "official_end": [1950, 3950],
                "winner": ["ct", "t"],
                "reason": ["t_killed", "ct_killed"],
            }
        ),  # fmt: skip
    }
    for empty in (
        "kills",
        "damages",
        "footsteps",
        "shots",
        "grenades",
        "infernos",
        "smokes",
        "bomb",
    ):
        frames[empty] = pl.DataFrame()
    if with_detonations:
        frames["flashes"] = frames["he_grenades"] = pl.DataFrame()
    if with_economy:
        frames["economy"] = _economy()
    if with_loadout:
        frames["loadout"] = _loadout()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, frame in frames.items():
            buffer = io.BytesIO()
            frame.write_parquet(buffer)
            bundle.writestr(f"{name}.parquet", buffer.getvalue())
        bundle.writestr("header.json", json.dumps({"map_name": "de_nuke"}))
    return out.getvalue()


@pytest.fixture
def nuke(db):
    alpha, bravo = Team(name="Alpha"), Team(name="Bravo")
    match = Match(hltv_id=1, team1=alpha, team2=bravo, slug="alpha-vs-bravo")
    match_map = MatchMap(
        match=match, map_number=1, game_map=GameMap(name="de_nuke"), team1=alpha, team2=bravo,
        tickrate=64, n_rounds=2, parsed_at=utcnow(),
    )  # fmt: skip
    db.add(match_map)
    db.flush()
    players = {}
    for steamid, name, team in ((11, "a1", alpha), (12, "a2", alpha), (21, "b1", bravo),
                                (22, "b2", bravo)):  # fmt: skip
        players[steamid] = Player(steamid=steamid, name=name)
        db.add(MapRoster(match_map=match_map, player=players[steamid], team=team))
    for number, winner in ((1, alpha), (2, bravo)):
        db.add(Round(match_map=match_map, number=number, start_tick=1, freeze_end_tick=2,
                     end_tick=3, official_end_tick=4, winner_side="ct", winner_team=winner,
                     ct_team=alpha, t_team=bravo))  # fmt: skip
    db.commit()
    return {"map": match_map, "match": match, "alpha": alpha, "bravo": bravo, "players": players}


def test_store_cuts_geometry_walks_and_replay(db, nuke):
    match_map = nuke["map"]
    dataset = tickdata.store(db, match_map, _bundle(), awpy_version="2.0.2")
    db.commit()
    assert dataset.derived_version == tickdata.derived_version()
    assert {"ticks", "rounds", "flashes", "he_grenades"} <= set(dataset.tables)

    geometry = dataset.geometry
    assert {label["name"] for label in geometry["labels"]} <= set(PLACES)
    assert set(geometry["level_labels"]) == {"upper", "lower"}
    assert abs(sum(geometry["level_share"].values()) - 1) < 1e-9
    assert geometry["place_levels"]["CTSpawn"] == {"upper": 1.0}

    walks = tickdata.load_walks([dataset])
    a1 = nuke["players"][11].id
    walked = walks[f"{a1}|ct|CTSpawn>Ramp>Lobby"]
    assert len(walked) == 2  # one walk per round
    walk = walked[0]
    assert len(walk["shape"]) == tickdata.TRACK_MEDOID_POINTS
    assert len(walk["points"]) == len(walk["places"]) == len(walk["lvl"]) >= 2
    assert walk["lvl"][0] == "upper" and walk["lvl"][-1] == "lower"

    stored = db.scalars(select(ReplayRound).where(ReplayRound.match_map_id == match_map.id))
    assert sorted(r.number for r in stored) == [1, 2]
    first = replay.round_data(db, match_map, 1)
    assert first["round"] == 1 and len(first["players"]) == 4
    assert first["levels"] == ["upper", "lower"]


def test_replay_api_sends_the_stored_gzip(client, auth, db, nuke):
    tickdata.store(db, nuke["map"], _bundle())
    db.commit()
    match_id = nuke["match"].id
    detail = client.get(f"/matches/{match_id}/maps/1", headers=auth).json()
    assert detail["playable"] and [lv["key"] for lv in detail["scene"]["levels"]] == [
        "upper",
        "lower",
    ]
    res = client.get(f"/matches/{match_id}/maps/1/rounds/2", headers=auth)
    assert res.status_code == 200 and res.headers["content-encoding"] == "gzip"
    assert res.json()["round"] == 2
    assert client.get(f"/matches/{match_id}/maps/1/rounds/9", headers=auth).status_code == 404
    # Revalidated every time: the same bytes are a 304, never a stale max-age.
    assert res.headers["cache-control"] == "private, no-cache"
    etag = res.headers["etag"]
    again = client.get(
        f"/matches/{match_id}/maps/1/rounds/2", headers={**auth, "If-None-Match": etag}
    )
    assert again.status_code == 304 and again.headers["etag"] == etag


def test_a_stale_build_is_rebuilt_from_the_stored_bundle(db, nuke):
    match_map = nuke["map"]
    dataset = tickdata.store(db, match_map, _bundle())
    dataset.derived_version = "0.0.0"
    db.query(ReplayRound).delete()
    db.commit()
    assert replay.round_data(db, match_map, 1)["round"] == 1
    assert db.get(TickDataset, dataset.id).derived_version == tickdata.derived_version()


def test_tracks_come_from_the_stored_walks(client, auth, db, nuke):
    match_map = nuke["map"]
    tickdata.store(db, match_map, _bundle())
    a1 = nuke["players"][11]
    db.add(PlayerMapRoute(
        match_map=match_map, player=a1, team=nuke["alpha"], side="ct",
        route_key="CTSpawn>Ramp>Lobby", places=["CTSpawn", "Ramp", "Lobby"], rounds=2,
        path=[{"place": "CTSpawn", "x": -900, "y": 300}, {"place": "Ramp", "x": -400, "y": 400},
              {"place": "Lobby", "x": 0, "y": 500}],
    ))  # fmt: skip
    db.commit()
    with dbctx.using(db):
        found = movement.tracks("de_nuke", nuke["alpha"], str(a1.id), "ct")["tracks"]
    assert len(found) == 1 and found[0]["rounds_seen"] == 2
    assert [s["place"] for s in found[0]["steps"]] == ["CTSpawn", "Ramp", "Lobby"]
    assert len(found[0]["lvl"]) == len(found[0]["points"])
    alpha, bravo = nuke["alpha"].id, nuke["bravo"].id
    body = client.get(
        f"/gameplan/{alpha}/vs/{bravo}/movement?team={alpha}&map=de_nuke&player={a1.id}&side=ct",
        headers=auth,
    ).json()
    assert body["scene"]["tracks"][0]["points"] == found[0]["points"]


def test_old_bundles_get_their_detonations_from_the_rows(db, nuke):
    match_map = nuke["map"]
    first = db.scalar(select(Round).where(Round.match_map_id == match_map.id, Round.number == 1))
    db.add(GrenadeThrow(round=first, entity_id=7, type="flash", thrower=nuke["players"][11],
                        thrower_side="ct", throw_tick=1500, x=1.0, y=2.0, z=3.0))  # fmt: skip
    db.commit()
    blob = tickdata.with_detonations(db, match_map, _bundle(with_detonations=False))
    bundle = tickdata.read(blob)
    flashes = bundle.get("flashes")
    assert flashes.height == 1 and flashes.row(0, named=True)["thrower_steamid"] == 11
    assert bundle.get("he_grenades").is_empty()

    parsed = tickdata.parsed_map(blob, "alpha-vs-bravo-m1-nuke.dem", "2.0.2")
    assert parsed.map_name == "de_nuke" and parsed.n_rounds == 2
    assert parsed.roster.height == 4 and parsed.round_sides.height == 2
    assert parsed.flashes.height == 1
    totals = {(r["steamid"], r["side"]): r["n_rounds"] for r in parsed.round_totals.to_dicts()}
    assert totals[(11, "ct")] == 2 and totals[(11, "all")] == 2


def test_a_bundle_missing_detonations_cannot_be_reparsed(db, nuke):
    from app.services.demo_parser import DemoParseError

    with pytest.raises(DemoParseError, match="flash/HE"):
        tickdata.parsed_map(_bundle(with_detonations=False), "x.dem")


def test_tick_data_without_the_economy_needs_its_demo(db, nuke):
    from app.services.demo_parser import DemoParseError

    with pytest.raises(DemoParseError, match="economy"):
        tickdata.parsed_map(_bundle(with_economy=False), "x.dem")
    assert tickdata.reparseable(tickdata.store(db, nuke["map"], _bundle()))
    old = TickDataset(tables=["ticks", "flashes", "he_grenades"])
    assert not tickdata.reparseable(old) and not tickdata.reparseable(None)


def test_buy_types_and_equipment_from_the_economy(db, nuke):
    parsed = tickdata.parsed_map(_bundle(), "alpha-vs-bravo-m1-nuke.dem")
    equipment = analysis_store._side_equipment(parsed)
    assert equipment == {(1, "ct"): 10400, (1, "t"): 1600, (2, "ct"): 10400, (2, "t"): 400}
    assert [analysis_store.buy_type(2, equipment[(2, side)]) for side in ("ct", "t")] == [
        "force",
        "eco",
    ]
    bought = analysis_store._player_economy(parsed)[(2, 11)]
    assert bought["balance"] == 1200 and bought["helmet"] is True
    assert analysis_store.primary_weapon(bought["inventory"]) == "M4A1-S"
    assert analysis_store.primary_weapon(["knife_t", "Glock-18", "Flashbang"]) == ""


@pytest.mark.parametrize(
    ("number", "value", "buy"),
    [(1, 3250, "pistol"), (13, None, "pistol"), (25, 10_000, "force"), (2, 4_999, "eco"),
     (2, 5_000, "force"), (2, 19_999, "force"), (2, 20_000, "full"), (3, None, "")],
)  # fmt: skip
def test_buy_type_thresholds(number, value, buy):
    assert analysis_store.buy_type(number, value) == buy


def test_snapshots_at_setup_and_plant(db, nuke):
    parsed = tickdata.parsed_map(_bundle(), "alpha-vs-bravo-m1-nuke.dem")
    assert parsed.tickrate == 10  # 200 ticks of freeze time
    rounds = {
        r.number: r for r in db.scalars(select(Round).where(Round.match_map_id == nuke["map"].id))
    }
    for number, freeze in ((1, 1200), (2, 3200)):
        rounds[number].freeze_end_tick, rounds[number].end_tick = freeze, freeze + 700
    rounds[2].bomb_plant_tick = 3300
    db.flush()
    analysis_store._ingest_snapshots(db, parsed, rounds, nuke["players"])
    rows = db.execute(
        select(Round.number, RoundSnapshot.moment, Player.steamid, RoundSnapshot.side,
               RoundSnapshot.place)
        .join(Round, Round.id == RoundSnapshot.round_id)
        .join(Player, Player.id == RoundSnapshot.player_id)
    ).all()  # fmt: skip
    got = {(n, moment, steamid): (side, place) for n, moment, steamid, side, place in rows}
    assert len(got) == 12
    # 20 s in, each player has reached their second callout; at the plant (10 s), not yet.
    assert got[(1, "setup", 11)] == ("ct", "Ramp") and got[(2, "setup", 22)] == ("t", "Silo")
    assert got[(2, "plant", 11)] == ("ct", "CTSpawn") and (1, "plant", 11) not in got


def test_a_landing_takes_the_callout_players_stood_in():
    ticks = pl.DataFrame({
        "X": [0.0, 10.0, 2000.0, 2010.0, 0.0, 10.0], "Y": [0.0, 10.0, 0.0, 10.0, 0.0, 10.0],
        "Z": [0.0, 0.0, 0.0, 0.0, -500.0, -500.0],
        "place": ["Ramp", "Ramp", "Silo", "Silo", "Lower", "Lower"],
    })  # fmt: skip
    cells = tickdata.callout_cells(ticks)
    points = [(5, 5, 20), (2005, 30, 0), (5, 5, -480), (1000, 0, 0), (None, 0, 0)]
    assert tickdata.callouts_at(cells, points) == ["Ramp", "Silo", "Lower", "", ""]
    assert tickdata.callouts_at(tickdata.callout_cells(None), points[:1]) == [""]


def test_the_replay_carries_the_loadout_as_changes(db, nuke):
    dataset = tickdata.store(db, nuke["map"], _bundle())
    db.commit()
    assert tickdata.reparseable(dataset)
    first = replay.round_data(db, nuke["map"], 1)
    assert first["loadout"] is True
    a1 = next(p for p in first["players"] if p["sid"] == "11")
    assert a1["held"] == [[0, "M4A1-S"], [12, "flash"]]
    assert a1["inv"] == [[0, ["M4A1-S", "USP-S", "flash", "flash"]]]  # knife left out
    assert a1["gear"] == [[0, 100, 1, 0, 1200], [12, 100, 1, 1, 1200]]
    b1 = next(p for p in first["players"] if p["sid"] == "21")
    assert "held" not in b1


def test_tick_data_without_the_loadout_replays_but_needs_its_demo(db, nuke):
    from app.services.demo_parser import DemoParseError

    blob = _bundle(with_loadout=False)
    dataset = tickdata.store(db, nuke["map"], blob)
    db.commit()
    assert not tickdata.reparseable(dataset)
    first = replay.round_data(db, nuke["map"], 1)
    assert first["loadout"] is False and all("held" not in p for p in first["players"])
    with pytest.raises(DemoParseError, match="loadout"):
        tickdata.parsed_map(blob, "x.dem")
    assert tickdata.parsed_map(_bundle(), "x.dem").loadout.height == _loadout().height


def test_walks_payload_is_compressed(db, nuke):
    dataset = tickdata.store(db, nuke["map"], _bundle())
    assert json.loads(gzip.decompress(dataset.walks))
