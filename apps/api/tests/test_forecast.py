"""The Forecast: Maps into a series, the veto played out, kept and graded (FC-2..FC-4)."""

import math
from datetime import date, datetime, timedelta

import pytest

from app.models import Forecast, Match, SeriesResult, Team
from app.services import dbctx, forecast, rating

MAPS = ["de_ancient", "de_anubis", "de_cache", "de_dust2", "de_inferno", "de_mirage", "de_nuke"]


@pytest.fixture(autouse=True)
def fresh_ratings():
    rating._LATEST.clear()
    yield
    rating._LATEST.clear()


def test_a_series_is_most_of_its_maps():
    assert forecast.series_chance([0.6], 1) == pytest.approx(0.6)
    assert forecast.series_chance([0.6] * 3, 3) == pytest.approx(0.6**2 * (3 - 2 * 0.6))
    # The order of the Maps doesn't matter, and a Bo3 favours the favourite.
    assert forecast.series_chance([0.7, 0.4, 0.5], 3) == pytest.approx(
        forecast.series_chance([0.5, 0.7, 0.4], 3)
    )
    assert forecast.series_chance([0.6] * 5, 5) > forecast.series_chance([0.6] * 3, 3) > 0.6


def test_the_veto_bans_our_worst_map_against_a_perfect_opponent():
    p = dict(zip(MAPS, (0.2, 0.5, 0.5, 0.5, 0.5, 0.5, 0.8), strict=True))
    share = dict.fromkeys(MAPS, 1 / 7)
    out = forecast.veto(p, share, "bo3", we_start=True)
    first = out["line"][0]
    assert first["who"] == "mine" and first["kind"] == "ban"
    minimax = {o["map"]: o["minimax"] for o in first["options"]}
    assert max(minimax, key=minimax.get) == "de_ancient"
    # An opponent who plays by our chances is the worst case: never better than expected.
    assert out["minimax"] <= out["expected"] + 1e-9
    assert len(out["maps"]) == 3 and out["decider"] in MAPS


def test_reliability_is_said_from_our_side(monkeypatch):
    band = {"lo": 0.8, "hi": 0.85, "n": 100, "won": 0.83, "low": 0.8, "high": 0.86}
    monkeypatch.setattr(forecast, "_committed", lambda: {"reliability": [band]})
    assert forecast.reliability(0.82)["won"] == 0.83
    ours = forecast.reliability(0.18)
    assert ours["won"] == pytest.approx(0.17) and ours["lo"] == 0.15 and ours["high"] == 0.2


def _teams(db):
    a, b = Team(name="The Huns"), Team(name="Rivals")
    db.add_all([a, b])
    db.commit()
    return a, b


def _results(db, a: str, b: str, a_wins: int, b_wins: int, start=date(2026, 1, 1)):
    day = start
    rows = [(True, i) for i in range(a_wins)] + [(False, i) for i in range(b_wins)]
    for won, i in rows:
        first, second = sorted((a, b), key=str.casefold)
        db.add(
            SeriesResult(
                source="vrs",
                key=f"{day}|{first}|{second}|{int(won)}|{i}",
                played_on=day,
                team_a=first,
                team_b=second,
                a_won=won if first == a else not won,
                roster_a=[],
                roster_b=[],
            )
        )
        day += timedelta(days=1)
    db.commit()


def test_an_unrated_team_gets_no_forecast(db):
    a, b = _teams(db)
    with dbctx.using(db):
        out = forecast.build(a, b)
    assert out["series"] == {}
    assert {x["code"] for x in out["limits"]} == {"unrated"}


def test_the_stronger_record_is_the_favourite(db):
    a, b = _teams(db)
    _results(db, "The Huns", "Rivals", a_wins=9, b_wins=3)
    with dbctx.using(db):
        out = forecast.build(a, b, today=date(2026, 2, 1))
    s = out["series"]
    assert s["bo3"]["expected"] > s["bo1"]["expected"] > 0.5
    assert {m["map"] for m in out["maps"]} == set(MAPS)
    # Offsets not yet shown to help: every Map the same, and the page says why.
    assert len({m["p"] for m in out["maps"]}) == 1
    assert "maps_even" in {x["code"] for x in out["limits"]}
    assert "cold" not in {x["code"] for x in out["limits"]}


def test_a_forecast_is_kept_then_graded_from_the_match(client, db, auth):
    a, b = _teams(db)
    _results(db, "The Huns", "Rivals", a_wins=9, b_wins=3)
    made = client.post("/forecasts", json={"my_team_id": a.id, "opponent_id": b.id}, headers=auth)
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["p_series"] > 0.5 and body["text"].startswith("Bo3: The Huns")
    assert body["graded_at"] is None

    listed = client.get("/forecasts", headers=auth).json()
    assert listed["summary"]["made"] == 1 and listed["summary"]["graded"] == 0

    db.add(
        Match(
            hltv_id=1,
            team1_id=b.id,
            team2_id=a.id,
            team1_score=1,
            team2_score=2,
            played_at=datetime.now() + timedelta(hours=2),
        )
    )
    db.commit()
    listed = client.get("/forecasts", headers=auth).json()
    item = listed["items"][0]
    assert item["result"]["won"] is True and item["result"]["score"] == "2-1"
    assert item["log_loss"] == pytest.approx(-math.log(item["p_series"]), abs=1e-3)
    assert listed["summary"]["graded"] == 1 and listed["summary"]["favourites_won"] == 1
    assert client.get(f"/forecasts/{item['id']}", headers=auth).json()["id"] == item["id"]


def test_an_unrated_fixture_cannot_be_kept(client, db, auth):
    a, b = _teams(db)
    out = client.post("/forecasts", json={"my_team_id": a.id, "opponent_id": b.id}, headers=auth)
    assert out.status_code == 409
    assert db.query(Forecast).count() == 0


def test_a_team_page_splits_its_maps_by_the_opponents_tier(client, db, auth):
    import datetime as dt

    from app.models import GameMap, Player
    from tests.test_gameplan import _map

    teams = [Team(name=n, hltv_id=i + 1) for i, n in enumerate(("Alpha", "Bravo"))]
    db.add_all(teams)
    db.flush()
    a, b = teams
    players = {t.id: [Player(steamid=t.id * 100 + i, name=f"{t.name[0]}{i}") for i in range(5)]
               for t in teams}  # fmt: skip
    _results(db, "Alpha", "Bravo", a_wins=9, b_wins=3, start=date(2026, 1, 1))
    mirage = GameMap(name="de_mirage", display_name="Mirage")
    match = Match(hltv_id=1, team1=a, team2=b, played_at=dt.datetime(2026, 3, 1))
    db.add(match)
    db.flush()
    _map(db, match, 1, mirage, a, b, players=players)
    db.commit()
    s = client.get(f"/teams/{a.id}", headers=auth).json()["strength"]
    assert s["name"] == "Alpha" and s["series"] == 12 and len(s["trend"]) >= 2
    assert sum(t["maps"] for t in s["tiers"]) == 1 and s["tiers"][0]["won"] == 1


def test_the_veto_plays_on_from_where_it_stands():
    """GP-10: our chance after their ban, every option at the next step valued."""
    maps = ["de_ancient", "de_anubis", "de_cache", "de_dust2", "de_inferno", "de_mirage",
            "de_nuke"]  # fmt: skip
    p = dict(zip(maps, (0.7, 0.3, 0.5, 0.5, 0.5, 0.5, 0.5), strict=True))
    share = dict.fromkeys(maps, 1 / 7)
    fresh = forecast.veto_from(p, share, "bo3", True, [])
    assert fresh["expected"] == forecast.veto(p, share, "bo3", True)["expected"]
    # We ban our worst; then it is their ban, with their likely choice per Map.
    after = forecast.veto_from(p, share, "bo3", True, ["de_anubis"])
    assert after["next"]["who"] == "theirs" and after["next"]["kind"] == "ban"
    assert all(o["chance"] is not None for o in after["next"]["options"])
    assert len(after["line"]) == 5 and len(after["maps"]) == 3
    with pytest.raises(ValueError):
        forecast.veto_from(p, share, "bo3", True, ["de_anubis", "de_anubis"])


def test_the_lab_needs_ratings_for_a_veto(client, auth, db):
    from app.models import Team

    a, b = Team(name="Alpha"), Team(name="Bravo")
    db.add_all([a, b])
    db.commit()
    out = client.post(f"/gameplan/{a.id}/vs/{b.id}/veto", headers=auth, json={"format": "bo3"})
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["veto"] is None and len(body["maps"]) == 7


def test_one_player_in_for_another_moves_the_rating_a_fifth(db):
    """FC-9: "s1 in for p5" moves the Huns a fifth of the way to s1's Team."""
    a, b = _teams(db)
    huns, rivals, stars = ([f"{c}{i}" for i in range(1, 6)] for c in "pqs")
    day = date(2026, 1, 1)
    games = [("Stars", stars, "Rivals", rivals, True)] * 6 + [
        ("The Huns", huns, "Rivals", rivals, True)
    ] * 4
    for i, (x, rx, y, ry, x_won) in enumerate(games):
        first, second = sorted((x, y), key=str.casefold)
        flip = first != x
        db.add(SeriesResult(source="vrs", key=f"{day}|{first}|{second}|{i}", played_on=day,
                            team_a=first, team_b=second, a_won=x_won != flip,
                            roster_a=ry if flip else rx, roster_b=rx if flip else ry))  # fmt: skip
        day += timedelta(days=1)
    db.commit()
    with dbctx.using(db):
        base = forecast.standing(a)
        moved = forecast.standing(a, ["p1", "p2", "p3", "p4", "s1"])
        out = forecast.build(a, b, my_lineup=["p1", "p2", "p3", "p4", "s1"], today=day)
        stars_rating = rating.current().teams[rating._key("Stars")].rating
    assert moved.swapped == 1 and not moved.lineup_changed
    assert moved.rating == pytest.approx(base.rating + (stars_rating - base.rating) / 5, abs=0.1)
    assert "swap" in {x["code"] for x in out["limits"]}
    assert out["why"][0]["code"] == "gap"
