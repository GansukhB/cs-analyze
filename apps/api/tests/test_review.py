"""The Review on one hand-built Round, and the Win probability it rests on.

Round 1 on Inferno, 2v2, CT Alpha (a1, a2) against T Bravo (b1, b2):

* 10 s in, b1's flash pops: a1 (CT) goes blind for 2.5 s, b2 (b1's own
  teammate) for 2 s. b1 has already put 40 into a1.
* b2 kills a1 while a1 is blind: a flash assist and a damage assist for b1.
  a2 is 2000 units away, so a1 died alone and nobody traded him.
* a2 kills b2 (no Trade: 7.8 s later), then b1, and wins a 1v2.

With Sightings, b1 has a2 in view for 1.5 s just before dying to him and never
fires.
"""

import io
import json
import zipfile

import polars as pl
import pytest
from sqlalchemy import select

from app.models import (
    GameMap,
    MapRoster,
    Match,
    MatchMap,
    MatchMapReview,
    Player,
    PlayerRound,
    Round,
    Team,
)
from app.models.base import utcnow
from app.services import mn, review, tickdata, winprob

START, END, OFFICIAL = 1000, 3560, 3700
FLASH, A1_DIES, B2_DIES, B1_DIES = 1640, 1700, 2200, 2500
PLAYERS = [(11, "a1", "Alpha", "ct"), (12, "a2", "Alpha", "ct"),
           (21, "b1", "Bravo", "t"), (22, "b2", "Bravo", "t")]  # fmt: skip
SPOT = {11: (0.0, 0.0), 12: (2000.0, 0.0), 21: (300.0, 0.0), 22: (350.0, 50.0)}
DIES = {11: A1_DIES, 21: B1_DIES, 22: B2_DIES}
BLIND = {11: 2.5, 22: 2.0}


def _ticks() -> pl.DataFrame:
    rows = []
    for steamid, name, clan, side in PLAYERS:
        x, y = SPOT[steamid]
        for tick in range(START, OFFICIAL, 2):
            blind = BLIND.get(steamid, 0.0)
            flash = blind if FLASH <= tick < FLASH + int(blind * 64) else 0.0
            rows.append({
                "health": 0 if tick >= DIES.get(steamid, 10**9) else 100,
                "flash_duration": flash, "place": "BombsiteA", "side": side,
                "team_clan_name": clan, "X": x, "Y": y, "Z": 0.0, "yaw": 180.0,
                "tick": tick, "steamid": steamid, "name": name, "round_num": 1,
            })  # fmt: skip
    return pl.DataFrame(rows, schema_overrides={"steamid": pl.UInt64})


def _kill(tick, attacker, victim, a_side, v_side, weapon="ak47") -> dict:
    ax, ay = SPOT[attacker]
    vx, vy = SPOT[victim]
    return {"tick": tick, "attacker_steamid": attacker, "victim_steamid": victim,
            "assister_steamid": None, "attacker_side": a_side, "victim_side": v_side,
            "weapon": weapon, "headshot": True, "thrusmoke": False, "penetrated": 0,
            "noscope": False, "attackerblind": False, "attacker_X": ax, "attacker_Y": ay,
            "attacker_Z": 0.0, "victim_X": vx, "victim_Y": vy, "victim_Z": 0.0,
            "attacker_place": "BombsiteA", "victim_place": "BombsiteA", "distance": 100.0,
            "round_num": 1}  # fmt: skip


def _held(steamid: int, tick: int, held: tuple[str, int] | None) -> str:
    """a1 holds ``held``'s item from its tick on (the AK-47 before); the rest the AK."""
    if held and steamid == 11 and tick >= held[1]:
        return held[0]
    return "AK-47"


def _bundle(sightings: bool, held: tuple[str, int] | None = None) -> bytes:
    kills = pl.DataFrame(
        [
            _kill(A1_DIES, 22, 11, "t", "ct"),
            _kill(B2_DIES, 12, 22, "ct", "t"),
            _kill(B1_DIES, 12, 21, "ct", "t"),
        ],  # fmt: skip
        schema_overrides={"attacker_steamid": pl.UInt64, "victim_steamid": pl.UInt64},
    )
    damages = pl.DataFrame(
        [
            {
                "tick": 1650,
                "attacker_steamid": 21,
                "victim_steamid": 11,
                "attacker_side": "t",
                "victim_side": "ct",
                "weapon": "glock",
                "dmg_health_real": 40,
                "health": 60,
                "round_num": 1,
            }
        ],  # fmt: skip
        schema_overrides={"attacker_steamid": pl.UInt64, "victim_steamid": pl.UInt64},
    )
    flashes = pl.DataFrame(
        [
            {
                "tick": FLASH,
                "thrower_steamid": 21,
                "thrower_side": "t",
                "X": 150.0,
                "Y": 0.0,
                "Z": 50.0,
                "thrower_X": 300.0,
                "thrower_Y": 0.0,
                "thrower_Z": 0.0,
                "round_num": 1,
            }
        ],  # fmt: skip
        schema_overrides={"thrower_steamid": pl.UInt64},
    )
    loadout = pl.DataFrame(
        [
            {
                "round_num": 1,
                "tick": t,
                "steamid": s,
                "held": _held(s, t, held),
                "inventory": ["knife", "AK-47", "Flashbang", "Smoke Grenade"],
                "armor": 100,
                "helmet": True,
                "defuser": False,
                "balance": 800,
            }
            for s in (11, 12, 21, 22)
            for t in range(START, OFFICIAL, 8)
        ],  # fmt: skip
        schema_overrides={"steamid": pl.UInt64},
    )
    frames = {
        "ticks": _ticks(),
        "rounds": pl.DataFrame(
            {
                "round_num": [1],
                "start": [800],
                "freeze_end": [START],
                "end": [END],
                "official_end": [OFFICIAL],
                "winner": ["ct"],
                "reason": ["t_killed"],
            }
        ),  # fmt: skip
        "kills": kills,
        "damages": damages,
        "flashes": flashes,
        "he_grenades": pl.DataFrame(),
        "economy": pl.DataFrame(),
        "loadout": loadout,
    }
    for empty in ("footsteps", "shots", "grenades", "infernos", "smokes", "bomb"):
        frames[empty] = pl.DataFrame()
    if sightings:
        seen = [{"round_num": 1, "tick": t, "steamid": 12, "spotter": 21}
                for t in range(2300, 2400, 2)]  # fmt: skip
        frames["sightings"] = pl.DataFrame(
            seen, schema_overrides={"steamid": pl.UInt64, "spotter": pl.UInt64}
        )
        frames["aim"] = pl.DataFrame(
            [
                {
                    "round_num": 1,
                    "tick": t,
                    "steamid": s,
                    "pitch": 0.0,
                    "scoped": False,
                    "ducking": False,
                    "walking": False,
                }
                for s in (11, 12, 21, 22)
                for t in range(START, OFFICIAL, 4)
            ],  # fmt: skip
            schema_overrides={"steamid": pl.UInt64},
        )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, frame in frames.items():
            buffer = io.BytesIO()
            frame.write_parquet(buffer)
            bundle.writestr(f"{name}.parquet", buffer.getvalue())
        bundle.writestr("header.json", json.dumps({"map_name": "de_inferno"}))
    return out.getvalue()


@pytest.fixture
def inferno(db):
    alpha, bravo = Team(name="Alpha"), Team(name="Bravo")
    match = Match(hltv_id=7, team1=alpha, team2=bravo, slug="alpha-vs-bravo")
    match_map = MatchMap(
        match=match, map_number=1, game_map=GameMap(name="de_inferno"), team1=alpha,
        team2=bravo, tickrate=64, n_rounds=1, parsed_at=utcnow(),
    )  # fmt: skip
    db.add(match_map)
    db.flush()
    rnd = Round(match_map=match_map, number=1, start_tick=800, freeze_end_tick=START,
                end_tick=END, official_end_tick=OFFICIAL, winner_side="ct", winner_team=alpha,
                ct_team=alpha, t_team=bravo, end_reason="t_killed")  # fmt: skip
    db.add(rnd)
    for steamid, name, clan, side in PLAYERS:
        team = alpha if clan == "Alpha" else bravo
        player = Player(steamid=steamid, name=name)
        db.add(MapRoster(match_map=match_map, player=player, team=team, display_name=name))
        db.add(PlayerRound(round=rnd, player=player, team=team, side=side, equip_value=4000))
    db.commit()
    return {"map": match_map, "match": match}


def _review(db, inferno, sightings=False, held=None) -> dict:
    tickdata.store(db, inferno["map"], _bundle(sightings, held))
    db.commit()
    return review.ensure(db, inferno["map"])


def _codes(payload) -> dict[str, list]:
    out: dict[str, list] = {}
    for f in payload["findings"]:
        out.setdefault(f["code"], []).append(f)
    return out


# ---------------------------------------------------------- Win probability ---
def _state(ct, t, planted=False, left=60.0, kits=0):
    return winprob.State(ct, t, ct * 4000.0, t * 4000.0, planted, left, kits, "de_inferno")


def test_the_game_decides_some_states_itself():
    assert winprob.ct_win(_state(0, 3)) == 0.0
    assert winprob.ct_win(_state(2, 0)) == 1.0
    assert winprob.ct_win(_state(3, 3, left=0)) == 1.0  # the clock ran out with no plant
    # Planted, and less time than a defuse takes: nothing a CT can do.
    assert winprob.ct_win(_state(3, 0, planted=True, left=8.0, kits=0)) == 0.0
    assert winprob.ct_win(_state(3, 0, planted=True, left=4.0, kits=1)) == 0.0
    assert winprob.ct_win(_state(3, 0, planted=True, left=8.0, kits=1)) > 0.5


def test_a_man_up_is_better_than_a_man_down():
    assert (
        winprob.ct_win(_state(5, 4)) > winprob.ct_win(_state(5, 5)) > winprob.ct_win(_state(4, 5))
    )
    assert winprob.win(_state(4, 5), "t") == pytest.approx(1 - winprob.ct_win(_state(4, 5)))


# ------------------------------------------------------------------ Swing ---
def test_a_kill_is_split_with_the_flash_and_the_damage_behind_it(db, inferno):
    payload = _review(db, inferno)
    rnd = payload["rounds"][0]
    first = rnd["events"][0]
    assert first["kind"] == "kill" and first["sid"] == "22" and first["victim"] == "11"
    gain = -first["d_ct"]  # Bravo's gain is the CT's loss
    assert gain > 0
    swing = rnd["swing"]
    # b1 flashed (20%) and damaged a1 for 40 (40%); b2 keeps the rest. Each of
    # them is then charged their own death: the CT's gain on that kill.
    died = {e["victim"]: e["d_ct"] for e in rnd["events"] if e["kind"] == "kill"}
    assert swing["22"] == pytest.approx(gain * 0.4 - died["22"], abs=1e-3)
    assert swing["21"] == pytest.approx(gain * 0.6 - died["21"], abs=1e-3)
    assert swing["11"] == pytest.approx(-gain, abs=1e-3)
    # The Round ends decided, and a2 won it.
    assert rnd["wp"][-1] == [round((END - START) / 64, 2), 1.0]
    assert rnd["decider"] == "12"


def test_findings_on_the_round(db, inferno):
    payload = _review(db, inferno)
    codes = _codes(payload)
    clutch = codes["clutch"][0]
    assert clutch["sids"] == ["12"] and clutch["facts"]["vs"] == 2 and clutch["facts"]["kills"] == 2
    assert codes["untraded"][0]["sids"][0] == "11"  # alone, a2 2000 units away
    flash = codes["flash_kill"][0]
    assert flash["sids"][:3] == ["21", "22", "11"] and not flash["facts"]["own"]
    assert payload["sightings"] is False
    assert set(payload["needs_sightings"]) == set(review.SIGHT_CODES)
    assert not any(f["sight"] for f in payload["findings"])
    b1 = next(p for p in payload["players"] if p["sid"] == "21")
    assert b1["utility"]["flashes"] == 1 and b1["utility"]["team_flashes"] == 1


@pytest.mark.parametrize(
    ("held", "caught"),
    [
        (("Butterfly Knife", A1_DIES - 96), True),  # 1.4 s: the knife was out before the duel
        (("Butterfly Knife", A1_DIES - 48), False),  # 0.6 s: a switch made in the fight
        (("Smoke Grenade", A1_DIES - 64), False),  # 0.9 s: a grenade gets 1.5 s for the throw
        (("Smoke Grenade", A1_DIES - 128), True),
    ],
)
def test_caught_without_a_gun_in_hand(db, inferno, held, caught):
    codes = _codes(_review(db, inferno, held=held))
    if not caught:
        assert "no_gun_in_hand" not in codes and codes["untraded"][0]["sids"][0] == "11"
        return
    # It names the cause, so a1's death is no longer "untraded".
    assert "untraded" not in codes
    finding = codes["no_gun_in_hand"][0]
    assert finding["sids"] == ["11", "22"]
    facts = finding["facts"]
    assert facts["held"] == held[0] and facts["gun"] == "AK-47"
    assert facts["seconds"] >= review.NO_GUN_SECONDS[facts["held_kind"]]
    assert finding["tick"] > held[1]  # the first Loadout sample without the gun


def test_a_knife_out_since_the_freeze_end_starts_three_seconds_before(db, inferno):
    finding = _codes(_review(db, inferno, held=("Karambit", START)))["no_gun_in_hand"][0]
    assert finding["facts"]["gun"] == "" and finding["facts"]["held_kind"] == "knife"
    assert finding["tick"] == A1_DIES - 3 * 64
    worded = mn.review_finding(finding, lambda sid: {"11": "a1", "22": "b2"}.get(sid, sid))
    assert worded["title"] == "a1 — буугаа бариагүй баригдав"
    assert "раунд эхэлснээс хойш буугаа гаргалгүй гартаа хутга" in worded["text"]


def test_sightings_add_what_the_eyes_saw(db, inferno):
    payload = _review(db, inferno, sightings=True)
    assert payload["sightings"] is True and payload["needs_sightings"] == []
    saw = _codes(payload)["saw_no_shot"][0]
    assert saw["sids"][:2] == ["21", "12"] and saw["sight"] is True
    assert saw["facts"]["self_killed"] is True


def test_a_stale_review_is_rebuilt_and_a_new_one_stored(db, inferno):
    _review(db, inferno)
    row = db.scalar(select(MatchMapReview))
    assert row.version == review.version()
    row.version = "old"
    db.commit()
    assert review.ensure(db, inferno["map"])["version"] == review.version()
    assert db.scalar(select(MatchMapReview)).version == review.version()


def test_the_page_gets_it_worded(client, auth, db, inferno):
    _review(db, inferno)
    res = client.get(f"/matches/{inferno['match'].id}/maps/1/review", headers=auth)
    assert res.status_code == 200
    body = res.json()
    assert "Sighting" in body["missing"]
    clutch = next(f for f in body["findings"] if f["code"] == "clutch")
    assert clutch["title"] == "a2 — 1v2 clutch" and clutch["kind_label"] == "Шийдвэрлэсэн үйлдэл"
    assert body["rounds"][0]["findings"]  # the Round lists its Findings by id
    assert body["rounds"][0]["summary"].startswith("Alpha (CT) хожив")


def test_a_map_without_tick_data_has_no_review(client, auth, db, inferno):
    res = client.get(f"/matches/{inferno['match'].id}/maps/1/review", headers=auth)
    assert res.status_code == 404


def test_the_assistant_reads_it(db, inferno):
    from app.services import assistant, dbctx

    _review(db, inferno)
    with dbctx.using(db):
        out = assistant._tool_match_review(inferno["match"].id, player="a2")
        missing = assistant._tool_match_review(inferno["match"].id, map_number=3)
    assert out["map"] == "Inferno" and out["parsed_maps"] == [1]
    assert [f["what"] for f in out["findings"]] == ["Clutch"]
    assert "error" in missing and missing["parsed_maps"] == [1]


# ----------------------------------------------------------------- a defuse ---
PLANT, DEFUSED = 1500, 3500  # 8.75 s left on the bomb when a2 finishes, with no kit


@pytest.fixture
def defused(db, inferno):
    """The same Round, but b1 plants first and a2 defuses after clearing the site."""
    from app.models import BombEvent

    rnd = db.scalar(select(Round))
    rnd.bomb_plant_tick = PLANT
    rnd.end_reason = "bomb_defused"
    players = {p.steamid: p for p in db.scalars(select(Player))}
    for tick, event, sid in ((PLANT, "plant", 21), (DEFUSED, "defuse", 12)):
        db.add(BombEvent(round=rnd, tick=tick, event=event, player=players[sid], x=0, y=0, z=0))
    db.commit()
    return inferno


def test_a_defuse_under_way_is_not_a_lost_round(db, defused):
    rnd = _review(db, defused)["rounds"][0]
    # Before: the clock read under 10 s while a2 was defusing, the CT's chance fell
    # to 0, and the defuse was worth the whole Round (+1.0) to a2.
    began = (DEFUSED - 10 * 64 - START) / 64
    during = [p for t, p in rnd["wp"] if began <= t < (DEFUSED - START) / 64]
    assert during and min(during) > 0.5
    defuse = next(e for e in rnd["events"] if e["kind"] == "defuse")
    assert 0 < defuse["d_ct"] < 0.5


def test_a_defuse_with_no_time_to_finish_is_still_a_ct_loss():
    planted = winprob.State(1, 0, 4000.0, 0.0, True, 8.0, 0, "de_inferno")
    assert winprob.ct_win(planted) == 0.0
    assert winprob.ct_win(winprob.State(**{**planted.__dict__, "defusing": True})) > 0.5


def test_kills_move_swing_between_players_and_create_none(db, inferno):
    # Every kill hands the killer's side what it takes from the victim's (RV-3):
    # in a Round with no plant or defuse, the Players' Swing adds up to zero.
    rnd = _review(db, inferno)["rounds"][0]
    assert sum(rnd["swing"].values()) == pytest.approx(0.0, abs=1e-6)
    kills = [e for e in rnd["events"] if e["kind"] == "kill"]
    assert len(kills) == 3


def test_every_finding_code_has_its_kind(db, inferno):
    for f in _review(db, inferno, sightings=True)["findings"]:
        assert review.CODE_KIND[f["code"]] == f["kind"], f["code"]
    assert set(review.CODE_KIND) == set(mn.REVIEW_CODE)
