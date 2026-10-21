"""A Team's style on a Map, Side by Side, against every Team's (docs/plans/05 TM-5).

Each number is read off stored rows for every Team with :data:`MIN_ROUNDS` on a
Side of the Map, and a Team's number is said as its percentile among them:

* T: when the first duel comes and the bomb goes down (medians), how often it
  is down inside :data:`EARLY_PLANT` and how often after :data:`LATE_PLANT`; an
  execute (two or more smokes or fires landing on the site in the
  :data:`EXECUTE_WINDOW` before the plant) or a fake (two or more on one site,
  the plant on the other);
* CT: an early pick (the first kill theirs inside :data:`EARLY_PICK`), utility
  to slow the T inside :data:`DELAY_SECONDS`, and in a post-plant Round lost,
  how often someone saved;
* both: a force after losing a pistol, the Round won after the first kill and
  after the first death, and full buys won against a light one;
* from the Round search's tokens (schema 2): a Side in mid by :data:`MID_AT`,
  a T lurk (one away from three or more at :data:`LURK_AT`), and how fast
  another CT reaches a site after losing its opening (:data:`ROTATE_WITHIN`).

The Pool is computed once per parse and Map and shared (:mod:`pool_cache`).
"""

from __future__ import annotations

import gzip
import json
import statistics
from collections import Counter, defaultdict

from sqlalchemy import func, select

from app.models import GameMap, GrenadeThrow, KillEvent, MatchMap, ReplayRound, Round
from app.services import after_contact, mn, playbook, pool_cache
from app.services.analysis_store import PISTOL_ROUNDS
from app.services.dbctx import db

STYLE_SCHEMA = 2  # 2: lurk, mid control, rotations (from the Round search's tokens)
MIN_ROUNDS = 12
EARLY_PLANT = 40.0
LATE_PLANT = 70.0
EXECUTE_WINDOW = 15.0
EXECUTE_GRENADES = 2
FAKE_WINDOW = 30.0
EARLY_PICK = 20.0
DELAY_SECONDS = 25.0
LIGHT = ("eco", "force")
MID_AT = 20  # seconds: who holds mid by then
LURK_AT = 30  # seconds: one T away from three or more on the other site
ROTATE_WITHIN = 20  # seconds after an opening at a site for another CT to arrive
# Fewer Rounds behind a number than this and the page marks it thin.
THIN = 5

# key -> (side, label, unit, which way is "more"), in the page's order.
METRICS = {
    "contact": ("t", "Анхны тулаан", "s", "хожуу"),
    "plant": ("t", "Plant-ын хугацаа", "s", "хожуу"),
    "early_plant": ("t", f"{int(EARLY_PLANT)} s дотор plant", "%", "хурдан"),
    "late_plant": ("t", f"{int(LATE_PLANT)} s-ээс хойш plant", "%", "удаан"),
    "execute": ("t", "Utility-тэй execute", "%", "олон"),
    "fake": ("t", "Fake", "%", "олон"),
    "mid_t": ("t", f"{MID_AT} s-д mid-д", "%", "олон"),
    "lurk": ("t", "Lurk", "%", "олон"),
    "early_pick": ("ct", f"Эхний {int(EARLY_PICK)} s-д pick", "%", "түрэмгий"),
    "mid_ct": ("ct", f"{MID_AT} s-д mid-д", "%", "олон"),
    "rotate": ("ct", "Rotate (opening-ийн дараа)", "s", "удаан"),
    "delay": ("ct", "Саатуулах utility", "%", "олон"),
    "saves": ("ct", "Plant-ын дараа хэмнэх", "%", "олон"),
    "force_after_pistol": ("both", "Pistol алдсаны дараа force", "%", "олон"),
    "convert": ("both", "Эхний kill → раунд", "%", "сайн"),
    "comeback": ("both", "Эхний үхэл → раунд", "%", "сайн"),
    "anti_eco": ("both", "Full vs хөнгөн buy", "%", "сайн"),
}


def _rows(map_name: str) -> list:
    return list(
        db().execute(
            select(
                Round.id, Round.match_map_id, Round.number, Round.freeze_end_tick,
                Round.bomb_plant_tick, Round.bomb_site, Round.winner_team_id,
                Round.ct_team_id, Round.t_team_id, Round.ct_buy, Round.t_buy, MatchMap.tickrate,
            )
            .join(MatchMap, MatchMap.id == Round.match_map_id)
            .join(GameMap, GameMap.id == MatchMap.game_map_id)
            .where(GameMap.name == map_name, MatchMap.parsed_at.is_not(None))
            .order_by(Round.match_map_id, Round.number)
        )
    )  # fmt: skip


def _first_kills(ids: list[int]) -> dict[int, tuple]:
    first = (
        select(KillEvent.round_id, func.min(KillEvent.tick).label("tick"))
        .where(KillEvent.round_id.in_(ids))
        .group_by(KillEvent.round_id)
        .subquery()
    )
    out = {}
    for rid, tick, side, x, y, z in db().execute(
        select(
            KillEvent.round_id, KillEvent.tick, KillEvent.attacker_side, KillEvent.victim_x,
            KillEvent.victim_y, KillEvent.victim_z,
        ).join(first, (first.c.round_id == KillEvent.round_id) & (first.c.tick == KillEvent.tick))
    ):  # fmt: skip
        out.setdefault(rid, (tick, side, (x, y, z)))
    return out


def _tokens(rows) -> dict[tuple[int, int], dict]:
    """The Round search's per-second place counts, by (Match Map, Round)."""
    maps = {r.match_map_id for r in rows}
    out = {}
    for mm, number, blob in db().execute(
        select(ReplayRound.match_map_id, ReplayRound.number, ReplayRound.tokens).where(
            ReplayRound.match_map_id.in_(maps), ReplayRound.tokens.is_not(None)
        )
    ):
        out[(mm, number)] = json.loads(gzip.decompress(blob))
    return out


def _lurked(tk: dict, toward: dict[str, set]) -> bool:
    """At LURK_AT, one T on a site's side while three or more are on the other."""
    a = after_contact._at(tk, "t", LURK_AT, toward["A"])
    b = after_contact._at(tk, "t", LURK_AT, toward["B"])
    return (a == 1 and b >= 3) or (b == 1 and a >= 3)


def _rotated(tk: dict, toward: set, s0: int) -> float | None:
    """Seconds after an opening at a site until one more CT stands there."""
    base = after_contact._at(tk, "ct", s0 + 1, toward)
    for d in range(2, ROTATE_WITHIN + 1):
        if after_contact._at(tk, "ct", s0 + d, toward) > base:
            return float(d)
    return None


def _grenades(ids: list[int]) -> dict[int, list]:
    out: dict[int, list] = defaultdict(list)
    for rid, side, start, x, y, z in db().execute(
        select(
            GrenadeThrow.round_id, GrenadeThrow.thrower_side, GrenadeThrow.start_tick,
            GrenadeThrow.x, GrenadeThrow.y, GrenadeThrow.z,
        ).where(
            GrenadeThrow.round_id.in_(ids),
            GrenadeThrow.type.in_(("smoke", "inferno")),
            GrenadeThrow.start_tick.is_not(None),
        )
    ):  # fmt: skip
        out[rid].append((side, start, (x, y, z)))
    return out


def _ct_deaths_after_plant(ids: list[int]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = defaultdict(list)
    for rid, tick in db().execute(
        select(KillEvent.round_id, KillEvent.tick).where(
            KillEvent.round_id.in_(ids), KillEvent.victim_side == "ct"
        )
    ):
        out[rid].append(tick)
    return out


def _values(map_name: str) -> dict[str, dict[str, list]]:
    """``{team: {metric: [per-Round values]}}`` for every Team on the Map."""
    rows = _rows(map_name)
    ids = [r.id for r in rows]
    if not ids:
        return {}
    first = _first_kills(ids)
    nades = _grenades(ids)
    ct_deaths = _ct_deaths_after_plant(ids)
    sites = playbook.site_centroids(map_name)
    tokens = _tokens(rows)
    leans = after_contact.place_leans(map_name)
    toward = {w: {p for p, lean in leans.items() if lean == w} for w in ("A", "mid", "B")}
    by_map: dict[int, dict[int, object]] = defaultdict(dict)
    for r in rows:
        by_map[r.match_map_id][r.number] = r
    out: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        rate = r.tickrate or 64

        def secs(tick, r=r, rate=rate):
            return (tick - r.freeze_end_tick) / rate

        t, ct = str(r.t_team_id or ""), str(r.ct_team_id or "")
        k = first.get(r.id)
        tk = tokens.get((r.match_map_id, r.number))
        if t:
            mine = out[t]
            mine["_t_rounds"].append(1)
            if tk:
                mine["mid_t"].append(int(after_contact._at(tk, "t", MID_AT, toward["mid"]) > 0))
                mine["lurk"].append(int(_lurked(tk, toward)))
            if k:
                mine["contact"].append(secs(k[0]))
            if r.bomb_plant_tick:
                at = secs(r.bomb_plant_tick)
                mine["plant"].append(at)
                mine["late_plant"].append(int(at >= LATE_PLANT))
                landed = [
                    (playbook.lean(pos, sites), secs(start))
                    for side, start, pos in nades.get(r.id, ())
                    if side == "t" and sites and None not in pos
                ]
                on_site = sum(
                    1
                    for lean, s in landed
                    if lean == r.bomb_site and at - EXECUTE_WINDOW <= s <= at
                )
                mine["execute"].append(int(on_site >= EXECUTE_GRENADES))
                other = "B" if r.bomb_site == "A" else "A"
                faked = sum(
                    1 for lean, s in landed if lean == other and at - FAKE_WINDOW <= s <= at
                )
                mine["fake"].append(int(r.bomb_site in ("A", "B") and faked >= EXECUTE_GRENADES))
            mine["early_plant"].append(
                int(bool(r.bomb_plant_tick) and secs(r.bomb_plant_tick or 0) <= EARLY_PLANT)
            )
        if ct:
            mine = out[ct]
            mine["_ct_rounds"].append(1)
            if tk:
                mine["mid_ct"].append(int(after_contact._at(tk, "ct", MID_AT, toward["mid"]) > 0))
                where = playbook.lean(k[2], sites) if k and sites and None not in k[2] else ""
                if k and k[1] == "t" and where in ("A", "B"):
                    took = _rotated(tk, toward[where], int(secs(k[0])))
                    if took is not None:
                        mine["rotate"].append(took)
            mine["early_pick"].append(int(bool(k) and k[1] == "ct" and secs(k[0]) <= EARLY_PICK))
            mine["delay"].append(
                int(any(side == "ct" and secs(start) <= DELAY_SECONDS
                        for side, start, _pos in nades.get(r.id, ())))
            )  # fmt: skip
            if r.bomb_plant_tick and r.winner_team_id and r.winner_team_id != r.ct_team_id:
                died = sum(1 for tick in ct_deaths.get(r.id, ()) if tick >= r.bomb_plant_tick)
                before = sum(1 for tick in ct_deaths.get(r.id, ()) if tick < r.bomb_plant_tick)
                mine["saves"].append(int(before + died < 5))
        prev = by_map[r.match_map_id].get(r.number - 1)
        for team, buy in ((t, r.t_buy), (ct, r.ct_buy)):
            if not team:
                continue
            mine = out[team]
            if prev is not None and prev.number in PISTOL_ROUNDS and prev.winner_team_id:
                if str(prev.winner_team_id) != team and buy:
                    mine["force_after_pistol"].append(int(buy in ("force", "full")))
            won = str(r.winner_team_id or "") == team
            if k:
                theirs = k[1] == ("t" if team == t else "ct")
                mine["convert" if theirs else "comeback"].append(int(won))
            their_buy = r.ct_buy if team == t else r.t_buy
            if buy == "full" and their_buy in LIGHT:
                mine["anti_eco"].append(int(won))
    return {team: dict(m) for team, m in out.items()}


def _summary(values: dict[str, list]) -> dict[str, tuple]:
    """``{metric: (value, n)}``: medians in seconds, shares in percent."""
    out = {}
    for key, (side, _label, unit, _more) in METRICS.items():
        seen = values.get(key) or []
        enough = (
            len(values.get("_t_rounds", [])) if side == "t" else len(values.get("_ct_rounds", []))
        )
        if side == "both":
            enough = len(values.get("_t_rounds", [])) + len(values.get("_ct_rounds", []))
        if enough < MIN_ROUNDS or not seen:
            continue
        value = statistics.median(seen) if unit == "s" else 100.0 * sum(seen) / len(seen)
        out[key] = (round(value, 1), len(seen))
    return out


def pool(map_name: str) -> dict[str, dict[str, list]]:
    """Every Team's numbers on the Map, ``{team: {metric: [value, n]}}``, shared."""
    key = f"style:v{STYLE_SCHEMA}:{map_name}:{pool_cache.parse_stamp()}"
    return pool_cache.remember(
        key, lambda: {team: _summary(v) for team, v in _values(map_name).items()}
    )


def team(team_id: int, map_name: str) -> dict:
    """The Team's style on the Map, each number with its percentile in the Pool."""
    everyone = pool(map_name)
    mine = everyone.get(str(team_id)) or {}
    sides: dict[str, list] = defaultdict(list)
    for key, (side, label, unit, more) in METRICS.items():
        if key not in mine:
            continue
        value, n = mine[key]
        others = [v[key][0] for v in everyone.values() if key in v]
        below = sum(1 for o in others if o < value)
        same = sum(1 for o in others if o == value)
        sides[side].append(
            {
                "key": key,
                "label": label,
                "value": value,
                "unit": unit,
                "n": n,
                "thin": n < THIN,
                "pct": round(100 * (below + 0.5 * same) / len(others)) if others else None,
                "teams": len(others),
                "more": more,
            }
        )
    return {
        "map": map_name,
        "label": mn.game_map(map_name),
        "sides": [
            {"side": s, "label": _side_label(s), "metrics": sides[s]}
            for s in ("t", "ct", "both")
            if sides.get(s)
        ],  # fmt: skip
    }


def _side_label(side: str) -> str:
    return {"t": "T тал", "ct": "CT тал", "both": "Хоёр тал"}[side]


def maps_of(team_id: int) -> list[str]:
    """The Maps the Team has stored Rounds on, the most played first."""
    counts: Counter = Counter()
    for name, n in db().execute(
        select(GameMap.name, func.count(MatchMap.id))
        .join(MatchMap, MatchMap.game_map_id == GameMap.id)
        .where(
            MatchMap.parsed_at.is_not(None),
            (MatchMap.team1_id == team_id) | (MatchMap.team2_id == team_id),
        )
        .group_by(GameMap.name)
    ):
        counts[name] = n
    return [name for name, _n in counts.most_common()]
