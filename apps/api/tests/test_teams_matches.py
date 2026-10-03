import datetime as dt

import pytest

from app.models import (
    Demo,
    GameMap,
    MapRoster,
    Match,
    MatchMap,
    Player,
    PlayerMap,
    Round,
    Team,
    Tournament,
)
from app.models.base import utcnow


@pytest.fixture
def fixture_data(db):
    """Vitality beat Spirit 2-1 (one map parsed), and played an unparsed match vs FaZe."""
    vitality = Team(name="Vitality", hltv_id=9565, slug="vitality")
    spirit = Team(name="Spirit", hltv_id=7020)
    faze = Team(name="FaZe")
    anubis = GameMap(name="de_anubis", display_name="Anubis")
    final = Match(
        hltv_id=1, slug="vitality-vs-spirit", team1=vitality, team2=spirit, score="2 - 1",
        team1_score=2, team2_score=1, tournament=Tournament(name="Major"),
        played_at=dt.datetime(2026, 9, 1),
    )  # fmt: skip
    older = Match(
        hltv_id=2, team1=faze, team2=vitality, score="0 - 2", team1_score=0, team2_score=2,
        played_at=dt.datetime(2026, 8, 1), demo_checked_at=utcnow(),
    )  # fmt: skip
    parsed = MatchMap(
        match=final, map_number=1, game_map=anubis, team1=vitality, team2=spirit,
        team1_score=13, team2_score=8, winner=vitality, n_rounds=3, parsed_at=utcnow(),
    )  # fmt: skip
    unparsed = MatchMap(match=final, map_number=2, team1_score=10, team2_score=13)
    zywoo, donk = Player(steamid=1, name="ZywOo"), Player(steamid=2, name="donk")
    demo = Demo(match=final, map="anubis", is_downloaded=True)
    db.add_all([final, older, parsed, unparsed, demo])
    db.flush()
    db.add_all([
        Round(match_map=parsed, number=1, start_tick=0, freeze_end_tick=1, end_tick=2,
              official_end_tick=3, winner_side="ct", winner_team=vitality, ct_team=vitality,
              t_team=spirit, end_reason="t_killed"),
        Round(match_map=parsed, number=2, start_tick=0, freeze_end_tick=1, end_tick=2,
              official_end_tick=3, winner_side="t", winner_team=spirit, ct_team=vitality,
              t_team=spirit, end_reason="bomb_exploded", bomb_plant_tick=2, bomb_site="B"),
        Round(match_map=parsed, number=3, start_tick=0, freeze_end_tick=1, end_tick=2,
              official_end_tick=3, winner_side="t", winner_team=vitality, ct_team=spirit,
              t_team=vitality, end_reason="ct_killed"),
        MapRoster(match_map=parsed, player=zywoo, team=vitality, rounds_total=3),
        MapRoster(match_map=parsed, player=donk, team=spirit, rounds_total=3),
        PlayerMap(match_map=parsed, player=zywoo, team=vitality, kills=5, deaths=1, kd_diff=4,
                  adr=110.5, kast_pct=100.0, hs_pct=40.0),
        PlayerMap(match_map=parsed, player=donk, team=spirit, kills=3, deaths=4, kd_diff=-1),
    ])  # fmt: skip
    db.commit()
    return {"vitality": vitality, "spirit": spirit, "final": final, "older": older}


def test_team_list_sorts_by_parsed_maps(client, auth, fixture_data):
    body = client.get("/teams", headers=auth).json()
    assert [t["name"] for t in body["teams"]] == ["Vitality", "Spirit", "FaZe"]
    vitality = body["teams"][0]
    assert vitality["matches"] == 2 and vitality["maps"] == 1
    assert vitality["hltv_url"] == "https://www.hltv.org/team/9565/vitality"
    assert body["teams"][2]["identified"] is False
    assert body["parsed_teams"] == 2 and body["total_matches"] == 2


def test_team_detail(client, auth, fixture_data):
    body = client.get(f"/teams/{fixture_data['vitality'].id}", headers=auth).json()
    assert body["record"] == {"won": 2, "lost": 0, "drawn": 0}
    final, older = body["results"]
    assert final["opponent"]["name"] == "Spirit" and final["outcome"] == "win"
    assert final["maps"][0] == {
        "name": "Anubis", "number": 1, "score": "13-8", "attributed": True, "won": True,
        "parsed": True,
    }  # fmt: skip
    assert final["maps"][1]["attributed"] is False and final["maps"][1]["score"] == "10-13"
    assert final["demo"]["word"] == "parsed" and final["n_parsed"] == 1
    # Seen from Vitality's side, FaZe 0-2 Vitality is 2-0.
    assert (older["ours"], older["theirs"], older["demo"]["word"]) == (2, 0, "no demo")
    assert body["map_record"] == [{"map": "Anubis", "played": 1, "won": 1, "lost": 0, "pct": 100}]
    assert [p["name"] for p in body["players"]] == ["ZywOo"]
    assert client.get("/teams/999", headers=auth).status_code == 404


def test_match_and_map(client, auth, fixture_data):
    match = client.get(f"/matches/{fixture_data['final'].id}", headers=auth).json()
    assert [m["label"] for m in match["maps"]] == ["Anubis", "?"]
    # Parsed but no tick bundle: it is still where the match page lands.
    assert match["default_map"] == 1 and match["maps"][0]["playable"] is False

    detail = client.get(f"/matches/{fixture_data['final'].id}/maps/1", headers=auth).json()
    assert detail["scene"] is None and detail["parsed"] is True
    assert [r["score"] for r in detail["rounds"]] == ["1-0", "1-1", "2-1"]
    assert [r["half_break"] for r in detail["rounds"]] == [False, False, True]
    second = detail["rounds"][1]
    assert second["planted"] is True and second["reason"] == "bomb exploded"
    home, away = detail["scoreboard"]
    assert home["team"]["name"] == "Vitality" and home["won"] is True
    assert home["players"][0]["name"] == "ZywOo" and home["players"][0]["adr"] == 110.5

    base = f"/matches/{fixture_data['final'].id}"
    assert client.get(f"{base}/maps/1/rounds/1", headers=auth).status_code == 404
    assert client.get(f"{base}/maps/9", headers=auth).status_code == 404
    assert client.get("/matches/999", headers=auth).status_code == 404


def test_match_without_parsed_maps(client, auth, fixture_data):
    match = client.get(f"/matches/{fixture_data['older'].id}", headers=auth).json()
    assert match["maps"] == [] and match["default_map"] is None
