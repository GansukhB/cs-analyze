"""The v2 pages' endpoints: Player rating, a my team's numbers, the overview and
Upcoming matches."""

import datetime as dt

import pytest

from app.models import (
    GameMap,
    MapRoster,
    Match,
    MatchMap,
    Player,
    PlayerMap,
    PlayerRound,
    Round,
    Team,
    Workspace,
    WorkspaceTeam,
)
from app.models.base import utcnow
from app.services import dbctx, player_rating, team_numbers


@pytest.fixture
def huns(db, workspace):
    """The Huns (a my team) beat Spirit 13-8 on Anubis: three stored Rounds."""
    huns, spirit = Team(name="The Huns"), Team(name="Spirit")
    db.add(WorkspaceTeam(workspace=workspace, team=huns))
    anubis = GameMap(name="de_anubis", display_name="Anubis")
    match = Match(
        team1=huns, team2=spirit, team1_score=1, team2_score=0, played_at=dt.datetime(2026, 9, 1)
    )
    mm = MatchMap(
        match=match, map_number=1, game_map=anubis, team1=huns, team2=spirit, team1_score=13,
        team2_score=8, winner=huns, n_rounds=3, parsed_at=utcnow(),
    )  # fmt: skip
    a, b = Player(steamid=1, name="a"), Player(steamid=2, name="b")
    db.add_all([match, mm])
    db.flush()

    def rnd(n, winner, ct, t, **kw):
        ticks = {"start_tick": 0, "freeze_end_tick": 1, "end_tick": 2, "official_end_tick": 3}
        sides = {"winner_team": winner, "ct_team": ct, "t_team": t}
        return Round(match_map=mm, number=n, **sides, **ticks, **kw)

    r1 = rnd(1, huns, huns, spirit, ct_buy="pistol", t_buy="pistol")
    r2 = rnd(2, spirit, huns, spirit, bomb_plant_tick=2, ct_buy="force", t_buy="full")
    r3 = rnd(3, huns, spirit, huns, bomb_plant_tick=2, t_buy="full", ct_buy="full")
    db.add_all([r1, r2, r3])
    db.flush()
    db.add_all([
        MapRoster(match_map=mm, player=a, team=huns, rounds_total=3),
        MapRoster(match_map=mm, player=b, team=spirit, rounds_total=3),
        PlayerMap(match_map=mm, player=a, team=huns, rounds_played=3, kills=4, deaths=1,
                  assists=1, damage=330, kast_pct=100.0, headshots=2, opening_kills=1),
        PlayerMap(match_map=mm, player=b, team=spirit, rounds_played=3, kills=1, deaths=4,
                  damage=120, kast_pct=33.3),
        PlayerRound(round=r1, player=a, team=huns, side="ct", kills=2, opening_kill=True),
        PlayerRound(round=r2, player=a, team=huns, side="ct", deaths=1, traded=True),
        PlayerRound(round=r3, player=a, team=huns, side="t", kills=2, opening_death=True),
    ])  # fmt: skip
    db.commit()
    return {"huns": huns, "spirit": spirit, "match": match, "mm": mm}


def test_player_rating_is_the_published_approximation():
    # 0.7 KPR, 0.65 DPR, 0.13 APR, 72% KAST, 78 ADR over 100 Rounds.
    value = player_rating.rating(100, 70, 65, 13, 7800, 72.0)
    assert value == pytest.approx(1.108, abs=0.001)
    # A game of deaths alone floors at 0, as HLTV's does.
    assert player_rating.rating(10, 0, 10, 0, 0, 0.0) == 0.0


def test_team_numbers(db, huns):
    with dbctx.using(db):
        n = team_numbers.numbers(huns["huns"].id, [huns["mm"]])
    got = {k: (v.won, v.of) for k, v in n.items()}
    assert got["maps"] == (1, 1)
    assert got["rounds"] == (2, 3) and got["rounds_ct"] == (1, 2) and got["rounds_t"] == (1, 1)
    assert got["pistol"] == (1, 1) and got["force"] == (0, 1)
    # Planted on our T Round and won it; planted against our CT and lost the retake.
    assert got["post_plant"] == (1, 1) and got["retake"] == (0, 1)
    assert got["opening"] == (1, 2) and got["trade"] == (1, 1)


def test_overview(client, auth, huns):
    body = client.get(
        f"/v2/teams/{huns['huns'].id}/overview", params={"period": "all"}, headers=auth
    ).json()
    assert body["kpis"]["maps"] == {"won": 1, "of": 1, "pct": 100.0, "prev": None}
    assert body["n_matches"] == 1 and body["n_maps"] == 1
    assert body["form"][0]["won"] is True and body["form"][0]["opponent"] == "Spirit"
    (player,) = body["players"]
    assert player["name"] == "a" and player["rating"] > 1.5
    assert body["trend"][0]["map"] == "de_anubis"
    assert body["upcoming"] is None
    # Not one of the Workspace's my teams.
    assert client.get(f"/v2/teams/{huns['spirit'].id}/overview", headers=auth).status_code == 404


def test_upcoming_match(client, auth, db, huns):
    made = client.post(
        "/v2/upcoming",
        json={"team_id": huns["huns"].id, "opponent_id": huns["spirit"].id,
              "starts_at": "2026-09-01T18:00:00+08:00", "best_of": 3, "tournament": "Cup"},
        headers=auth,
    )  # fmt: skip
    assert made.status_code == 201
    u = made.json()
    assert u["starts_at"] == "2026-09-01T10:00:00Z" and len(u["checklist"]) == 6
    listed = client.get("/v2/upcoming", params={"past": True}, headers=auth).json()["upcoming"]
    # The stored Match between the two Teams that day is taken for it.
    assert listed[0]["match_id"] == huns["match"].id
    patched = client.patch(
        f"/v2/upcoming/{u['id']}",
        json={"checklist": [{"text": "Veto", "done": True}],
              "counters": [{"key": "k", "title": "B stack"}]},
        headers=auth,
    ).json()  # fmt: skip
    assert patched["checklist"] == [{"text": "Veto", "done": True}]
    assert patched["counters"][0]["title"] == "B stack"
    # Only a my team plays one, never against itself.
    bad = {
        "team_id": huns["spirit"].id,
        "opponent_id": huns["huns"].id,
        "starts_at": "2026-10-01T10:00:00Z",
    }
    assert client.post("/v2/upcoming", json=bad, headers=auth).status_code == 404
    same = {
        "team_id": huns["huns"].id,
        "opponent_id": huns["huns"].id,
        "starts_at": "2026-10-01T10:00:00Z",
    }
    assert client.post("/v2/upcoming", json=same, headers=auth).status_code == 422
    # Another Workspace never reaches it.
    other = Workspace(name="Other")
    db.add(other)
    db.commit()
    from app.models import UpcomingMatch

    db.get(UpcomingMatch, u["id"]).workspace_id = other.id
    db.commit()
    assert client.delete(f"/v2/upcoming/{u['id']}", headers=auth).status_code == 404


def test_match_report(client, auth, huns):
    url = f"/v2/teams/{huns['huns'].id}/matches/{huns['match'].id}/maps/1/report"
    body = client.get(url, headers=auth).json()
    assert (body["ours"], body["theirs"]) == (13, 8) and body["them"]["name"] == "Spirit"
    assert [r["won"] for r in body["rounds"]] == [True, False, True]
    assert [(h["side"], h["ours"], h["theirs"]) for h in body["halves"]] == [
        ("ct", 1, 1),
        ("t", 1, 0),
    ]
    pistol = next(b for b in body["buys"] if b["buy"] == "pistol")
    assert (pistol["won"], pistol["of"], pistol["won_rounds"]) == (1, 1, [1])
    assert body["teams"][0]["team"]["name"] == "The Huns"
    assert body["quick"]["post_plant"] == [1, 1]
    listed = client.get(f"/v2/teams/{huns['huns'].id}/matches", headers=auth).json()["matches"]
    assert listed[0]["maps"][0]["score"] == "13–8"


def test_player_profile_and_note(client, auth, huns):
    url = f"/v2/teams/{huns['huns'].id}/players/1/profile"
    body = client.get(url, headers=auth).json()
    assert body["name"] == "a" and body["rounds"] == 3 and body["maps"] == 1
    # Read from the Rounds: four kills and a death over three of them.
    assert body["kpis"]["rating"] > 1.0
    # Three Rounds is no Pool: no axis is placed against nobody.
    assert body["pool_players"] == 0 and body["axes"]["firepower"] is None
    assert body["form"]["maps"][0]["map"] == "de_anubis" and body["note"] is None
    put = client.put("/v2/players/1/note", json={"text": " Pop flash-ийг хүлээ "}, headers=auth)
    assert put.json()["text"] == "Pop flash-ийг хүлээ"
    assert client.get(url, headers=auth).json()["note"]["text"] == "Pop flash-ийг хүлээ"
    roster = client.get(f"/v2/teams/{huns['huns'].id}/players", headers=auth).json()
    assert roster["players"] == [{"steamid": "1", "name": "a"}]
