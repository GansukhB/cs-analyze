"""Where a Team stands and moves on one Map and Side (v2 screen 05).

Four views of the same Rounds, each Team apart so two can be set side by side:

* **heat**: where its living Players stood, sampled every two seconds from the
  stored Replay (8 Hz), in windows of the Round's clock, and the share of
  player-seconds in each game Callout per window;
* **move**: its Players' walked routes (``player_map_routes``), pooled by route
  across the five: how often, how often the Round was won, the kills and deaths;
* **trade**: who avenged whom inside the trade window, and where the deaths no one
  avenged fell;
* **lurk** (T only): the Player who stands far from every living teammate 30 s in
  on 40% of his Rounds (the Review's rule, ``review._lurkers``), his distance
  from the nearest teammate through the Round against the rest, and what his
  Rounds came to.

The Replay pass is the heavy one, so it is cut once per parse (``pool_cache``).
Bind a session with ``dbctx.using``.
"""

from __future__ import annotations

import gzip
import json
import math
from collections import Counter, defaultdict

from sqlalchemy import select

from app.models import (
    KillEvent,
    MatchMap,
    Player,
    PlayerMapRoute,
    PlayerRound,
    ReplayRound,
    Round,
    Team,
)
from app.services import heatmap_groups, pool_cache
from app.services import scope as visibility
from app.services.dbctx import db
from app.services.demo_parser import TRADE_SECONDS
from app.services.review import LURK_AT, LURK_DIST, LURK_ROUNDS, LURK_SHARE

SCHEMA = 1
# The Round's clock in windows (seconds from the end of buy time).
WINDOWS = ((0, 20), (20, 45), (45, 75), (75, 999))
SAMPLE_SECONDS = 2
MAX_POINTS = 2500
CURVE_STEP = 5
CURVE_BINS = 24  # to 120 s
ROUTES = 6


def _maps(team: Team, map_name: str) -> list[MatchMap]:
    from app.services import team_numbers

    return [m for m in team_numbers.team_maps(team.id) if team_numbers.map_name(m) == map_name]


def _side_rounds(team_id: int, maps: list[MatchMap], side: str) -> list[Round]:
    column = Round.t_team_id if side == "t" else Round.ct_team_id
    return list(
        db().scalars(
            select(Round).where(
                Round.match_map_id.in_([m.id for m in maps] or [0]), column == team_id
            )
        )
    )


def digest(team: Team, map_name: str, side: str) -> dict:
    """The Replay pass for one Team, Map and Side, cut once per parse."""
    key = (
        f"v2:spatial:v{SCHEMA}:{team.id}:{map_name}:{side}:"
        f"{pool_cache.parse_stamp()}{visibility.cache_part(db())}"
    )
    return pool_cache.remember(key, lambda: _digest(team, map_name, side))


def _digest(team: Team, map_name: str, side: str) -> dict:
    maps = _maps(team, map_name)
    rounds = _side_rounds(team.id, maps, side)
    by_map: dict[int, set[int]] = defaultdict(set)
    for r in rounds:
        by_map[r.match_map_id].add(r.number)
    points: list[list[list[float]]] = [[] for _ in WINDOWS]
    places: list[Counter] = [Counter() for _ in WINDOWS]
    near: dict[str, list[list[float]]] = defaultdict(lambda: [[] for _ in range(CURVE_BINS)])
    alone: Counter = Counter()
    played: Counter = Counter()
    lurk_rounds: dict[str, list[tuple[int, int]]] = defaultdict(list)
    names: dict[str, str] = {}
    session = db()
    for mm, numbers in by_map.items():
        rows = session.execute(
            select(ReplayRound.number, ReplayRound.payload).where(
                ReplayRound.match_map_id == mm, ReplayRound.number.in_(list(numbers))
            )
        )
        for number, blob in rows:
            p = json.loads(gzip.decompress(blob))
            hz = int(p["hz"])
            mine = [pl for pl in p["players"] if pl["side"] == side]
            for pl in mine:
                names[pl["sid"]] = pl["name"]
            frames = min((len(pl["hp"]) for pl in mine), default=0)
            for s in range(0, int(frames / hz)):
                f = s * hz
                living = {
                    pl["sid"]: (pl["x"][f], pl["y"][f])
                    for pl in mine
                    if f < len(pl["hp"]) and pl["hp"][f] and pl["x"][f] is not None
                }
                w = next(i for i, (a, b) in enumerate(WINDOWS) if a <= s < b)
                for pl in mine:
                    if pl["sid"] not in living:
                        continue
                    here = None
                    for frame, idx in pl["place"]:
                        if frame > f:
                            break
                        here = idx
                    if here is not None:
                        places[w][p["places"][here]] += 1
                    if s % SAMPLE_SECONDS == 0:
                        x, y = living[pl["sid"]]
                        points[w].append([round(x, 1), round(y, 1)])
                if len(living) >= 2 and s // CURVE_STEP < CURVE_BINS:
                    for sid, (x, y) in living.items():
                        d = min(
                            math.hypot(x - ox, y - oy) for o, (ox, oy) in living.items() if o != sid
                        )
                        near[sid][s // CURVE_STEP].append(d)
                        if s == LURK_AT:
                            played[sid] += 1
                            if d > LURK_DIST:
                                alone[sid] += 1
                                lurk_rounds[sid].append((mm, number))
    for w, pts in enumerate(points):
        if len(pts) > MAX_POINTS:
            step = len(pts) / MAX_POINTS
            points[w] = [pts[int(i * step)] for i in range(MAX_POINTS)]
    curves = {
        sid: [round(sum(v) / len(v)) if v else None for v in bins] for sid, bins in near.items()
    }
    return {
        "rounds": len(rounds),
        "points": points,
        "places": [dict(c) for c in places],
        "curves": curves,
        "alone": dict(alone),
        "played": dict(played),
        "lurk_rounds": {sid: [list(x) for x in v] for sid, v in lurk_rounds.items()},
        "names": names,
    }


def heat(d: dict) -> dict:
    zones: dict[str, list[float]] = defaultdict(lambda: [0.0] * len(WINDOWS))
    for w, counts in enumerate(d["places"]):
        total = sum(counts.values()) or 1
        for place, n in counts.items():
            zones[place][w] = round(100.0 * n / total, 1)
    every: Counter = Counter()
    for counts in d["places"]:
        every.update(counts)
    total = sum(every.values()) or 1
    rows = [
        {"place": place, "shares": shares, "all": round(100.0 * every[place] / total, 1)}
        for place, shares in zones.items()
    ]
    rows.sort(key=lambda r: -r["all"])
    return {"points": d["points"], "zones": rows[:14]}


def lurk(team: Team, d: dict) -> dict | None:
    """The Team's lurker on this Map's T side, by the Review's rule, and his Rounds."""
    # Short of the rule, the one who stood alone most often is still shown, marked.
    eligible = [sid for sid, n in d["played"].items() if n >= LURK_ROUNDS]
    if not eligible:
        return None
    sid = max(eligible, key=lambda s: d["alone"].get(s, 0) / d["played"][s])
    rule = d["alone"].get(sid, 0) / d["played"][sid] >= LURK_SHARE
    others = [c for s, c in d["curves"].items() if s != sid]
    rest = []
    for i in range(CURVE_BINS):
        values = [c[i] for c in others if c[i] is not None]
        rest.append(round(sum(values) / len(values)) if values else None)
    rounds = [tuple(x) for x in d["lurk_rounds"].get(sid, [])]
    player = db().scalar(select(Player).where(Player.steamid == int(sid)))
    outcome = _lurk_outcome(team.id, player.id if player else None, rounds)
    return {
        "steamid": sid,
        "name": d["names"].get(sid, "?"),
        "share": round(100.0 * d["alone"].get(sid, 0) / d["played"][sid]),
        "rule": rule,
        "played": d["played"][sid],
        "curve": d["curves"].get(sid, []),
        "team_curve": rest,
        **outcome,
    }


def _lurk_outcome(team_id: int, player_id: int | None, rounds: list[tuple[int, int]]) -> dict:
    out = {"rounds": len(rounds), "kills": 0, "deaths": 0, "untraded": 0, "won": 0}
    if not rounds or player_id is None:
        return out
    session = db()
    for mm, number in rounds:
        r = session.scalar(select(Round).where(Round.match_map_id == mm, Round.number == number))
        if r is None:
            continue
        out["won"] += 1 if r.winner_team_id == team_id else 0
        pr = session.scalar(
            select(PlayerRound).where(
                PlayerRound.round_id == r.id, PlayerRound.player_id == player_id
            )
        )
        if pr:
            out["kills"] += pr.kills
            out["deaths"] += pr.deaths
            out["untraded"] += 1 if pr.deaths and not pr.traded else 0
    return out


def routes(team: Team, map_name: str, side: str) -> list[dict]:
    """The Team's walked routes on this Map and Side, pooled across its Players."""
    maps = _maps(team, map_name)
    rows = db().scalars(
        select(PlayerMapRoute).where(
            PlayerMapRoute.match_map_id.in_([m.id for m in maps] or [0]),
            PlayerMapRoute.team_id == team.id,
            PlayerMapRoute.side == side,
        )
    )
    pooled: dict[str, dict] = {}
    total = 0
    for r in rows:
        total += r.rounds
        e = pooled.setdefault(
            r.route_key,
            {
                "places": r.places,
                "rounds": 0,
                "won": 0,
                "kills": 0,
                "deaths": 0,
                "path": r.path,
                "best": 0,
            },
        )
        e["rounds"] += r.rounds
        e["won"] += r.rounds_won
        e["kills"] += r.kills
        e["deaths"] += r.deaths
        if r.rounds > e["best"]:
            e["best"], e["path"] = r.rounds, r.path
    out = [
        {
            "label": " → ".join(e["places"]),
            "rounds": e["rounds"],
            "share": round(100.0 * e["rounds"] / total, 1) if total else 0.0,
            "win": round(100.0 * e["won"] / e["rounds"]) if e["rounds"] else None,
            "kills": e["kills"],
            "deaths": e["deaths"],
            "path": [
                [round(s["x"], 1), round(s["y"], 1)] for s in e["path"] if s.get("x") is not None
            ],
        }
        for e in pooled.values()
        if len(e["places"]) >= 2
    ]
    out.sort(key=lambda r: -r["rounds"])
    return out[:ROUTES]


def trades(team: Team, map_name: str, side: str) -> dict:
    """Who avenged whom inside the trade window, and the deaths nobody avenged."""
    maps = _maps(team, map_name)
    rounds = _side_rounds(team.id, maps, side)
    ids = [r.id for r in rounds] or [0]
    rates = {m.id: m.tickrate or 64 for m in maps}
    rate_of = {r.id: rates.get(r.match_map_id, 64) for r in rounds}
    session = db()
    team_of = {
        (rid, pid): tid
        for rid, pid, tid in session.execute(
            select(PlayerRound.round_id, PlayerRound.player_id, PlayerRound.team_id).where(
                PlayerRound.round_id.in_(ids)
            )
        )
    }
    kills = session.execute(
        select(KillEvent.round_id, KillEvent.tick, KillEvent.attacker_id, KillEvent.victim_id,
               KillEvent.attacker_x, KillEvent.attacker_y, KillEvent.victim_x, KillEvent.victim_y)
        .where(KillEvent.round_id.in_(ids))
        .order_by(KillEvent.round_id, KillEvent.tick)
    ).all()  # fmt: skip
    by_round: dict[int, list] = defaultdict(list)
    for k in kills:
        by_round[k.round_id].append(k)
    pair: Counter = Counter()
    died: Counter = Counter()
    avenged: Counter = Counter()
    segments, lone = [], []
    for rid, seq in by_round.items():
        window = TRADE_SECONDS * rate_of.get(rid, 64)
        for i, k in enumerate(seq):
            if team_of.get((rid, k.victim_id)) != team.id or k.attacker_id is None:
                continue
            died[k.victim_id] += 1
            trader = next(
                (
                    later
                    for later in seq[i + 1 :]
                    if later.tick - k.tick <= window
                    and later.victim_id == k.attacker_id
                    and team_of.get((rid, later.attacker_id)) == team.id
                ),
                None,
            )
            if trader is not None:
                avenged[k.victim_id] += 1
                pair[(k.victim_id, trader.attacker_id)] += 1
                if k.victim_x is not None and trader.attacker_x is not None:
                    segments.append(
                        [[k.victim_x, k.victim_y], [trader.attacker_x, trader.attacker_y]]
                    )
            elif k.victim_x is not None:
                lone.append([round(k.victim_x, 1), round(k.victim_y, 1)])
    pids = set(died) | {t for _v, t in pair}
    names = dict(
        session.execute(select(Player.id, Player.name).where(Player.id.in_(pids or {0}))).all()
    )
    order = sorted(died, key=lambda p: -died[p])
    traders = sorted({t for _v, t in pair} | set(order), key=lambda p: names.get(p, ""))
    return {
        "players": [
            {"name": names.get(p, "?"), "deaths": died[p], "traded": avenged[p],
             "pct": round(100.0 * avenged[p] / died[p]) if died[p] else None}
            for p in order
        ],
        "traders": [names.get(t, "?") for t in traders],
        "matrix": [[pair.get((v, t), 0) for t in traders] for v in order],
        "segments": segments[:400],
        "lone": lone[:400],
    }  # fmt: skip


def build(team: Team, map_name: str, side: str, mode: str) -> dict:
    out: dict = {"team": {"id": team.id, "name": team.name}}
    if mode in ("heat", "lurk"):
        d = digest(team, map_name, side)
        out["rounds"] = d["rounds"]
        if mode == "heat":
            out["heat"] = heat(d)
        else:
            out["lurk"] = lurk(team, d) if side == "t" else None
    else:
        out["rounds"] = len(_side_rounds(team.id, _maps(team, map_name), side))
    if mode == "move":
        out["routes"] = routes(team, map_name, side)
    if mode == "trade":
        out["trade"] = trades(team, map_name, side)
    return out


def scene(maps: list[MatchMap], map_name: str) -> dict:
    """The overview and the Callout labels the page draws over."""
    geometry = heatmap_groups.map_geometry(maps)
    return {"plate": heatmap_groups.plate(map_name), "labels": geometry.get("labels") or []}
