# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""A Team's map pool and the Active Duty Maps read from the data (docs/plans/05 TM-6)."""

from app.services import dbctx, map_pool, mapstrategy
from tests.test_gameplan import league, memory_cache  # noqa: F401


def test_the_active_maps_come_from_the_data_topped_up_to_seven(db, league):
    with dbctx.using(db):
        active = map_pool.active_duty()
    assert len(active) == map_pool.ACTIVE_SIZE and "de_mirage" in active
    assert set(active) <= set(mapstrategy.ACTIVE_DUTY) | {"de_mirage"}


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
