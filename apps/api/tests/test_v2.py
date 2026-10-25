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


def test_scouting(client, auth, huns):
    url = f"/v2/teams/{huns['huns'].id}/scouting/{huns['spirit'].id}"
    body = client.get(url, headers=auth).json()
    assert body["opponent"]["name"] == "Spirit" and body["map"] == "de_anubis"
    anubis = next(m for m in body["maps"] if m["map"] == "de_anubis")
    assert (anubis["theirs"], anubis["won"], anubis["ours"]) == (1, 0, 1)
    # Their one T Round (R2) was a full buy; its plant names no site, so it counts as none.
    (full,) = [s for s in body["sites"] if s["buy"] == "full"]
    assert (full["n"], full["none"], full["won_none"]) == (1, 1, 1)
    assert body["window"]["h2h_maps"] == 1 and body["upcoming"] is None


def test_spatial_modes(client, auth, db, huns):
    from app.models import KillEvent, Player

    a = db.query(Player).filter_by(steamid=1).one()
    b = db.query(Player).filter_by(steamid=2).one()
    r2 = db.query(Round).filter_by(number=2).one()
    # b killed a on our CT Round 2 and nobody avenged him.
    db.add(KillEvent(round=r2, tick=10, attacker_id=b.id, victim_id=a.id, attacker_side="t",
                     victim_side="ct", weapon="ak47", victim_x=1.0, victim_y=2.0))  # fmt: skip
    db.add(PlayerRound(round=r2, player=b, team=huns["spirit"], side="t", kills=1))
    db.commit()
    url = f"/v2/teams/{huns['huns'].id}/spatial"
    q = {"opponent": huns["spirit"].id, "side": "ct"}
    trade = client.get(url, params={**q, "mode": "trade"}, headers=auth).json()
    assert trade["map"] == "de_anubis" and trade["us"]["rounds"] == 2
    assert trade["us"]["trade"]["players"] == [{"name": "a", "deaths": 1, "traded": 0, "pct": 0.0}]
    assert (
        trade["us"]["trade"]["lone"] == [[1.0, 2.0]] and trade["them"]["team"]["name"] == "Spirit"
    )
    # No Replay stored: the heat says nothing rather than failing.
    heat = client.get(url, params={**q, "mode": "heat"}, headers=auth).json()
    assert heat["us"]["heat"]["zones"] == [] and heat["windows"][0] == [0, 20]
    lurk = client.get(url, params={**q, "side": "t", "mode": "lurk"}, headers=auth).json()
    assert lurk["us"]["lurk"] is None


def test_utility(client, auth, db, huns):
    from app.models import GrenadeThrow, KillEvent, Player

    a = db.query(Player).filter_by(steamid=1).one()
    b = db.query(Player).filter_by(steamid=2).one()
    r1 = db.query(Round).filter_by(number=1).one()
    # Our flash pops at tick 100 and a kills b 0.5 s later (64 tick): a won fight.
    db.add(GrenadeThrow(round=r1, entity_id=1, type="flash", thrower_id=a.id, thrower_side="ct",
                        throw_tick=100, x=0.0, y=0.0))  # fmt: skip
    db.add(KillEvent(round=r1, tick=132, attacker_id=a.id, victim_id=b.id, attacker_side="ct",
                     victim_side="t", weapon="ak47"))  # fmt: skip
    db.add(PlayerRound(round=r1, player=b, team=huns["spirit"], side="t", deaths=1))
    db.commit()
    body = client.get(
        f"/v2/teams/{huns['huns'].id}/utility", params={"period": "all"}, headers=auth
    ).json()
    assert body["rounds"] == 3 and body["throws"] == 1 and body["map"] == "de_anubis"
    assert (body["sync"]["fights"], body["sync"]["won"], body["sync"]["flashes"]) == (1, 1, 1)
    (fight,) = [x for x in body["sync"]["bins"] if x["n"]]
    assert fight["from"] == 0.4 and fight["to"] == 0.6
    (p,) = body["players"]
    assert p["name"] == "a" and p["flashes_thrown"] == 1 and body["lineups"] == []


def test_practice_week(client, auth, huns):
    t = huns["huns"].id
    week = "2026-08-31"  # a Monday; the Match was on Tuesday 2026-09-01
    block = client.post(
        f"/v2/teams/{t}/blocks",
        json={"day": "2026-09-02", "start": "19:00", "end": "22:00", "kind": "scrim",
              "title": "Scrim", "opponent_id": huns["spirit"].id},
        headers=auth,
    ).json()  # fmt: skip
    assert block["hours"] == 3.0 and block["opponent"]["name"] == "Spirit"
    # Past midnight counts too.
    late = {"day": "2026-09-03", "start": "23:00", "end": "01:00", "kind": "review"}
    assert client.post(f"/v2/teams/{t}/blocks", json=late, headers=auth).json()["hours"] == 2.0
    goal = client.post(
        f"/v2/teams/{t}/goals",
        json={"kpi": "rounds", "side": "ct", "target": 40, "start_on": "2026-08-01",
              "due_on": "2026-12-01", "title": "CT"},
        headers=auth,
    ).json()  # fmt: skip
    # One CT Round won of two since August: 50%, its 80% range taking 40 in.
    assert goal["progress"]["value"] == 50.0 and goal["progress"]["of"] == 2
    assert goal["progress"]["verdict"] == "close" and goal["baseline"] is None
    item = client.post(
        f"/v2/teams/{t}/queue",
        json={"match_id": huns["match"].id, "map_number": 1, "round": 2, "t": 12.5,
              "title": "Retake", "tag": "Retake", "week": week},
        headers=auth,
    ).json()  # fmt: skip
    assert item["map"] == "Anubis" and item["watched"] is False
    watched = client.patch(f"/v2/queue/{item['id']}", json={"watched": True}, headers=auth).json()
    assert watched["watched"] is True
    body = client.get(f"/v2/teams/{t}/practice", params={"week": "2026-09-03"}, headers=auth).json()
    assert body["week"] == week and body["hours"]["scrim"] == 3.0 and body["hours"]["review"] == 2.0
    assert [q["title"] for q in body["queue"]] == ["Retake"]
    assert [g["title"] for g in body["goals"]] == ["CT"]
    moved = client.post(f"/v2/queue/{item['id']}/next-week", headers=auth).json()
    assert moved["id"] == item["id"]
    assert (
        client.get(f"/v2/teams/{t}/practice", params={"week": week}, headers=auth).json()["queue"]
        == []
    )
    bad = {"kpi": "nope", "target": 1, "due_on": "2026-12-01"}
    assert client.post(f"/v2/teams/{t}/goals", json=bad, headers=auth).status_code == 422
    assert client.delete(f"/v2/goals/{goal['id']}", headers=auth).status_code == 204


def test_v2_schema_names_leave_v1_alone():
    """A v2 shape named like a v1 one renames both in the contract (app__schemas_*)."""
    from app.main import app

    names = app.openapi()["components"]["schemas"]
    assert not [n for n in names if n.startswith("app__")]
