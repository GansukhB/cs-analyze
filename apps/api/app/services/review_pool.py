"""Strengths and Weaknesses read off the Reviews, against the Pool (CONTEXT.md).

Every stored Review at the current :func:`app.services.review.version` is cut
into tallies, one per Match Map, Team and Side: the Summary's numbers (opening
duels, trades, buys, pistols, post-plant, retakes, comebacks), every Finding of
that Team with its Round, Player, Swing and Spot, and each Player's Swing per
Round. A Team's number on one Side of a Map is a Strength or a Weakness when its
z against the Pool's passes the metrics tab's bounds (±0.8) (docs/adr/0008).
Small samples are pulled toward what is known: the Pool's spread is measured
net of chance, and a Map's own number only moves the Team's tendency across all
its Maps as far as its events allow (:class:`Estimate`); a line carried by that
tendency is marked ``all_maps``. The same holds for a Lineup Player's Swing
per Round.

The Game Plan never rebuilds a Review: one that is stale or missing is left out
and counted (:func:`state`), and :func:`request_refresh` has the worker rebuild
it. The tallies are cut once per set of stored Reviews and kept in the process,
keyed by :func:`stamp`. Like the other game-plan services this takes no session:
bind one with ``dbctx.using``.
"""

from __future__ import annotations

import gzip
import json
import logging
import math
import statistics
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from redis.exceptions import RedisError
from sqlalchemy import func, or_, select

from app.models import GameMap, MatchMap, MatchMapReview, Player, Team, TickDataset
from app.services import mapstrategy, review, review_summary
from app.services import scope as visibility
from app.services.dbctx import db, memo
from app.services.gameplan import MIN_POOL_ROUNDS, STRENGTH_Z
from app.services.playbook import MAX_REFS, MIN_HABIT_ROUNDS, strength

logger = logging.getLogger(__name__)

SIDES = ("ct", "t")
# A Pool needs this many members before anyone is measured against it.
MIN_POOL_TEAMS = 3
MIN_POOL_PLAYERS = 8
# A Player's Swing per Round says something past these Rounds on one Side: on
# one Map, and across all Maps (where it also joins the Player Pool).
PLAYER_MAP_ROUNDS = 24
PLAYER_ALL_ROUNDS = 40
# A Map's own number carries a line from this reliability on; below it the line
# is the Team's tendency across all Maps, and says so (see :class:`Estimate`).
MIN_RELIABILITY = 0.5
# A Round counts as one a Player won or lost for their Team past this Swing.
PLAYER_ROUND_SWING = 0.15
# A Finding's rate is counted per this many Rounds, the length of a regulation Map.
PER_ROUNDS = 24
HALF = 12
# What a Finding without Swing is worth (review_summary.ZERO_SWING_VALUE).
ZERO_SWING_VALUE = review_summary.ZERO_SWING_VALUE
REFRESH_LOCK = "review-refresh"
REFRESH_LOCK_SECONDS = 30 * 60
# After a refresh some Review failed to build, wait this long before trying again.
REFRESH_RETRY_SECONDS = 10 * 60


@dataclass(frozen=True)
class Measure:
    """One number a Team can be strong or weak at.

    A ``rate`` is a share of events (opening duels won, deaths traded, Rounds won
    after the plant); a ``code`` is how often a kind of Finding happens per
    :data:`PER_ROUNDS` Rounds. ``says`` is which way it can speak: a rate both,
    a good Finding only as a Strength (more of it), a bad one only as a Weakness.
    ``fewest`` is the events (rate) or Rounds (code) it needs at one scope.
    """

    key: str
    kind: str
    says: str
    sides: tuple[str, ...] = SIDES
    fewest: int = 8
    value: float | None = None

    @property
    def good_high(self) -> bool:
        return self.kind == "rate" or self.says == "strength"


def _rate(key, says="both", sides=SIDES, fewest=8, value=1.0) -> Measure:
    return Measure(key, "rate", says, sides, fewest, value)


def _good(code, sides=SIDES, value=None) -> Measure:
    return Measure(code, "code", "strength", sides, HALF, value)


def _bad(code, sides=SIDES, value=None) -> Measure:
    return Measure(code, "code", "weakness", sides, HALF, value)


MEASURES: tuple[Measure, ...] = (
    _rate("opening", value=None),  # an opening duel is worth its Win probability move
    _rate("trade", value=None),  # an untraded death is worth what it cost
    _rate("pistol", fewest=8),
    _rate("full_v_full", fewest=6),
    _rate("force", fewest=4),
    _rate("eco", says="strength", fewest=4),
    _rate("full_v_light", says="weakness", fewest=4),
    _rate("post_plant", sides=("t",), fewest=4),
    _rate("retake", sides=("ct",), fewest=4),
    _rate("comeback", says="strength", fewest=PER_ROUNDS),
    _good("entry"),
    _good("big_frag"),
    _good("multikill"),
    _good("clutch"),
    _good("plant", sides=("t",)),
    _good("defuse", sides=("ct",)),
    _good("flash_kill"),
    _good("nade_damage_kill"),
    _good("fire_delay", sides=("ct",)),
    _bad("died_in_advantage"),
    _bad("advantage_lost"),
    _bad("team_flashed_death"),
    _bad("team_flash"),
    _bad("lost_weapon_save"),
    _bad("awp_miss"),
    _bad("moving_shots"),
    _bad("unfinished"),
    _bad("blind_unpunished"),
    _bad("no_gun_in_hand"),
    _bad("unused_utility"),
    _bad("bomb_lost", sides=("t",)),
    _bad("time_out", sides=("t",)),
    _bad("kitless", sides=("ct",)),
    _bad("defuse_chance", sides=("ct",)),
    _bad("crosshair"),
    _bad("unscoped_awp"),
    _bad("saw_no_shot"),
    _bad("saw_first_lost"),
)
BY_KEY = {m.key: m for m in MEASURES}
# The Findings that are good for their Team (the Summary's split): Key plays and
# the Utility effects that helped.
GOOD_FINDINGS = {"entry", "big_frag", "multikill", "clutch", "plant", "defuse", "retake",
                 *review_summary.GOOD_UTILITY}  # fmt: skip


# ------------------------------------------------------------- the tallies ---
@dataclass
class Tally:
    """One Team on one Side of one Match Map, as its Review tells it."""

    mm: int
    match: int
    num: int
    map: str
    team: int
    side: str
    sight: bool
    loadout: bool = True
    rounds: list[int] = field(default_factory=list)
    # rate key -> [(round, hit, sid, value)]; sid is who the event is about.
    events: dict[str, list[tuple]] = field(default_factory=lambda: defaultdict(list))
    # Finding code -> [(round, t, sid, swing, spot)]
    codes: dict[str, list[tuple]] = field(default_factory=lambda: defaultdict(list))
    # sid -> [(round, swing)]
    players: dict[str, list[tuple]] = field(default_factory=lambda: defaultdict(list))

    def ref(self, n: int) -> dict:
        return {"match": self.match, "map": self.num, "round": n}


def can_show(t: Tally, code: str) -> bool:
    """Whether this Team-map's Tick Data could have shown ``code`` at all."""
    if code in review.SIGHT_CODES and not t.sight:
        return False
    return t.loadout or code not in review.LOADOUT_CODES


def _cut(stored: dict, meta: dict) -> list[Tally]:
    """A Review's tallies, one per Team and Side it has Rounds for."""
    out: dict[tuple, Tally] = {}

    def tally(team, side) -> Tally:
        key = (team, side)
        if key not in out:
            out[key] = Tally(**meta, team=team, side=side, sight=bool(stored.get("sightings")),
                             loadout=not stored.get("needs_loadout"))  # fmt: skip
        return out[key]

    for r in stored["rounds"]:
        for side in SIDES:
            team = r.get(f"{side}_team_id")
            if team is None:
                continue
            t = tally(team, side)
            rr = review_summary._Round(r, side)
            n = rr.n
            t.rounds.append(n)
            k = rr.opening()
            if k is not None:
                got = rr.mine(k["a"])
                t.events["opening"].append((n, got, k["a"] if got else k["v"], abs(rr.delta(k))))
            for k in r.get("kills") or []:
                if rr.mine(k["v"]):
                    t.events["trade"].append((n, bool(k.get("traded")), k["v"], 0.0))
            buys = {
                "pistol": rr.buy == "pistol",
                "full_v_full": rr.buy == "full" and rr.their_buy == "full",
                "force": rr.buy == "force",
                "eco": rr.buy == "eco",
                "full_v_light": rr.buy == "full" and rr.their_buy in ("eco", "force"),
            }
            for key, applies in buys.items():
                if applies:
                    t.events[key].append((n, rr.won, None, 1.0))
            if rr.plant is not None:
                key = "post_plant" if side == "t" else "retake"
                t.events[key].append((n, rr.won, rr.plant.get("sid"), 1.0))
            lows = [p for _t, p in rr.wp]
            low = bool(rr.won and lows and min(lows) <= review_summary.COMEBACK_WP)
            t.events["comeback"].append((n, low, r.get("decider") if low else None, 1.0))
            swing = r.get("swing") or {}
            for sid, s in (r.get("sides") or {}).items():
                if s == side:
                    t.players[sid].append((n, float(swing.get(sid, 0.0))))
    by_n = {r["n"]: r for r in stored["rounds"]}
    for f in stored["findings"]:
        r = by_n.get(f.get("round"))
        if r is None or f.get("side") not in SIDES:
            continue
        team = r.get(f"{f['side']}_team_id")
        if team is None:
            continue
        sid = (f.get("sids") or [None])[0]
        spot = (f.get("facts") or {}).get("spot") or ""
        tally(team, f["side"]).codes[f["code"]].append(
            (f["round"], f.get("t") or 0.0, sid, float(f.get("swing") or 0.0), spot)
        )
    return list(out.values())


@dataclass
class Data:
    """Every tally, the Pools they make, and the Players' names."""

    stamp: str
    tallies: list[Tally]
    by_team: dict[int, list[Tally]]
    names: dict[str, str]
    pools: dict[tuple, dict[str, dict]]
    player_pools: dict[tuple, dict]
    untagged: dict[int, int]  # team -> its Match Maps whose Rounds name no Teams
    # sid -> {match_map id: his engagements there} (PL-5), Reviews with Sightings only
    aims: dict[str, dict[int, dict]] = field(default_factory=dict)


_lock = threading.Lock()
_cached: dict[str, Data] = {}


def stamp() -> str:
    """Moves whenever a Review is built or the Review version changes."""

    def compute():
        count, latest = (
            db()
            .execute(
                select(func.count(MatchMapReview.id), func.max(MatchMapReview.updated_at)).where(
                    MatchMapReview.version == review.version()
                )
            )
            .one()
        )
        return f"r{count}-{int(latest.timestamp()) if latest else 0}"

    return memo(("review_stamp",), compute)


def data() -> Data:
    """The tallies and Pools for the stored Reviews, cut once per :func:`stamp`."""
    # Per scope too: a Workspace with official uploads has a Pool of its own (WS-2).
    key = stamp() + visibility.cache_part(db())
    with _lock:
        found = _cached.get(key)
        if found is None:
            found = _load(key)
            _cached.clear()
            _cached[key] = found
    return found


def _load(key: str) -> Data:
    rows = db().execute(
        select(
            MatchMapReview.payload,
            MatchMap.id,
            MatchMap.match_id,
            MatchMap.map_number,
            MatchMap.team1_id,
            MatchMap.team2_id,
            GameMap.name,
        )
        .join(MatchMap, MatchMap.id == MatchMapReview.match_map_id)
        .join(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(MatchMapReview.version == review.version())
    )
    tallies: list[Tally] = []
    names: dict[str, str] = {}
    untagged: Counter = Counter()
    aims: dict[str, dict[int, dict]] = defaultdict(dict)
    for payload, mm, match, num, team1, team2, map_name in rows:
        stored = json.loads(gzip.decompress(payload))
        cut = _cut(stored, {"mm": mm, "match": match, "num": num, "map": map_name})
        tallies += cut
        if not cut:
            for team in (team1, team2):
                if team is not None:
                    untagged[team] += 1
        for p in stored.get("players") or []:
            names[p["sid"]] = p.get("name") or names.get(p["sid"], "?")
            if p.get("aim"):
                aims[p["sid"]][mm] = p["aim"]
    by_team: dict[int, list[Tally]] = defaultdict(list)
    for t in tallies:
        by_team[t.team].append(t)
    pools, player_pools = _pools(by_team)
    return Data(key, tallies, dict(by_team), names, pools, player_pools, dict(untagged), dict(aims))


# ----------------------------------------------------------------- numbers ---
@dataclass
class Read:
    """A Measure read off some tallies: its value and the events behind it."""

    value: float
    of: int
    hits: list[tuple]  # (tally, round, sid, swing/value, spot) for a good reading
    misses: list[tuple]  # the same for a bad one
    per_event: float  # Rounds one event is worth


def read(m: Measure, tallies: list[Tally]) -> Read | None:
    """The Measure over these tallies, or None while it has too few events."""
    if m.kind == "rate":
        hits, misses, worth = [], [], 0.0
        for t in tallies:
            for n, hit, sid, value in t.events.get(m.key, ()):
                (hits if hit else misses).append((t, n, sid, value, ""))
                worth += value
        of = len(hits) + len(misses)
        if of < m.fewest:
            return None
        per_event = m.value if m.value is not None else worth / of
        if m.key == "trade":
            # What an untraded death cost, from the Findings that flagged one.
            cost = [abs(e[3]) for t in tallies for e in t.codes.get("untraded", ())]
            per_event = statistics.fmean(cost) if cost else 0.2
            spots = {}
            for t in tallies:
                for n, _t, sid, _sw, spot in t.codes.get("untraded", ()):
                    spots[(t.mm, n, sid)] = spot
            misses = [(t, n, sid, v, spots.get((t.mm, n, sid), "")) for t, n, sid, v, _ in misses]
        return Read(len(hits) / of, of, hits, misses, per_event)
    # Only the Team-maps whose Tick Data could show this code count (RV-5).
    able = [t for t in tallies if can_show(t, m.key)]
    rounds = sum(len(t.rounds) for t in able)
    if rounds < m.fewest:
        return None
    found = [
        (t, n, sid, swing, spot) for t in able for n, _t, sid, swing, spot in t.codes.get(m.key, ())
    ]
    if m.value is not None:
        per_event = m.value
    else:
        swings = [abs(e[3]) for e in found]
        per_event = statistics.fmean(swings) if swings else 0.0
        per_event = max(per_event, ZERO_SWING_VALUE.get(m.key, 0.0))
    good = m.says == "strength"
    return Read(
        len(found) / rounds * PER_ROUNDS,
        rounds,
        found if good else [],
        [] if good else found,
        per_event,
    )


# The least true spread a Pool is given, by kind: a share, Findings per 24 Rounds,
# Swing per Round.
_FLOOR = {"rate": 0.02, "code": 0.1, "player": 0.003}


def _noise(kind: str, mean: float, of: int, per_round: float = 0.0) -> float:
    """How much a number over ``of`` events varies by chance alone (a variance)."""
    if of <= 0:
        return math.inf
    if kind == "rate":
        return max(mean * (1 - mean), 0.01) / of
    if kind == "code":
        return PER_ROUNDS * max(mean, 0.05) / of
    return per_round / of


def _spread(kind: str, pairs: list[tuple[float, int]], per_round: float = 0.0) -> dict:
    """The Pool's mean and its true spread: the members' spread less what their
    sample sizes alone would make (a team's 2/9 retakes is mostly chance)."""
    values = [v for v, _of in pairs]
    mean = statistics.fmean(values)
    noise = statistics.fmean(_noise(kind, mean, of, per_round) for _v, of in pairs)
    floor = max(abs(mean) * 0.10, _FLOOR[kind])
    sd = math.sqrt(max(statistics.pvariance(values) - noise, floor**2))
    return {"mean": mean, "sd": sd, "n": len(values), "kind": kind, "per_round": per_round}


def _reliability(spread: dict, of: int) -> float:
    """How much of a number over ``of`` events is the Team rather than chance (0..1)."""
    sd2 = spread["sd"] ** 2
    return sd2 / (sd2 + _noise(spread["kind"], spread["mean"], of, spread["per_round"]))


def _z(spread: dict, value: float, of: int) -> tuple[float, float]:
    """``(z, excess)``: the value's distance from the Pool once pulled toward it
    by how little there is of it, so five pistol rounds can't make a Weakness."""
    excess = _reliability(spread, of) * (value - spread["mean"])
    return excess / spread["sd"], excess


def _pools(by_team: dict[int, list[Tally]]) -> tuple[dict, dict]:
    """Each Measure's spread across the Pool: per Map and Side, and per Side."""
    members = {
        team: ts
        for team, ts in by_team.items()
        if sum(len(t.rounds) for t in ts) >= MIN_POOL_ROUNDS
    }
    values: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for ts in members.values():
        scopes: dict[tuple, list[Tally]] = defaultdict(list)
        for t in ts:
            scopes[(t.map, t.side)].append(t)
            scopes[(None, t.side)].append(t)
        for (map_name, side), part in scopes.items():
            for m in MEASURES:
                if side not in m.sides:
                    continue
                got = read(m, part)
                if got is not None:
                    values[(map_name, side)][m.key].append((got.value, got.of))
    pools = {
        scope: {
            key: _spread(BY_KEY[key].kind, pairs)
            for key, pairs in by_key.items()
            if len(pairs) >= MIN_POOL_TEAMS
        }
        for scope, by_key in values.items()
    }
    # Players: Swing per Round, over whichever Teams they played for.
    rounds: dict[tuple, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for ts in by_team.values():
        for t in ts:
            for sid, rows in t.players.items():
                rounds[(t.map, t.side)][sid] += rows
                rounds[(None, t.side)][sid] += rows
    player_pools = {}
    for scope, by_sid in rounds.items():
        need = PLAYER_ALL_ROUNDS if scope[0] is None else PLAYER_MAP_ROUNDS
        kept = [rows for rows in by_sid.values() if len(rows) >= need]
        if len(kept) < MIN_POOL_PLAYERS:
            continue
        per_round = statistics.pvariance([s for rows in kept for _n, s in rows])
        pairs = [(sum(s for _n, s in rows) / len(rows), len(rows)) for rows in kept]
        player_pools[scope] = _spread("player", pairs, per_round)
    return pools, player_pools


# ------------------------------------------------------------ the judgement ---
def _evidence(events: list[tuple], of: int, h2h: set[int], unit: str = "") -> dict:
    """A line's Evidence strength and Replay links (the Playbook's shape)."""
    maps = {e[0].mm for e in events}
    refs, seen = [], set()
    for e in events:
        key = (e[0].mm, e[1])
        if key not in seen:
            seen.add(key)
            refs.append(e[0].ref(e[1]))
        if len(refs) == MAX_REFS:
            break
    out = {
        "n": len(events),
        "of": of,
        "maps": len(maps),
        "h2h": sum(1 for e in events if e[0].mm in h2h),
        "strength": strength(len(maps)),
        "refs": refs,
    }
    if unit:
        out["unit"] = unit
    return out


@dataclass
class Estimate:
    """A Team's (or Player's) number on one Side of a Map, as far as it can be told.

    The tendency across all their Maps, pulled toward the Pool by how much there
    is of it, is carried to this Map's Pool; this Map's own number then moves it
    by how much there is of that. A Map seen twice barely moves it, so a Team
    that trades well everywhere is not called weak at it from one bad night, nor
    strong at entries on a Map where its entries have been poor.

    What a line shows is this Map's own number against its Pool when there is
    one, and beside it the number across all Maps (``everywhere``) when that
    tendency weighed more than the Map did (``scope: all_maps``). When the two
    point opposite ways there is no line: a Team strong at retakes everywhere
    but 0 of 4 on this Map is not called strong at them here.
    """

    z: float  # against this Map's Pool (all Maps' when this Map has no Pool)
    excess: float  # the estimate less that Pool's mean
    scope: str  # "map" when this Map's own events carry it, else "all_maps"
    value: float  # the number shown first
    mean: float  # and its Pool's mean
    everywhere: tuple[float, float] | None  # (value, Pool mean) across all Maps, beside it


def estimate(
    on_map: tuple[float, int] | None,
    everywhere: tuple[float, int] | None,
    map_spread: dict | None,
    all_spread: dict | None,
) -> Estimate | None:
    """``on_map`` and ``everywhere`` are ``(value, events)``, None where too few."""
    if everywhere is None or all_spread is None:
        return None
    tendency = _reliability(all_spread, everywhere[1]) * (everywhere[0] - all_spread["mean"])
    across = (everywhere[0], all_spread["mean"])
    if map_spread is None:
        z = tendency / all_spread["sd"]
        return Estimate(z, tendency, "all_maps", *across, None)
    # A Map's Pool is a few Teams with a few Rounds each: once chance is taken
    # out its spread can read as nothing. The true spread on one Map is taken to
    # be at least the one across all Maps, or any small difference becomes a big z.
    map_spread = {**map_spread, "sd": max(map_spread["sd"], all_spread["sd"])}
    prior = map_spread["mean"] + tendency
    weight = _reliability(map_spread, on_map[1]) if on_map else 0.0
    value = prior + weight * (on_map[0] - prior) if on_map else prior
    excess = value - map_spread["mean"]
    z = excess / map_spread["sd"]
    if on_map is None:
        return Estimate(z, excess, "all_maps", *across, None)
    here = (on_map[0], map_spread["mean"])
    if weight >= MIN_RELIABILITY:
        return Estimate(z, excess, "map", *here, None)
    if (on_map[0] - map_spread["mean"]) * excess < 0:
        # The tendency says one thing and this Map the other: say neither.
        return None
    return Estimate(z, excess, "all_maps", *here, across)


def _judge(
    m: Measure,
    on_map: list[Tally],
    everywhere: list[Tally],
    spreads: tuple[dict | None, dict | None],
    h2h: set[int],
    map_name: str,
) -> dict | None:
    """A Strength or a Weakness of one Measure on one Side of this Map, or None."""
    here, there = read(m, on_map), read(m, everywhere)
    est = estimate(
        (here.value, here.of) if here else None,
        (there.value, there.of) if there else None,
        (spreads[0] or {}).get(m.key),
        (spreads[1] or {}).get(m.key),
    )
    if est is None:
        return None
    score = est.z if m.good_high else -est.z
    if score >= STRENGTH_Z and m.says in ("both", "strength"):
        good = True
    elif score <= -STRENGTH_Z and m.says in ("both", "weakness"):
        good = False
    else:
        return None
    # The Rounds behind it come from this Map when it has enough of them, so the
    # Replay links stay on the Map being prepared; else from all Maps.
    found = [
        (got, part, events)
        for got, part in ((here, on_map), (there, everywhere))
        if got and len(events := got.hits if good else got.misses) >= MIN_HABIT_ROUNDS
    ]
    if not found:
        return None
    got, tallies, events = found[0]
    if m.kind == "rate":
        per_half = got.of / max(1, sum(len(t.rounds) for t in tallies)) * HALF
        weight = abs(est.excess) * per_half * got.per_event
    else:
        weight = abs(est.excess) / (PER_ROUNDS / HALF) * got.per_event
    # Who died untraded is mostly who died: a trade line names nobody.
    players = [] if m.key == "trade" else Counter(e[2] for e in events if e[2]).most_common(3)
    # Spots only mean something on their own Map, whatever scope the number came from.
    spots = Counter(e[4] for e in events if e[4] and e[0].map == map_name)
    unit = "үхэл" if m.key == "trade" else ""
    return {
        "key": m.key,
        "kind": m.kind,
        "good": good,
        "scope": est.scope,
        "value": round(est.value, 4),
        "mean": round(est.mean, 4),
        "everywhere": _pair(est.everywhere),
        "z": round(est.z, 2),
        "of": got.of,
        "weight": round(weight, 3),
        "players": players,
        "spots": [(s, c) for s, c in spots.most_common(3) if c >= 2],
        "evidence": _evidence(events, got.of, h2h, unit),
    }


def _pair(values: tuple[float, float] | None) -> dict | None:
    return None if values is None else {"value": round(values[0], 4), "mean": round(values[1], 4)}


def _sides(team_id: int, map_name: str, side: str) -> tuple[list[Tally], list[Tally]]:
    everywhere = [t for t in data().by_team.get(team_id, []) if t.side == side]
    return [t for t in everywhere if t.map == map_name], everywhere


def team_lines(team: Team, map_name: str, h2h: set[int]) -> list[dict]:
    """The Team's Strengths and Weaknesses on each Side of this Map (see :class:`Estimate`)."""
    d = data()
    out = []
    for side in SIDES:
        on_map, everywhere = _sides(team.id, map_name, side)
        spreads = (d.pools.get((map_name, side)), d.pools.get((None, side)))
        for m in MEASURES:
            if side in m.sides:
                line = _judge(m, on_map, everywhere, spreads, h2h, map_name)
                if line:
                    out.append({**line, "side": side})
    return out


def score(team: Team, key: str, map_name: str, side: str) -> float | None:
    """The Team's z on one Measure on this Map, signed so that above 0 is good for
    them; None when it can't be told."""
    m = BY_KEY.get(key)
    if m is None or side not in m.sides:
        return None
    d = data()
    on_map, everywhere = _sides(team.id, map_name, side)
    here, there = read(m, on_map), read(m, everywhere)
    est = estimate(
        (here.value, here.of) if here else None,
        (there.value, there.of) if there else None,
        d.pools.get((map_name, side), {}).get(key),
        d.pools.get((None, side), {}).get(key),
    )
    if est is None:
        return None
    return est.z if m.good_high else -est.z


def _players_of(team: Team) -> list[tuple[Player, int]]:
    """The Team's Lineup, each Player with the Team their numbers come from."""
    from app.services import lineup

    ids = lineup.fielded(team)
    newcomers = {p.id for p in lineup.newcomers(team)}
    players = list(db().scalars(select(Player).where(Player.id.in_(list(ids))))) if ids else []
    out = []
    for p in players:
        source = team.id
        if p.id in newcomers:
            found = lineup.elsewhere(p)
            if found is None:
                continue
            source = found[0].id
        out.append((p, source))
    return out


def player_lines(team: Team, map_name: str, h2h: set[int]) -> list[dict]:
    """Each Lineup Player's Swing per Round on each Side, where it stands out."""
    d = data()
    out = []
    for player, source in _players_of(team):
        sid = str(player.steamid)
        for side in SIDES:
            on_map, everywhere = _sides(source, map_name, side)
            here = [(t, n, s) for t in on_map if sid in t.players for n, s in t.players[sid]]
            there = [(t, n, s) for t in everywhere if sid in t.players for n, s in t.players[sid]]
            line = _judge_player(
                sid, here, there, d.player_pools.get((map_name, side)),
                d.player_pools.get((None, side)), h2h, map_name,
            )  # fmt: skip
            if line:
                out.append({**line, "side": side, "player": player.name, "sid": sid,
                            "elsewhere": source != team.id})  # fmt: skip
    return out


def _mean(rows: list[tuple], need: int) -> tuple[float, int] | None:
    return (sum(s for *_r, s in rows) / len(rows), len(rows)) if len(rows) >= need else None


def _judge_player(sid, here, there, map_spread, all_spread, h2h, map_name) -> dict | None:
    est = estimate(
        _mean(here, PLAYER_MAP_ROUNDS), _mean(there, PLAYER_ALL_ROUNDS), map_spread, all_spread
    )
    if est is None or abs(est.z) < STRENGTH_Z:
        return None
    good = est.z > 0
    for rows in (here if len(here) >= PLAYER_MAP_ROUNDS else [], there):
        rounds = [(t, n, sid, s, "") for t, n, s in rows
                  if (s >= PLAYER_ROUND_SWING if good else s <= -PLAYER_ROUND_SWING)]  # fmt: skip
        if len(rounds) >= MIN_HABIT_ROUNDS:
            break
    else:
        return None
    rounds.sort(key=lambda e: -abs(e[3]))
    # What they do in those Rounds: their most frequent Findings of the matching kind.
    codes: Counter = Counter()
    spots: Counter = Counter()
    for t in {id(t): t for t, _n, _s in rows}.values():
        for code, found in t.codes.items():
            if (code in GOOD_FINDINGS) != good:
                continue
            for _n, _t, who, _sw, spot in found:
                if who == sid:
                    codes[code] += 1
                    if spot and t.map == map_name:
                        spots[spot] += 1
    return {
        "key": "player",
        "kind": "player",
        "good": good,
        "scope": est.scope,
        "value": round(est.value, 4),
        "mean": round(est.mean, 4),
        "everywhere": _pair(est.everywhere),
        "z": round(est.z, 2),
        "of": len(rows),
        "weight": round(abs(est.excess) * HALF, 3),
        "codes": codes.most_common(3),
        "spots": [(s, c) for s, c in spots.most_common(2) if c >= 2],
        "evidence": _evidence(rounds, len(rows), h2h),
    }


def player_note(team: Team, sid: str, map_name: str, side: str) -> dict | None:
    """A Player's Review on one Side of a Map (else of all Maps): what a habit
    line about them can add. None without enough Rounds."""
    d = data()
    tallies = [t for t in d.by_team.get(team.id, []) if sid in t.players and t.side == side]
    for scope, part in (("map", [t for t in tallies if t.map == map_name]), ("all_maps", tallies)):
        rows = [s for t in part for _n, s in t.players[sid]]
        if len(rows) < MIN_HABIT_ROUNDS * 3:
            continue
        codes: Counter = Counter()
        for t in part:
            for code, found in t.codes.items():
                codes[code] += sum(1 for e in found if e[2] == sid)
        return {
            "scope": scope,
            "rounds": len(rows),
            "swing": round(sum(rows) / len(rows), 4),
            "good": [(c, n) for c, n in codes.most_common() if c in GOOD_FINDINGS][:2],
            "bad": [(c, n) for c, n in codes.most_common() if c not in GOOD_FINDINGS][:2],
        }
    return None


def place_note(team: Team, map_name: str, side: str, inside) -> dict | None:
    """The Team's Findings on one Side of a Map whose Spot is inside a place
    (``inside(spot)``): what a habit line about that place can add."""
    d = data()
    codes: Counter = Counter()
    rounds = set()
    for t in d.by_team.get(team.id, []):
        if t.side != side or t.map != map_name:
            continue
        for code, found in t.codes.items():
            for n, _t, _sid, _sw, spot in found:
                if spot and inside(spot):
                    codes[code] += 1
                    rounds.add((t.mm, n))
    if sum(codes.values()) < MIN_HABIT_ROUNDS:
        return None
    return {
        "good": [(c, n) for c, n in codes.most_common() if c in GOOD_FINDINGS][:2],
        "bad": [(c, n) for c, n in codes.most_common() if c not in GOOD_FINDINGS][:2],
        "rounds": len(rounds),
    }


# --------------------------------------------------------- how much there is ---
def state(teams: list[Team]) -> dict:
    """For these Teams: their parsed Match Maps, how many have a current Review,
    how many wait for one, how many carry Sightings, and how many name no Teams."""
    d = data()
    out = {}
    for team in teams:
        maps = {m.id for m in mapstrategy.maps_in_window(team)}
        reviewed = {t.mm for t in d.by_team.get(team.id, [])}
        sighted = {t.mm for t in d.by_team.get(team.id, []) if t.sight}
        waiting = len(maps & set(stale_ids()))
        out[team.id] = {
            "maps": len(maps),
            "reviewed": len(reviewed & maps),
            "waiting": waiting,
            "sightings": len(sighted & maps),
            "untagged": d.untagged.get(team.id, 0),
        }
    return out


def stale_ids() -> list[int]:
    """Match Maps with Tick Data whose Review is missing or not at the current version."""

    def compute():
        return list(
            db().scalars(
                select(TickDataset.match_map_id)
                .outerjoin(MatchMapReview, MatchMapReview.match_map_id == TickDataset.match_map_id)
                .where(or_(MatchMapReview.id.is_(None), MatchMapReview.version != review.version()))
                .order_by(TickDataset.match_map_id)
            )
        )

    return memo(("review_stale",), compute)


def request_refresh(*, force: bool = False) -> bool:
    """Have the worker rebuild the stale Reviews, unless it already is. Never raises."""
    from app.cache import get_cache

    try:
        if not force and not stale_ids():
            return False
        cache = get_cache()
        if force:
            cache.delete(REFRESH_LOCK)
        if not cache.set(REFRESH_LOCK, "1", nx=True, ex=REFRESH_LOCK_SECONDS):
            return False
    except (RedisError, RuntimeError):
        logger.warning("could not request a Review refresh")
        return False
    try:
        from app.tasks import refresh_reviews

        refresh_reviews.delay()
    except Exception:
        logger.exception("could not queue the Review refresh")
        release_refresh()
        return False
    return True


def release_refresh(hold: int = 0) -> None:
    """End a refresh. ``hold`` keeps the lock that many seconds more, so Reviews
    that failed to build are not retried on every Game Plan opened."""
    from app.cache import get_cache

    try:
        if hold:
            get_cache().set(REFRESH_LOCK, "1", ex=hold)
        else:
            get_cache().delete(REFRESH_LOCK)
    except RedisError:
        logger.warning("could not release the Review refresh lock")
