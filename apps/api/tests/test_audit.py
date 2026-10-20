# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""The timeout audit and opening duels (docs/plans/07 RV-8)."""

from sqlalchemy import select

from app.models import Match, MatchMap, Round
from app.services import audit, dbctx
from tests.test_gameplan import league, memory_cache  # noqa: F401


def _alpha_bravo(db, league):
    a, b = league["a"], league["b"]
    match = db.scalar(select(Match).where(Match.team1_id == a.id, Match.team2_id == b.id))
    return db.scalar(select(MatchMap).where(MatchMap.match_id == match.id)), a, b


def _script(db, mm, a, b, timeouts=True):
    """Alpha loses 2-4, calls a timeout and wins 5, loses 6-8, goes on without one
    and wins 9-12."""
    lost = {2, 3, 4, 6, 7, 8}
    for r in db.scalars(select(Round).where(Round.match_map_id == mm.id)):
        r.winner_team_id = b.id if r.number in lost else a.id
        alpha_ct = r.ct_team_id == a.id
        called = timeouts and r.number == 5
        r.ct_timeout = (called and alpha_ct) if timeouts else None
        r.t_timeout = (called and not alpha_ct) if timeouts else None
        r.tech_timeout = False if timeouts else None
    db.commit()


def test_a_timeout_with_its_run_and_the_run_that_went_without(db, league):
    mm, a, b = _alpha_bravo(db, league)
    _script(db, mm, a, b)
    with dbctx.using(db):
        out = audit.map_audit(mm)
        pool = audit.pool()
    assert out["known"]
    [called] = out["timeouts"]
    assert (called["round"], called["team_id"], called["lost_before"], called["won_next"]) == (
        5, a.id, 3, True,
    )  # fmt: skip
    # Alpha after 6-8 with two left, and Bravo after losing 9-11.
    missed = [(m["round"], m["team_id"], m["left"], m["won_next"]) for m in out["missed"]]
    assert missed == [(9, a.id, 2, True), (12, b.id, 3, False)]
    assert pool["after_timeout"] == {"rounds": 1, "won": 1, "pct": 100.0}
    assert pool["without"] == {"rounds": 2, "won": 1, "pct": 50.0}
    alpha = [o for o in out["openings"] if o["team_id"] == a.id]
    assert alpha and alpha[0]["attempts"] > 0


def test_tick_data_without_timeouts_says_nothing_about_them(db, league, client, auth):
    mm, a, b = _alpha_bravo(db, league)
    _script(db, mm, a, b, timeouts=False)
    body = client.get(f"/matches/{mm.match_id}/maps/1/audit", headers=auth).json()
    assert body["known"] is False and body["timeouts"] == [] and body["missed"] == []
    assert body["openings"] and body["pool"]["maps"] == 0
