"""Тоглогч тус бүрээр: юу хийдэг, хаанаас хийдэг, эсрэг нь юу хийх вэ.

:mod:`app.services.gameplan` баг хоёрын түвшинг харьцуулдаг бол энэ модуль
нэг шат доош ордог: **тоглогч x газрын зураг x тал** түвшинд зэвсэг, гранат,
байршил, зам, дуэль, хохирлыг цуглуулж, тэднээс заавар гаргана.

Гурван түүврийг тусад нь барина:

* **own**  -- манай/тэдний өөрсдийн тоглолт (энэ фикстурыг хассан). Түвшин.
* **vs**   -- зөвхөн энэ өрсөлдөгчийн эсрэг.
* **delta** -- хоёрын зөрүү. "Тэр сайн" гэдгээс "тэр биднийг барьдаг" гэдгийг
  салгадаг цорын ганц зүйл.

Заавар бүр **бүтэцтэй** (``kind`` + параметрүүд) буцна: монгол өгүүлбэрийг
:mod:`app.services.mn` угсарна. Байршил, зам хоёр **зөвхөн нэг газрын зургийн
дотор** утгатай тул газрын зураг хооронд хэзээ ч нэгтгэхгүй.

cstat-ийн ``hltv/services/playerplan.py``-аас шилжүүлсэн.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased, joinedload

from app.models import (
    MatchMap,
    Player,
    PlayerMap,
    PlayerMapDuel,
    PlayerMapPosition,
    PlayerMapRoute,
    PlayerMapUtility,
    PlayerMapWeapon,
    PlayerRound,
    PositionKind,
    Round,
    Team,
)
from app.services import lineup as lineups
from app.services import mapstrategy
from app.services import roles as role_service
from app.services.dbctx import count_if, db, total

logger = logging.getLogger(__name__)

# Эдгээрээс доош бол тохиолдол, хандлага биш.
MIN_PLACE = 4
MIN_WEAPON_KILLS = 5
MIN_DUELS = 4
MIN_ROUTE_ROUNDS = 3
# Зэвсгийн эзлэх хувь -- үүнээс дээш бол "түүний зэвсэг".
SIGNATURE_SHARE = 0.30


def _pct(n, d, nd=1):
    return round(n / d * 100, nd) if d else 0.0


def _ratio(n, d, nd=2):
    return round(n / d, nd) if d else 0.0


def _parsed_pool() -> list[MatchMap]:
    return list(
        db().scalars(
            select(MatchMap)
            .options(joinedload(MatchMap.match), joinedload(MatchMap.game_map))
            .where(MatchMap.parsed_at.is_not(None))
        )
    )


# ------------------------------------------------------------------ түүвэр ---
def split_maps(team: Team, opponent: Team) -> dict:
    """Багийн газрын зургуудыг өөрийн ба эсрэг талын эсрэг гэж хуваана."""
    all_maps = mapstrategy.maps_in_window(team)
    vs_ids = {m.id for m in mapstrategy.maps_in_window(team, opponent=opponent)}
    return {
        "own": [m for m in all_maps if m.id not in vs_ids],
        "vs": [m for m in all_maps if m.id in vs_ids],
        "all": all_maps,
    }


def current_lineup(team: Team) -> set:
    """Багийн Lineup-ийн нэрс: сонгосон бол тэд, үгүй бол сүүлийн тоглолтын тав."""
    return lineups.names(team, lambda: {p.name for p in lineups.latest_five(team)})


# ------------------------------------------------------------------- хэсэг ---
def _form(team: Team, match_maps: Iterable[MatchMap]) -> dict[int, dict]:
    """Тоглогч тус бүрийн үндсэн үзүүлэлт, талаар нь задалсан."""
    map_ids = [m.id for m in match_maps]
    if not map_ids:
        return {}
    session = db()
    out: dict[int, dict] = {}
    for row in session.execute(
        select(
            PlayerMap.player_id,
            Player.name,
            func.count(PlayerMap.id),
            total(PlayerMap.rounds_played),
            total(PlayerMap.kills),
            total(PlayerMap.deaths),
            total(PlayerMap.assists),
            total(PlayerMap.headshots),
            total(PlayerMap.damage),
            total(PlayerMap.opening_kills),
            total(PlayerMap.opening_deaths),
        )
        .join(Player, Player.id == PlayerMap.player_id)
        .where(PlayerMap.match_map_id.in_(map_ids), PlayerMap.team_id == team.id)
        .group_by(PlayerMap.player_id, Player.name)
    ):
        pid, name, maps = row[0], row[1], row[2]
        rounds, kills, deaths, assists, headshots, damage, ok, od = (int(v or 0) for v in row[3:])
        attempts = ok + od
        out[pid] = {
            "player_id": pid,
            "name": name,
            "maps": maps,
            "rounds": rounds,
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "damage": damage,
            "adr": _ratio(damage, rounds, 1),
            "kd": _ratio(kills, deaths, 2) if deaths else float(kills),
            "hs_pct": _pct(headshots, kills),
            "opening_kills": ok,
            "opening_deaths": od,
            "opening_win_pct": _pct(ok, attempts),
            "opening_rate": _ratio(attempts, rounds, 3),
            "sides": {},
        }

    where = (
        PlayerRound.round_id.in_(select(Round.id).where(Round.match_map_id.in_(map_ids))),
        PlayerRound.team_id == team.id,
    )
    for pid, n, kast, traded, deaths, multi in session.execute(
        select(
            PlayerRound.player_id,
            func.count(PlayerRound.id),
            count_if(PlayerRound.kast),
            count_if(PlayerRound.traded),
            total(PlayerRound.deaths),
            count_if(PlayerRound.kills >= 3),
        )
        .where(*where)
        .group_by(PlayerRound.player_id)
    ):
        entry = out.get(pid)
        if entry:
            entry["kast_pct"] = _pct(int(kast), n)
            entry["traded_death_pct"] = _pct(int(traded), int(deaths))
            entry["multi_kill_rounds"] = int(multi)
    for pid, side, n, kills, deaths, damage, ok, od in session.execute(
        select(
            PlayerRound.player_id,
            PlayerRound.side,
            func.count(PlayerRound.id),
            total(PlayerRound.kills),
            total(PlayerRound.deaths),
            total(PlayerRound.damage),
            count_if(PlayerRound.opening_kill),
            count_if(PlayerRound.opening_death),
        )
        .where(*where, PlayerRound.side != "")
        .group_by(PlayerRound.player_id, PlayerRound.side)
    ):
        entry = out.get(pid)
        if not entry:
            continue
        ok, od = int(ok), int(od)
        entry["sides"][side] = {
            "rounds": n,
            "kills": int(kills),
            "deaths": int(deaths),
            "adr": _ratio(int(damage), n, 1),
            "opening_kills": ok,
            "opening_deaths": od,
            "opening_win_pct": _pct(ok, ok + od),
        }
    return out


def _weapons(team: Team, match_maps: Iterable[MatchMap]) -> dict[int, dict]:
    """Тоглогч x тал x зэвсэг. 'Түүний зэвсэг' гэж юуг хэлэхийг тодорхойлно."""
    map_ids = [m.id for m in match_maps]
    if not map_ids:
        return {}
    raw: dict = defaultdict(lambda: defaultdict(dict))
    for pid, side, weapon, kills, hs, damage, hits in db().execute(
        select(
            PlayerMapWeapon.player_id,
            PlayerMapWeapon.side,
            PlayerMapWeapon.weapon,
            total(PlayerMapWeapon.kills),
            total(PlayerMapWeapon.headshots),
            total(PlayerMapWeapon.damage),
            total(PlayerMapWeapon.hits),
        )
        .where(
            PlayerMapWeapon.match_map_id.in_(map_ids),
            PlayerMapWeapon.team_id == team.id,
            PlayerMapWeapon.side != "",
        )
        .group_by(PlayerMapWeapon.player_id, PlayerMapWeapon.side, PlayerMapWeapon.weapon)
    ):
        raw[pid][side][weapon] = {
            "weapon": weapon,
            "kills": int(kills),
            "headshots": int(hs),
            "damage": int(damage),
            "hits": int(hits),
        }
    out: dict[int, dict] = {}
    for pid, by_side in raw.items():
        entry = {}
        for side, guns in by_side.items():
            rows = sorted(guns.values(), key=lambda g: -g["kills"])
            whole = sum(g["kills"] for g in rows) or 1
            for g in rows:
                g["share"] = round(g["kills"] / whole, 3)
                g["hs_pct"] = _pct(g["headshots"], g["kills"])
                g["dmg_per_kill"] = _ratio(g["damage"], g["kills"], 0) or None
            signature = next(
                (
                    g
                    for g in rows
                    if g["share"] >= SIGNATURE_SHARE and g["kills"] >= MIN_WEAPON_KILLS
                ),
                None,
            )
            entry[side] = {"rows": rows[:5], "total_kills": whole, "signature": signature}
        out[pid] = entry
    return out


def _utility(team: Team, match_maps: Iterable[MatchMap]) -> dict[int, dict]:
    map_ids = [m.id for m in match_maps]
    if not map_ids:
        return {}
    session = db()
    rounds_by_side: dict[str, int] = defaultdict(int)
    for ct_id, t_id in session.execute(
        select(Round.ct_team_id, Round.t_team_id).where(Round.match_map_id.in_(map_ids))
    ):
        if ct_id == team.id:
            rounds_by_side["ct"] += 1
        if t_id == team.id:
            rounds_by_side["t"] += 1
    out: dict[int, dict] = defaultdict(dict)
    for pid, side, smokes, infernos, fire, he, flashes, smoke_rounds, smoke_won in session.execute(
        select(
            PlayerMapUtility.player_id,
            PlayerMapUtility.side,
            total(PlayerMapUtility.smokes),
            total(PlayerMapUtility.infernos),
            total(PlayerMapUtility.fire_damage),
            total(PlayerMapUtility.he_damage),
            total(PlayerMapUtility.flash_assists),
            total(PlayerMapUtility.smoke_rounds),
            total(PlayerMapUtility.smoke_rounds_won),
        )
        .where(
            PlayerMapUtility.match_map_id.in_(map_ids),
            PlayerMapUtility.team_id == team.id,
            PlayerMapUtility.side != "",
        )
        .group_by(PlayerMapUtility.player_id, PlayerMapUtility.side)
    ):
        n = rounds_by_side.get(side, 0)
        smokes, infernos, flashes = int(smokes), int(infernos), int(flashes)
        out[pid][side] = {
            "smokes": smokes,
            "infernos": infernos,
            "per_round": _ratio(smokes + infernos, n, 2),
            "fire_damage": int(fire),
            "he_damage": int(he),
            "flash_assists": flashes,
            "flash_per_round": _ratio(flashes, n, 3),
            "smoke_rounds": int(smoke_rounds),
            "smoke_win_pct": _pct(int(smoke_won), int(smoke_rounds)),
            "rounds": n,
        }
    return dict(out)


def _positions(team: Team, match_maps: Iterable[MatchMap]) -> dict[int, dict]:
    """{player: {map: {side: {kills_from, deaths_at}}}} -- газрын зургаар."""
    maps_by_id = {m.id: m for m in match_maps}
    if not maps_by_id:
        return {}
    out: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
    for pid, map_id, side, place, kind, n in db().execute(
        select(
            PlayerMapPosition.player_id,
            PlayerMapPosition.match_map_id,
            PlayerMapPosition.side,
            PlayerMapPosition.place,
            PlayerMapPosition.kind,
            total(PlayerMapPosition.count),
        )
        .where(
            PlayerMapPosition.match_map_id.in_(list(maps_by_id)),
            PlayerMapPosition.team_id == team.id,
            PlayerMapPosition.side != "",
            PlayerMapPosition.place != "",
        )
        .group_by(
            PlayerMapPosition.player_id,
            PlayerMapPosition.match_map_id,
            PlayerMapPosition.side,
            PlayerMapPosition.place,
            PlayerMapPosition.kind,
        )
    ):
        m = maps_by_id[map_id]
        name = m.game_map.name if m.game_map else "?"
        if kind == PositionKind.KILL_FROM:
            key = "kills_from"
        elif kind == PositionKind.DEATH_AT:
            key = "deaths_at"
        else:
            continue
        out[pid][name][side][key].append({"place": place, "count": int(n or 0)})
    # Нэг газрын зураг олон удаа тоглосон бол нэгтгээд эрэмбэлнэ.
    tidy: dict[int, dict] = {}
    for pid, by_map in out.items():
        tidy[pid] = {}
        for map_name, by_side in by_map.items():
            tidy[pid][map_name] = {}
            for side, kinds in by_side.items():
                merged = {}
                for key, rows in kinds.items():
                    acc: dict[str, int] = defaultdict(int)
                    for r in rows:
                        acc[r["place"]] += r["count"]
                    merged[key] = sorted(
                        ({"place": p, "count": c} for p, c in acc.items()),
                        key=lambda r: -r["count"],
                    )[:5]
                    # Before the cut to five: a share must be of every kill, not the top five's.
                    merged[f"{key}_total"] = sum(acc.values())
                tidy[pid][map_name][side] = merged
    return tidy


def _routes(team: Team, match_maps: Iterable[MatchMap]) -> dict[int, list]:
    maps_by_id = {m.id: m for m in match_maps}
    if not maps_by_id:
        return {}
    out: dict[int, list] = defaultdict(list)
    for r in db().scalars(
        select(PlayerMapRoute).where(
            PlayerMapRoute.match_map_id.in_(list(maps_by_id)),
            PlayerMapRoute.team_id == team.id,
            PlayerMapRoute.rounds >= MIN_ROUTE_ROUNDS,
            PlayerMapRoute.side != "",
        )
    ):
        m = maps_by_id[r.match_map_id]
        out[r.player_id].append(
            {
                "map": m.game_map.name if m.game_map else "?",
                "side": r.side,
                "route": r.label,
                "rounds": r.rounds,
                "kills": r.kills,
                "deaths": r.deaths,
                "net_per_round": r.net_per_round,
                "win_pct": r.win_pct,
                "adjusted": round((r.kills - r.deaths) / (r.rounds + 3), 2),
            }
        )
    for pid in out:
        out[pid].sort(key=lambda x: x["adjusted"])
    return dict(out)


def _duels(team: Team, opponent: Team, match_maps: Iterable[MatchMap]) -> dict[int, list]:
    """Тоглогч тус бүрийн эсрэг талын тоглогч бүртэй харьцсан данс."""
    map_ids = [m.id for m in match_maps]
    if not map_ids:
        return {}
    killer, victim = aliased(Player), aliased(Player)
    pairs: dict[tuple, dict] = defaultdict(
        lambda: {
            "for": 0,
            "against": 0,
            "opening_for": 0,
            "opening_against": 0,
            "from": defaultdict(int),
            "died_at": defaultdict(int),
        }
    )
    D = PlayerMapDuel
    for (
        k_id,
        k_name,
        v_id,
        v_name,
        k_team,
        _side,
        k_place,
        v_place,
        kills,
        openings,
    ) in db().execute(
        select(
            D.killer_id,
            killer.name,
            D.victim_id,
            victim.name,
            D.killer_team_id,
            D.side,
            D.killer_place,
            D.victim_place,
            total(D.kills),
            total(D.opening_kills),
        )
        .join(killer, killer.id == D.killer_id)
        .join(victim, victim.id == D.victim_id)
        .where(
            D.match_map_id.in_(map_ids),
            or_(
                and_(D.killer_team_id == team.id, D.victim_team_id == opponent.id),
                and_(D.killer_team_id == opponent.id, D.victim_team_id == team.id),
            ),
        )
        .group_by(
            D.killer_id,
            killer.name,
            D.victim_id,
            victim.name,
            D.killer_team_id,
            D.side,
            D.killer_place,
            D.victim_place,
        )
    ):
        kills, openings = int(kills or 0), int(openings or 0)
        if k_team == team.id:
            key = (k_id, v_id, v_name)
            pairs[key]["for"] += kills
            pairs[key]["opening_for"] += openings
            if k_place:
                pairs[key]["from"][k_place] += kills
        else:
            key = (v_id, k_id, k_name)
            pairs[key]["against"] += kills
            pairs[key]["opening_against"] += openings
            if v_place:
                pairs[key]["died_at"][v_place] += kills

    out: dict[int, list] = defaultdict(list)
    for (pid, opp_id, opp_name), d in pairs.items():
        duels = d["for"] + d["against"]
        out[pid].append(
            {
                "opponent_id": opp_id,
                "opponent": opp_name,
                "for": d["for"],
                "against": d["against"],
                "net": d["for"] - d["against"],
                "duels": duels,
                "thin": duels < MIN_DUELS,
                "opening_for": d["opening_for"],
                "opening_against": d["opening_against"],
                "kills_from": sorted(
                    ({"place": p, "count": c} for p, c in d["from"].items()),
                    key=lambda r: -r["count"],
                )[:3],
                "died_at": sorted(
                    ({"place": p, "count": c} for p, c in d["died_at"].items()),
                    key=lambda r: -r["count"],
                )[:3],
            }
        )
    for pid in out:
        out[pid].sort(key=lambda x: x["net"])
    return dict(out)


# ------------------------------------------------------------- нэгтгэл ------
def team_players(team: Team, opponent: Team, *, baseline=None, cohorts=None) -> list[dict]:
    """Багийн тоглогч бүрийн бүрэн зураглал, түүврээр нь тусгаарлан."""
    split = split_maps(team, opponent)
    own, vs = split["own"], split["vs"]

    form_own, form_vs = _form(team, own), _form(team, vs)
    weapons_own, weapons_vs = _weapons(team, own), _weapons(team, vs)
    util_own, util_vs = _utility(team, own), _utility(team, vs)
    pos_own, pos_vs = _positions(team, own), _positions(team, vs)
    routes_own = _routes(team, own)
    duels = _duels(team, opponent, vs)

    if baseline is None or cohorts is None:
        pool = _parsed_pool()
        baseline = baseline or role_service.league_baseline(pool)
        cohorts = cohorts or role_service.role_cohorts(pool, baseline)
    picture = role_service.rate_team(team, split["all"], baseline=baseline, cohorts=cohorts)
    roles_by_id = {p["player_id"]: p for p in picture["players"]}
    fielded = lineups.fielded(team)

    out = []
    for pid in set(form_own) | set(form_vs):
        base = form_own.get(pid) or form_vs.get(pid) or {}
        name = base.get("name") or str(pid)
        rp = roles_by_id.get(pid) or {}
        fits = rp.get("fit") or {}
        out.append(
            {
                "player_id": pid,
                "name": name,
                "in_lineup": (not fielded) or pid in fielded,
                "role": {
                    s: {
                        "role": v["role"],
                        "label": v["label"],
                        "confidence": v["confidence"],
                        "fit": (fits.get(s) or {}).get("score"),
                        "fit_verdict": (fits.get(s) or {}).get("verdict"),
                    }
                    for s, v in (rp.get("roles") or {}).items()
                    if v.get("role")
                },
                "rating": rp.get("rating"),
                "form": {"own": form_own.get(pid), "vs": form_vs.get(pid)},
                "delta": _form_delta(form_own.get(pid), form_vs.get(pid)),
                "weapons": {"own": weapons_own.get(pid, {}), "vs": weapons_vs.get(pid, {})},
                "utility": {"own": util_own.get(pid, {}), "vs": util_vs.get(pid, {})},
                "positions": {"own": pos_own.get(pid, {}), "vs": pos_vs.get(pid, {})},
                "routes": routes_own.get(pid, []),
                "duels": duels.get(pid, []),
            }
        )
    out += [_newcomer(p, baseline, cohorts) for p in lineups.newcomers(team)]
    out.sort(key=lambda p: (not p["in_lineup"], -((p["form"]["own"] or {}).get("adr") or 0)))
    return out


def _newcomer(player: Player, baseline, cohorts) -> dict:
    """Энэ багт тоглоогүй ч Lineup-д сонгогдсон тоглогч: тоо нь сүүлд тоглосон багаас."""
    found = lineups.elsewhere(player)
    card = {
        "player_id": player.id,
        "name": player.name,
        "in_lineup": True,
        "elsewhere": found[0].name if found else "",
        "role": {},
        "rating": None,
        "form": {"own": None, "vs": None},
        "delta": {},
        "weapons": {"own": {}, "vs": {}},
        "utility": {"own": {}, "vs": {}},
        "positions": {"own": {}, "vs": {}},
        "routes": [],
        "duels": [],
    }
    if not found or not found[1]:
        return card
    team, maps = found
    rp = next(
        (
            p
            for p in role_service.rate_team(team, maps, baseline=baseline, cohorts=cohorts)[
                "players"
            ]
            if p["name"] == player.name
        ),
        {},
    )
    fits = rp.get("fit") or {}
    card.update(
        role={
            s: {
                "role": v["role"],
                "label": v["label"],
                "confidence": v["confidence"],
                "fit": (fits.get(s) or {}).get("score"),
                "fit_verdict": (fits.get(s) or {}).get("verdict"),
            }
            for s, v in (rp.get("roles") or {}).items()
            if v.get("role")
        },
        rating=rp.get("rating"),
        form={"own": _form(team, maps).get(player.id), "vs": None},
        weapons={"own": _weapons(team, maps).get(player.id, {}), "vs": {}},
        utility={"own": _utility(team, maps).get(player.id, {}), "vs": {}},
        positions={"own": _positions(team, maps).get(player.id, {}), "vs": {}},
        routes=_routes(team, maps).get(player.id, []),
    )
    return card


_DELTA_KEYS = ("adr", "kd", "kast_pct", "opening_win_pct", "hs_pct", "traded_death_pct")


def _form_delta(own: dict | None, vs: dict | None) -> dict:
    """Өөрийн түвшин ба энэ өрсөлдөгчийн эсрэг үзүүлэлтийн зөрүү."""
    if not own or not vs:
        return {}
    out = {}
    for key in _DELTA_KEYS:
        a, b = own.get(key), vs.get(key)
        if isinstance(a, int | float) and isinstance(b, int | float):
            out[key] = round(b - a, 2)
    return out


# --------------------------------------------------------- зөвлөмж үүсгэх ---
def scout_instructions(player: dict, my_side: bool) -> list[dict]:
    """Нэг тоглогчийн талаарх бүтэцтэй заавар.

    ``my_side=False`` бол "түүний эсрэг яаж тоглох вэ", ``True`` бол "тэр юу
    хийх ёстой вэ". Түүвэр хүрэлцээгүй бол мөр үүсэхгүй.
    """
    out = []
    form = player["form"]["own"] or {}
    rounds = form.get("rounds") or 0

    # 1. Гарын үсэг болсон зэвсэг.
    for side, data in (player["weapons"].get("own") or {}).items():
        sig = data.get("signature")
        if sig:
            out.append(
                {
                    "kind": "signature_weapon",
                    "side": side,
                    "weapon": sig["weapon"],
                    "kills": sig["kills"],
                    "share": sig["share"],
                    "hs_pct": sig["hs_pct"],
                    "mine": my_side,
                }
            )

    # 2. Нээлтийн тулаан -- нээдэг үү, эсвэл эхэлж үхдэг үү.
    if rounds >= 40 and form.get("opening_kills", 0) + form.get("opening_deaths", 0) >= 15:
        out.append(
            {
                "kind": "opening_profile",
                "mine": my_side,
                "kills": form["opening_kills"],
                "deaths": form["opening_deaths"],
                "win_pct": form["opening_win_pct"],
                "rate": form["opening_rate"],
            }
        )

    # 3. Гранатын машин.
    for side, u in (player["utility"].get("own") or {}).items():
        if u.get("rounds", 0) >= 30 and u.get("per_round", 0) >= 1.4:
            out.append(
                {
                    "kind": "utility_engine",
                    "side": side,
                    "mine": my_side,
                    "per_round": u["per_round"],
                    "smokes": u["smokes"],
                    "infernos": u["infernos"],
                    "flash_per_round": u["flash_per_round"],
                }
            )
        if u.get("rounds", 0) >= 30 and u.get("flash_per_round", 0) >= 0.08:
            out.append(
                {
                    "kind": "flash_engine",
                    "side": side,
                    "mine": my_side,
                    "flashes": u["flash_assists"],
                    "per_round": u["flash_per_round"],
                }
            )

    # 4. Байршил -- газрын зураг тус бүрийн дотор.
    for map_name, by_side in (player["positions"].get("own") or {}).items():
        for side, kinds in by_side.items():
            kf = [r for r in kinds.get("kills_from", []) if r["count"] >= MIN_PLACE]
            da = [r for r in kinds.get("deaths_at", []) if r["count"] >= MIN_PLACE]
            if kf:
                out.append(
                    {
                        "kind": "kills_from",
                        "map": map_name,
                        "side": side,
                        "places": kf[:3],
                        "mine": my_side,
                    }
                )
            if da:
                out.append(
                    {
                        "kind": "dies_at",
                        "map": map_name,
                        "side": side,
                        "places": da[:3],
                        "mine": my_side,
                    }
                )

    # 5. Дуэль -- зөвхөн энэ өрсөлдөгчийн эсрэг.
    for d in player["duels"]:
        if d["thin"]:
            continue
        if d["net"] <= -6:
            out.append({"kind": "duel_loses", "mine": my_side, **d})
        elif d["net"] >= 4:
            out.append({"kind": "duel_wins", "mine": my_side, **d})

    # 6. Энэ өрсөлдөгчийн эсрэг унасан үзүүлэлт.
    delta = player.get("delta") or {}
    vs_rounds = (player["form"].get("vs") or {}).get("rounds") or 0
    if vs_rounds >= 40:
        for key in ("adr", "opening_win_pct", "kast_pct"):
            value = delta.get(key)
            if value is None:
                continue
            if value <= -8 or value >= 8:
                out.append(
                    {
                        "kind": "drops_vs_them" if value <= -8 else "rises_vs_them",
                        "metric": key,
                        "delta": value,
                        "own": (player["form"]["own"] or {}).get(key),
                        "vs": (player["form"]["vs"] or {}).get(key),
                        "rounds": vs_rounds,
                        "mine": my_side,
                    }
                )

    # 7. Зам -- зөвхөн өөрийн багт, засах зүйл учраас.
    if my_side:
        for r in [r for r in player["routes"] if r["adjusted"] <= -0.34][:2]:
            out.append({"kind": "bad_route", "mine": True, **r})
    return out


def build(my_team: Team, opponent: Team, *, baseline=None, cohorts=None) -> dict:
    """Хоёр багийн тоглогч бүрийн зураглал ба заавар."""
    pool = _parsed_pool()
    baseline = baseline or role_service.league_baseline(pool)
    cohorts = cohorts or role_service.role_cohorts(pool, baseline)

    mine = team_players(my_team, opponent, baseline=baseline, cohorts=cohorts)
    theirs = team_players(opponent, my_team, baseline=baseline, cohorts=cohorts)
    for p in mine:
        p["instructions"] = scout_instructions(p, my_side=True)
    for p in theirs:
        p["instructions"] = scout_instructions(p, my_side=False)
    return {
        "mine": {"team": my_team.name, "players": mine},
        "opponent": {"team": opponent.name, "players": theirs},
    }


# ------------------------------------------------- газрын зураг x тал -------
def map_side_setup(
    team: Team, opponent: Team, map_name: str, side: str, *, players: list[dict] | None = None
) -> dict:
    """Тухайн газрын зураг, тал дээр хэн хаана байрладаг вэ.

    Хамгийн олон алалт авсан байршлыг "түүний байр" гэж үзэж, тархалтыг хамт
    буцаана: нэг газарт төвлөрсөн бол цэг баригч, тарсан бол эргэлдэгч.
    """
    if players is None:
        players = team_players(team, opponent)
    rows = []
    for p in players:
        if not p["in_lineup"]:
            continue
        by_map = (p["positions"].get("own") or {}).get(map_name) or {}
        cell = by_map.get(side) or {}
        kf = cell.get("kills_from") or []
        da = cell.get("deaths_at") or []
        if not kf and not da:
            continue
        kills = cell.get("kills_from_total") or sum(r["count"] for r in kf) or 0
        top = kf[0] if kf else None
        rows.append(
            {
                "name": p["name"],
                "role": (p["role"].get(side) or {}).get("label"),
                "role_key": (p["role"].get(side) or {}).get("role"),
                "post": top["place"] if top else None,
                "post_kills": top["count"] if top else 0,
                "kills_from": kf[:3],
                "deaths_at": da[:3],
                "total_kills": kills,
                "concentration": round(top["count"] / kills, 2) if top and kills else 0.0,
                "spread": len(kf),
            }
        )
    rows.sort(key=lambda r: -r["total_kills"])
    return {"map": map_name, "side": side, "team": team.name, "players": rows}


def map_matrix(
    my_team: Team,
    opponent: Team,
    *,
    players_mine: list[dict] | None = None,
    players_theirs: list[dict] | None = None,
) -> list[dict]:
    """Газрын зураг бүрээр хоёр талын байрлалын зураглал."""
    names = set()
    for team in (my_team, opponent):
        for m in mapstrategy.maps_in_window(team):
            if m.game_map:
                names.add(m.game_map.name)
    if players_mine is None:
        players_mine = team_players(my_team, opponent)
    if players_theirs is None:
        players_theirs = team_players(opponent, my_team)

    out = []
    for name in sorted(names):
        entry = {"map": name, "sides": {}}
        for side in ("ct", "t"):
            entry["sides"][side] = {
                "mine": map_side_setup(my_team, opponent, name, side, players=players_mine),
                # Бид CT байхад тэд T, эсрэгээрээ.
                "theirs": map_side_setup(
                    opponent, my_team, name, "t" if side == "ct" else "ct", players=players_theirs
                ),
            }
        if any(
            entry["sides"][s]["mine"]["players"] or entry["sides"][s]["theirs"]["players"]
            for s in ("ct", "t")
        ):
            out.append(entry)
    return out
