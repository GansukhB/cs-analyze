"""Parse and ingest a real ``.dem`` end to end. Slow (awpy), so opt-in:

CS_ANALYZE_TEST_DEM=/path/to/some-m1-ancient.dem npm run test:api -- tests/test_real_demo.py
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import (
    Demo,
    GrenadeThrow,
    KillEvent,
    MapRoster,
    Match,
    MatchMap,
    PlayerMap,
    PlayerMapRoute,
    PlayerMatch,
    PlayerRound,
    ReplayRound,
    Round,
    RoundSnapshot,
    TickDataset,
)
from app.services import analysis_store, archive, demo_parser, replay, tickdata

DEM = os.environ.get("CS_ANALYZE_TEST_DEM")
pytestmark = pytest.mark.skipif(not DEM, reason="set CS_ANALYZE_TEST_DEM to a .dem file")


@pytest.fixture(scope="module")
def parsed():
    return demo_parser.parse_map(Path(DEM))


def count(db, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where))


def _ingest(db, tmp_path, parsed, hltv_id: int):
    entry = archive.parse_demo_name(Path(DEM).name)
    match = Match(hltv_id=hltv_id, slug=f"real-demo-{hltv_id}")
    demo = Demo(match=match, map=entry.map, map_number=entry.map_number or 1, path=DEM)
    demo.filename = Path(DEM).name
    demo.is_downloaded = True
    db.add(demo)
    db.commit()
    bundle = tickdata.pack(parsed, tmp_path)
    return demo, bundle


def snapshot(db, match_map_id: int) -> dict:
    """Row counts and a few sums that would move if a re-parse stored anything else."""
    in_map = Round.match_map_id == match_map_id
    rounds = select(Round.id).where(in_map)
    return {
        "rounds": count(db, Round, in_map),
        "roster": count(db, MapRoster, MapRoster.match_map_id == match_map_id),
        "kills": count(db, KillEvent, KillEvent.round_id.in_(rounds)),
        "grenades": count(db, GrenadeThrow, GrenadeThrow.round_id.in_(rounds)),
        "player_rounds": count(db, PlayerRound, PlayerRound.round_id.in_(rounds)),
        "snapshots": count(db, RoundSnapshot, RoundSnapshot.round_id.in_(rounds)),
        "routes": count(db, PlayerMapRoute, PlayerMapRoute.match_map_id == match_map_id),
        "damage": db.scalar(
            select(func.sum(PlayerMap.damage)).where(PlayerMap.match_map_id == match_map_id)
        ),
        "kills_total": db.scalar(
            select(func.sum(PlayerMap.kills)).where(PlayerMap.match_map_id == match_map_id)
        ),
    }


def test_parse_ingest_and_reparse_from_tick_data(db, tmp_path, parsed):
    demo, bundle = _ingest(db, tmp_path, parsed, 1)
    assert bundle and not list(tmp_path.glob("*.zip")), "pack() leaves no file behind"
    steps = []
    match_map = analysis_store.ingest_map(db, demo, parsed, bundle=bundle, on_step=steps.append)
    assert steps[0] == "roster" and steps[-1] == "player_match" and "tickdata" in steps
    assert match_map.n_rounds == parsed.n_rounds > 0
    assert count(db, MapRoster) >= 10
    assert count(db, KillEvent) > 0 and count(db, PlayerRound) > 0
    assert count(db, PlayerMap) == count(db, MapRoster) == count(db, PlayerMatch)
    dataset = db.scalar(select(TickDataset).where(TickDataset.match_map_id == match_map.id))
    assert dataset.size_bytes == len(bundle)
    assert {"ticks", "flashes", "he_grenades", "economy"} <= set(dataset.tables)
    buys = db.execute(select(Round.number, Round.ct_buy, Round.t_buy).where(
        Round.match_map_id == match_map.id)).all()  # fmt: skip
    assert all(ct and t for _n, ct, t in buys)
    assert {(ct, t) for n, ct, t in buys if n in (1, 13)} == {("pistol", "pistol")}
    assert count(db, PlayerRound, PlayerRound.equip_value.is_(None)) == 0
    setups = count(db, RoundSnapshot, RoundSnapshot.moment == "setup")
    assert setups > 8 * parsed.n_rounds  # nearly everyone is still alive 20 s in
    assert count(db, RoundSnapshot, RoundSnapshot.moment == "plant") > 0
    lingering = GrenadeThrow.type.in_(("smoke", "inferno"))
    assert count(db, GrenadeThrow, lingering, GrenadeThrow.place == "") < 0.1 * count(
        db, GrenadeThrow, lingering
    )
    assert dataset.geometry["labels"] and tickdata.load_walks([dataset])
    assert count(db, ReplayRound, ReplayRound.match_map_id == match_map.id) == parsed.n_rounds
    before = snapshot(db, match_map.id)

    # The Demo is gone; the stored Tick Data is all a re-parse gets.
    again = tickdata.parsed_map(dataset.bundle, demo.filename, dataset.awpy_version)
    stored = dataset.bundle
    match_map = analysis_store.ingest_map(db, demo, again, bundle=stored)
    assert count(db, MatchMap) == 1
    assert snapshot(db, match_map.id) == before


def test_replay_from_the_tick_data(db, tmp_path, parsed):
    demo, bundle = _ingest(db, tmp_path, parsed, 2)
    match_map = analysis_store.ingest_map(db, demo, parsed, bundle=bundle)

    scene = replay.scene(db, match_map)
    assert scene["plate"]["url"] == f"/radars/{parsed.map_name}.png"
    assert len(scene["plate"]["extent"]) == 4 and scene["labels"]

    first = replay.round_data(db, match_map, 1)
    assert first["round"] == 1 and first["hz"] == replay.REPLAY_HZ
    assert len(first["players"]) >= 10 and first["events"]
    player = first["players"][0]
    assert len(player["x"]) == first["frames"] == len(player["hp"])
    assert replay.round_data(db, match_map, 1) == first
