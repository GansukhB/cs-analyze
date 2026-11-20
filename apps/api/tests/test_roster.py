# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""Who played for a Team when (docs/plans/05 TM-10)."""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models import Match
from app.services import warmer
from tests.test_gameplan import league, memory_cache  # noqa: F401


def test_a_long_gap_splits_a_players_time_into_two_stretches(client, auth, db, league):
    a = league["a"]
    body = client.get(f"/teams/{a.id}/roster", headers=auth).json()
    assert body["from"] == "2026-09-02" and body["to"] == "2026-09-03"
    assert len(body["players"]) == 5
    assert all(len(p["spans"]) == 1 and p["maps"] == 2 for p in body["players"])
    # Alpha's Match against Charlie was played months earlier: a second stretch.
    earlier = db.scalar(
        select(Match).where(Match.team2_id == league["c"].id, Match.team1_id == a.id)
    )
    earlier.played_at = dt.datetime(2026, 3, 1)
    db.commit()
    # A stored answer (docs/adr/0015): read stale at once, then the warm-up has it.
    res = client.get(f"/teams/{a.id}/roster", headers=auth)
    assert res.headers["X-Answer"] == "stale"
    warmer.Warmer(sessionmaker(bind=db.get_bind(), expire_on_commit=False))._wanted()
    res = client.get(f"/teams/{a.id}/roster", headers=auth)
    assert res.headers["X-Answer"] == "fresh"
    spans = res.json()["players"][0]["spans"]
    assert [(s["from"], s["to"], s["maps"]) for s in spans] == [
        ("2026-03-01", "2026-03-01", 1), ("2026-09-03", "2026-09-03", 1),
    ]  # fmt: skip
    assert client.get("/teams/999999/roster", headers=auth).status_code == 404
