# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""Eco-adjusted duels and Swing by opponent tier (docs/plans/04 PL-6)."""

import pytest
from sqlalchemy import select

from app.models import MatchMap
from app.services import dbctx, duels
from tests.test_gameplan import league, memory_cache  # noqa: F401


def test_a_rifle_beating_a_pistol_is_worth_less_than_the_reverse(db, league, monkeypatch):
    star = league["players"][league["a"].id][0].id
    # The Pool: rifles beat pistols 8 times in 10, either Side.
    pool = [(1, 2, side, "rifle", "pistol", 0) for side in ("ct", "t") for _ in range(40)]
    pool += [(2, 1, side, "pistol", "rifle", 0) for side in ("ct", "t") for _ in range(10)]
    # Our star, with a rifle: 3 pistols killed, then dead to one.
    his = [(star, 9, "ct", "rifle", "pistol", 1)] * 3 + [(9, star, "t", "pistol", "rifle", 2)]
    monkeypatch.setattr(duels, "_feed", lambda ids=None: iter(his if ids else pool))
    with dbctx.using(db):
        table = duels.table()
        assert table[("ct", "rifle", "pistol")] == pytest.approx(0.8, abs=0.02)
        mine = duels.player(star, list(db.scalars(select(MatchMap.id))))
    # Won 3 of 4 where the guns expected 3.2: a little under, per Round he played.
    assert (mine["duels"], mine["won"]) == (4, 3)
    assert mine["expected_pct"] == pytest.approx(80.0, abs=1.0)
    assert mine["over_per_round"] < 0


def test_the_player_page_carries_duels_and_tiers(client, auth, db, league):
    star = league["players"][league["a"].id][0]
    page = client.get(f"/players/{star.steamid}", headers=auth).json()
    assert page["duels"]["duels"] > 0
    # Without Ratings every opponent is in the last tier.
    assert [t["tier"] for t in page["by_tier"]] in ([], ["Бусад"])
