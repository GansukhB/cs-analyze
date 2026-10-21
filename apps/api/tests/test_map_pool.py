# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""A Team's map pool and the Active Duty Maps read from the data (docs/plans/05 TM-6)."""

from app.services import dbctx, map_pool, patches
from tests.test_gameplan import league, memory_cache  # noqa: F401


def test_the_active_maps_are_valves_on_the_day(db, league, monkeypatch):
    with dbctx.using(db):
        active = map_pool.active_duty()
    assert active == patches.pool_on() and len(active) == map_pool.ACTIVE_SIZE
    assert patches.pool_on("2025-08-01") == (
        "de_ancient", "de_dust2", "de_inferno", "de_mirage", "de_nuke", "de_overpass", "de_train"
    )  # fmt: skip
    # A file that names too few: the data's most played, topped up from it.
    monkeypatch.setattr(patches, "pool_on", lambda when=None: ("de_cache", "de_nuke"))
    with dbctx.using(db):
        db.info.clear()
        active = map_pool.active_duty()
    assert active == ("de_cache", "de_mirage", "de_nuke")


def test_a_day_belongs_to_the_latest_patch_before_it():
    assert patches.era("2026-07-08")["name"] == "Cache, C4"
    assert patches.era("2026-07-07")["date"] == "2026-04-20"
    assert patches.era("2020-01-01") is None and patches.era(None) is None
    assert patches.latest() == patches.every()[-1]


def test_a_pool_is_as_deep_as_its_maps_played_and_held(client, auth, db, league):
    a = league["a"]
    with dbctx.using(db):
        pool = map_pool.team_pool(a)
    mirage = next(r for r in pool["rows"] if r["map"] == "de_mirage")
    # Two Maps of Mirage, its only Map: its own share, so it holds, and it is deep.
    assert mirage["maps"] == 2 and mirage["status"] == "deep" and mirage["shrunk"] == pool["mean"]
    assert pool["depth"] == 1
    assert {r["status"] for r in pool["rows"] if r["map"] != "de_mirage"} == {"untested"}
    page = client.get(f"/teams/{a.id}", headers=auth).json()
    assert page["map_pool"]["depth"] == 1


def test_an_old_map_counts_less_than_a_recent_one(db, league):
    """TM-3: Nuke lost 4-8 a year before the Team's latest weighs about a twentieth
    of Nuke won 8-4 on its latest day, so the Map reads well above its 50%."""
    import datetime as dt

    from app.models import GameMap, Match
    from tests.test_gameplan import _map

    a, b = league["a"], league["b"]
    nuke = GameMap(name="de_nuke", display_name="Nuke")
    for number, day, first, second in ((90, dt.datetime(2025, 9, 1), b, a),
                                       (91, dt.datetime(2026, 10, 1), a, b)):  # fmt: skip
        match = Match(hltv_id=number, team1=a, team2=b, played_at=day)
        db.add(match)
        db.flush()
        _map(db, match, 1, nuke, first, second, players=league["players"])
    db.commit()
    with dbctx.using(db):
        pool = map_pool.team_pool(a)
    row = next(r for r in pool["rows"] if r["map"] == "de_nuke")
    assert row["share"] == 50.0 and row["shrunk"] > 55
