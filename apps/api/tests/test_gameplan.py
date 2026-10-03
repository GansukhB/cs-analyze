import datetime as dt

import pytest
from sqlalchemy import delete, select

from app.config import get_settings
from app.models import (
    GameMap,
    KillEvent,
    MapRoster,
    Match,
    MatchMap,
    Player,
    PlayerMap,
    PlayerMapDuel,
    PlayerMapRoute,
    PlayerRound,
    Round,
    Team,
)
from app.models.base import utcnow
from app.routers import gameplan as gameplan_router
from app.services import dbctx, gameplan, heatmap_groups, mapstrategy

TABS = ["decision", "verdict", "metrics", "h2h", "maps", "players", "duels", "roles", "edge",
        "heatmaps", "movement", "todo"]  # fmt: skip


@pytest.fixture(autouse=True)
def memory_cache(monkeypatch, tmp_path):
    """Redis replaced by a dict, and the drawn pictures kept out of the repo."""
    store: dict = {}
    monkeypatch.setattr(gameplan_router, "_cache_get", lambda key: store.get(key))
    monkeypatch.setattr(
        gameplan_router, "_cache_set", lambda key, value: store.__setitem__(key, value)
    )
    monkeypatch.setattr(get_settings(), "hltv_data_dir", tmp_path)
    return store


def _map(db, match, number, game_map, ct_first, t_first, players):
    """A parsed map of 12 rounds: ``ct_first`` holds CT for 1-6, then sides swap.

    ``ct_first`` wins 5 of its 6 CT rounds and 3 of its 6 T rounds (8-4). Every
    round has one kill per side, positioned, so the grid has points to draw.
    """
    mm = MatchMap(
        match=match, map_number=number, game_map=game_map, team1=ct_first, team2=t_first,
        tickrate=64, n_rounds=12, parsed_at=utcnow(),
    )  # fmt: skip
    db.add(mm)
    db.flush()
    score = {ct_first.id: 0, t_first.id: 0}
    for team, roster in ((ct_first, players[ct_first.id]), (t_first, players[t_first.id])):
        for p in roster:
            db.add(MapRoster(match_map=mm, player=p, team=team, rounds_total=12))
            db.add(PlayerMap(match_map=mm, player=p, team=team, rounds_played=12, kills=6,
                             deaths=6, damage=900, opening_kills=1, opening_deaths=1))  # fmt: skip
    for n in range(1, 13):
        ct, t = (ct_first, t_first) if n <= 6 else (t_first, ct_first)
        winner = ct_first if (n - 1) % 6 < (5 if n <= 6 else 3) else t_first
        score[winner.id] += 1
        rnd = Round(
            match_map=mm, number=n, start_tick=n * 1000, freeze_end_tick=n * 1000 + 100,
            end_tick=n * 1000 + 900, official_end_tick=n * 1000 + 950,
            winner_side="ct" if winner is ct else "t", winner_team=winner, ct_team=ct, t_team=t,
            end_reason="t_killed", bomb_plant_tick=n * 1000 + 700 if n % 3 == 0 else None,
            bomb_site="A" if n % 3 == 0 else "",
        )  # fmt: skip
        db.add(rnd)
        db.flush()
        ct_p, t_p = players[ct.id], players[t.id]
        for i, (killer, victim, side) in enumerate(
            ((ct_p[0], t_p[0], "ct"), (t_p[1], ct_p[1], "t"))
        ):
            db.add(KillEvent(
                round=rnd, tick=rnd.freeze_end_tick + 640 * (i + 1), attacker=killer, victim=victim,
                attacker_side=side, victim_side="t" if side == "ct" else "ct", weapon="ak47",
                attacker_x=-500.0 + n * 40 + i * 300, attacker_y=200.0 + n * 25,
                attacker_z=0.0, victim_x=-480.0 + n * 40, victim_y=260.0 + n * 20, victim_z=0.0,
                attacker_place="BombsiteA", victim_place="Middle",
            ))  # fmt: skip
        for team, side in ((ct, "ct"), (t, "t")):
            for j, p in enumerate(players[team.id]):
                busy = j < 2
                db.add(PlayerRound(round=rnd, player=p, team=team, side=side, kills=int(busy),
                                   deaths=int(busy), damage=80, kast=j < 3,
                                   opening_kill=j == 0, opening_death=j == 1))  # fmt: skip
    for team, side in ((ct_first, "ct"), (t_first, "t")):
        p = players[team.id][0]
        db.add(PlayerMapRoute(
            match_map=mm, player=p, team=team, side=side, route_key="Spawn>Middle>BombsiteA",
            places=["Spawn", "Middle", "BombsiteA"], rounds=5, kills=3, deaths=2, rounds_won=3,
            path=[{"place": "Spawn", "x": -900, "y": 0}, {"place": "Middle", "x": -500, "y": 200},
                  {"place": "BombsiteA", "x": -100, "y": 400}],
        ))  # fmt: skip
    home, away = players[ct_first.id], players[t_first.id]
    db.add_all([
        PlayerMapDuel(match_map=mm, killer=home[0], victim=away[0], killer_team=ct_first,
                      victim_team=t_first, side="ct", kills=2),
        PlayerMapDuel(match_map=mm, killer=away[1], victim=home[1], killer_team=t_first,
                      victim_team=ct_first, side="t", kills=1),
    ])  # fmt: skip
    mm.team1_score, mm.team2_score = score[ct_first.id], score[t_first.id]
    mm.winner = ct_first if score[ct_first.id] > score[t_first.id] else t_first
    return mm


@pytest.fixture
def league(db):
    """Three teams, every pair met once on Mirage: A beat B, A beat C, B beat C."""
    teams = [Team(name=name, hltv_id=i + 1) for i, name in enumerate(("Alpha", "Bravo", "Charlie"))]
    db.add_all(teams)
    db.flush()
    players = {
        t.id: [Player(steamid=t.id * 100 + i, name=f"{t.name[0]}{i}") for i in range(5)]
        for t in teams
    }
    mirage = GameMap(name="de_mirage", display_name="Mirage")
    a, b, c = teams
    for number, (home, away, day) in enumerate(((a, b, 3), (a, c, 2), (b, c, 1)), start=1):
        match = Match(hltv_id=number, team1=home, team2=away, played_at=dt.datetime(2026, 9, day))
        db.add(match)
        db.flush()
        _map(db, match, 1, mirage, home, away, players=players)
    db.commit()
    return {"a": a, "b": b, "c": c, "players": players}


def test_pistol_rounds_follow_mr12_and_overtime():
    assert mapstrategy.pistol_rounds(range(1, 32)) == {1, 13, 25, 28, 31}


def test_report_reads_sides_from_round_teams(db, league):
    a, b = league["a"], league["b"]
    with dbctx.using(db):
        report = gameplan.build(a, b)
        assert report["lede"] == {"my_maps": 1, "opponent_maps": 1, "h2h_maps": 1}
        h2h = report["head_to_head"]["totals"]
        assert (h2h["maps_played"], h2h["maps_won"], h2h["maps_lost"]) == (1, 1, 0)
        # Side rates come from Round.ct_team, never winner_side: Alpha's CT half on
        # the Bravo map was rounds 1-6 (5 won), its T half rounds 7-12.
        metrics = gameplan.team_metrics(a, mapstrategy.maps_in_window(a, opponent=b))
        assert metrics["ct_rounds"] == 6 and metrics["t_rounds"] == 6
        assert metrics["ct_win_pct"] == round(5 / 6 * 100, 1)
        duels = report["duels"]
        assert duels["rows"] and duels["cols"]
        assert all(cell["thin"] for cell in duels["cells"].values())


def test_pick_lists_teams_with_parsed_maps(client, auth, league):
    body = client.get("/gameplan/teams", headers=auth).json()
    assert [t["name"] for t in body["teams"]] == ["Alpha", "Bravo", "Charlie"]
    assert all(t["maps"] == 2 for t in body["teams"]) and body["parsed_maps"] == 3


def test_header_and_every_panel(client, auth, league):
    a, b = league["a"].id, league["b"].id
    header = client.get(f"/gameplan/{a}/vs/{b}", headers=auth).json()
    assert header["my_team"]["name"] == "Alpha" and header["opponent"]["name"] == "Bravo"
    assert [t["key"] for t in header["tabs"]] == TABS
    assert header["default_tab"] == "decision"
    heat = next(t for t in header["tabs"] if t["key"] == "heatmaps")
    assert heat["n"] > 0
    for tab in TABS:
        res = client.get(f"/gameplan/{a}/vs/{b}/s/{tab}", headers=auth)
        assert res.status_code == 200, (tab, res.text)
        body = res.json()
        assert body["tab"] == tab and body["cached"] is False and body["data"]
    decision = client.get(f"/gameplan/{a}/vs/{b}/s/decision", headers=auth).json()
    assert decision["cached"] is True
    assert decision["data"]["decision"]["label"]
    maps = client.get(f"/gameplan/{a}/vs/{b}/s/maps", headers=auth).json()["data"]
    assert maps["board"][0]["call_label"] and "<svg" in maps["chart"]


def test_fixture_guards(client, auth, league):
    a, b, c = league["a"].id, league["b"].id, league["c"].id
    assert client.get(f"/gameplan/{a}/vs/{a}", headers=auth).status_code == 400
    assert client.get(f"/gameplan/{a}/vs/9999", headers=auth).status_code == 404
    assert client.get(f"/gameplan/{a}/vs/{b}/s/nope", headers=auth).status_code == 404
    # A team from another fixture is not drawn on this one.
    url = f"/gameplan/{a}/vs/{b}/heatmap?team={c}&map=de_mirage"
    assert client.get(url, headers=auth).status_code == 404
    url = f"/gameplan/{a}/vs/{b}/heatmap?team={a}&map=de_mirage&side=mid"
    assert client.get(url, headers=auth).status_code == 400
    assert client.get(f"/gameplan/{a}/vs/{b}").status_code == 401


def test_heatmap_points_for_the_browser(client, auth, league, tmp_path):
    a, b = league["a"].id, league["b"].id
    url = f"/gameplan/{a}/vs/{b}/heatmap?team={a}&map=de_mirage&player=all&side=all&kind=kills"
    body = client.get(url, headers=auth).json()
    assert body["kind"] == "kills" and body["cmap"] == "inferno"
    assert len(body["points"]) >= 5 and all(len(p) == 2 for p in body["points"])
    assert body["subtitle"].endswith(f"{len(body['points'])} positions") and body["heat"] is True
    assert body["plate"]["url"] == "/radars/de_mirage.png" and len(body["plate"]["extent"]) == 4
    # Drawn by the page: nothing is rendered or written on the server.
    assert not any(tmp_path.rglob("*"))
    deaths = client.get(url.replace("kind=kills", "kind=deaths"), headers=auth).json()
    assert deaths["cmap"] == "viridis"
    # Nothing on that selection: an honest empty, not an error.
    none = client.get(url.replace("de_mirage", "de_nuke"), headers=auth).json()
    assert none == {"empty": True}


def test_heatmap_with_few_points_draws_only_the_dots(client, auth, league, db):
    a, b = league["a"], league["b"]
    p = league["players"][a.id][0]
    # Two deaths left: too few for a density, still where this player died.
    deaths = db.scalars(
        select(KillEvent.id).where(KillEvent.victim_id == p.id).order_by(KillEvent.id)
    ).all()
    db.execute(delete(KillEvent).where(KillEvent.id.in_(deaths[2:])))
    db.commit()
    with dbctx.using(db):
        index = heatmap_groups.build_index(a, b)
    assert index["available"][heatmap_groups.key("de_mirage", a.id, p.id, "all", "deaths")] == 2
    url = (
        f"/gameplan/{a.id}/vs/{b.id}/heatmap?team={a.id}&map=de_mirage"
        f"&player={p.id}&side=all&kind=deaths"
    )
    body = client.get(url, headers=auth).json()
    assert len(body["points"]) == 2 and body["heat"] is False
    assert body["subtitle"].endswith("2 positions · too few for a heat layer")


def test_movement_for_one_player(client, auth, league, tmp_path):
    a, b = league["a"].id, league["b"].id
    p = league["players"][a][0].id
    url = f"/gameplan/{a}/vs/{b}/movement?team={a}&map=de_mirage&player={p}&side=all"
    body = client.get(url, headers=auth).json()
    assert "url" not in body and body["routes"] == 1
    assert [t["title"] for t in body["tables"]]
    scene = body["scene"]
    assert scene["plate"]["url"] == "/radars/de_mirage.png"
    assert scene["routes"][0]["steps"][0]["place"] == "Spawn"
    assert not any(tmp_path.rglob("*"))
    # No Tick Data in this fixture, so no walked tracks: an empty list.
    tracks = client.get(url.replace("/movement?", "/tracks?"), headers=auth).json()
    assert tracks == {"tracks": []}
