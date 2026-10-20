# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""The timeout card (docs/plans/06 GP-4)."""

from types import SimpleNamespace

import pytest

from app.services import stats, timeout_card
from tests.test_gameplan import league, memory_cache  # noqa: F401


def test_pressure_is_after_two_lost_or_their_own_timeout(monkeypatch):
    won = {1: 7, 2: 9, 3: 9, 4: 9, 5: 7, 12: 9, 13: 9, 14: 7}
    rounds = [SimpleNamespace(id=n, match_map_id=1, number=n, winner=w) for n, w in won.items()]
    monkeypatch.setattr(timeout_card, "_timeouts", lambda team, ids: {5})
    # Lost 2 and 3: under pressure in 4 and 5 (5 also after their timeout). 13
    # starts a half afresh, so 14 follows one loss, not two.
    assert timeout_card._pressure(7, rounds) == {4, 5}


def test_a_move_needs_to_be_likely_real():
    assert stats.chance_higher(8, 10, 2, 10) > 0.95
    assert stats.chance_higher(3, 6, 3, 6) == pytest.approx(0.5)


def test_the_game_plan_serves_it(client, auth, db, league, memory_cache):
    a, b = league["a"], league["b"]
    card = client.get(f"/gameplan/{a.id}/vs/{b.id}/timeout/de_mirage", headers=auth)
    assert card.status_code == 200, card.text
    body = card.json()
    assert body["rounds"] > 0 and {s["side"] for s in body["sides"]} == {"t", "ct"}
    assert "after_timeout" in body["pool"]
