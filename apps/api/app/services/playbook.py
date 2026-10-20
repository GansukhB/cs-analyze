"""The Playbook: how to play one Map of a Fixture, read off what both Teams did.

CONTEXT.md defines the terms: Playbook, Evidence strength, Setup, Set play, Buy
type, Self-scout. This module finds the habits and returns them structured, each
with its evidence; :mod:`app.services.mn` words them and adds the counter. Like
the other game-plan services it takes no session: bind one with ``dbctx.using``.

The opponent's habits are read from every parsed Match Map of theirs,
Head-to-head included, and each piece of evidence says how many of its Rounds
were Head-to-head. A habit is named only once it repeats in
:data:`MIN_HABIT_ROUNDS` Rounds on one Side; below that a section still lists
what happened, but never calls it a habit.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

from sqlalchemy import func, or_, select

from app.models import (
    BombEvent,
    BombEventType,
    BuyType,
    GameMap,
    GrenadeThrow,
    KillEvent,
    MatchMap,
    Player,
    PlayerMapDuel,
    PlayerRound,
    Round,
    RoundSnapshot,
    SnapshotMoment,
    Team,
)
from app.services import lineup, mapstrategy, stats
from app.services.analysis_store import PISTOL_ROUNDS
from app.services.dbctx import db, memo

# CONTEXT.md, Evidence strength.
MIN_HABIT_ROUNDS = 4
MEDIUM_FROM_MAPS = 2
STRONG_FROM_MAPS = 4
# Round references kept per habit, for the Replay links.
MAX_REFS = 8

# Past the round count, the share of the Side's rounds a habit must also hold:
# a Setup seen in 7 of 61 rounds repeats, but it is not what they do.
SETUP_SHARE = 0.3
STACK_SHARE = 0.25
OPENING_SHARE = 0.2
# A site is their habit once this share of their plants goes there.
SITE_SHARE = 0.6
# A player's Setup spot is a habit once they stand there this often.
SPOT_SHARE = 0.5
# Three on one site at the Setup is a stack.
STACK_FROM = 3
# A point leans to a site when it is this much closer to it than to the other.
LEAN_RATIO = 0.6
# How much closer to one site, in players, a Setup must be before the other is soft.
SOFT_SITE_GAP = 0.8
# Retakes: called weak at or under, strong at or over (percent won). Only when
# the Map's Pool is too small to judge against (see `_pool_judged`).
RETAKE_WEAK_PCT = 35
RETAKE_STRONG_PCT = 60
# The Pool a site or retake habit is judged against: the other Teams on this
# Map with at least this many plants, and at least this many of those Teams.
POOL_MIN_EVENTS = 4
POOL_MIN_TEAMS = 3
# The least true spread between Teams assumed for each (stats.MIN_SPREAD): which
# site a Team goes to differs more from Team to Team than how often it retakes.
SITE_MIN_SPREAD = 0.12
RETAKE_MIN_SPREAD = 0.08
# A habit is said when the chance it points the wrong way is under the first;
# under the second it is shown as a lean, a weaker line worth a look.
HABIT_LFSR = stats.LFSR
LEAN_LFSR = 0.20
# The Set play window and how far apart in time the same grenade may land.
SET_PLAY_WINDOW = 40.0
SET_PLAY_SPREAD = 5.0
SET_PLAY_MAX = 3
SET_PLAY_GRENADES = ("smoke", "inferno")
# Economy habits: they force when the money is short this often, or save.
FORCE_SHARE = 0.5
SAVE_SHARE = 0.7
# A player is their team's AWP when it is the gun they carry in this share of
# the rounds they had one (eco rounds would otherwise hide every AWPer).
AWP = "AWP"
AWP_SHARE = 0.4

LEANS = ("A", "mid", "B")


@dataclass(frozen=True)
class _Round:
    id: int
    match_map_id: int
    match_id: int
    map_number: int
    number: int
    tickrate: int
    freeze_end: int
    end: int
    plant: int | None
    site: str
    winner: int | None
    ct_team: int | None
    t_team: int | None
    ct_buy: str
    t_buy: str
    h2h: bool

    def side_of(self, team_id: int) -> str:
        return "ct" if self.ct_team == team_id else "t" if self.t_team == team_id else ""

    def team_on(self, side: str) -> int | None:
        return self.ct_team if side == "ct" else self.t_team

    def buy(self, team_id: int) -> str:
        return self.ct_buy if self.ct_team == team_id else self.t_buy

    def secs(self, tick: int) -> float:
        return (tick - self.freeze_end) / (self.tickrate or 64)

    @property
    def ref(self) -> dict:
        return {"match": self.match_id, "map": self.map_number, "round": self.number}


def strength(maps: int) -> str:
    if maps >= STRONG_FROM_MAPS:
        return "strong"
    return "medium" if maps >= MEDIUM_FROM_MAPS else "weak"


def _evidence(rounds: Iterable[_Round], of: int) -> dict:
    rounds = list(rounds)
    maps = {r.match_map_id for r in rounds}
    return {
        "n": len(rounds),
        "of": of,
        "maps": len(maps),
        "h2h": sum(1 for r in rounds if r.h2h),
        "strength": strength(len(maps)),
        "refs": [r.ref for r in rounds[:MAX_REFS]],
    }


# ------------------------------------------------------------------ loading --
def _team_rounds(team: Team, other: Team, map_name: str | None) -> list[_Round]:
    """Every parsed Round the team played, on one Map or on all of them."""

    def compute():
        maps = [
            m
            for m in mapstrategy.maps_in_window(team)
            if map_name is None or (m.game_map and m.game_map.name == map_name)
        ]
        if not maps:
            return []
        # The current five's era (TM-3): habits of a roster that is gone mislead.
        maps, _narrowed = mapstrategy.era_maps(team, maps)
        h2h = {m.id for m in mapstrategy.maps_in_window(team, opponent=other)}
        info = {m.id: m for m in maps}
        rows = (
            db()
            .execute(
                select(
                    Round.id,
                    Round.match_map_id,
                    Round.number,
                    Round.freeze_end_tick,
                    Round.end_tick,
                    Round.bomb_plant_tick,
                    Round.bomb_site,
                    Round.winner_team_id,
                    Round.ct_team_id,
                    Round.t_team_id,
                    Round.ct_buy,
                    Round.t_buy,
                )
                .where(Round.match_map_id.in_(list(info)))
                .order_by(Round.match_map_id, Round.number)
            )
            .all()
        )
        return [
            _Round(
                id=r.id,
                match_map_id=r.match_map_id,
                match_id=info[r.match_map_id].match_id,
                map_number=info[r.match_map_id].map_number,
                number=r.number,
                tickrate=info[r.match_map_id].tickrate or 64,
                freeze_end=r.freeze_end_tick,
                end=r.end_tick,
                plant=r.bomb_plant_tick,
                site=r.bomb_site,
                winner=r.winner_team_id,
                ct_team=r.ct_team_id,
                t_team=r.t_team_id,
                ct_buy=r.ct_buy,
                t_buy=r.t_buy,
                h2h=r.match_map_id in h2h,
            )
            for r in rows
        ]

    return memo(("pb_rounds", team.id, other.id, map_name), compute)


@dataclass
class _Detail:
    """What happened inside a set of Rounds, keyed by round id."""

    setup: dict[int, list]  # (player_id, side, place, x, y, z)
    plant: dict[int, list]
    grenades: dict[int, list]  # (type, side, start_tick, place)
    first_kill: dict[int, tuple]  # (attacker_id, victim_id, attacker_side, places..., tick)
    names: dict[int, str]


def _detail(rounds: list[_Round]) -> _Detail:
    ids = [r.id for r in rounds]
    out = _Detail(defaultdict(list), defaultdict(list), defaultdict(list), {}, {})
    if not ids:
        return out
    session = db()
    for row in session.execute(
        select(
            RoundSnapshot.round_id,
            RoundSnapshot.moment,
            RoundSnapshot.player_id,
            RoundSnapshot.side,
            RoundSnapshot.place,
            RoundSnapshot.x,
            RoundSnapshot.y,
            RoundSnapshot.z,
        ).where(RoundSnapshot.round_id.in_(ids))
    ):
        target = out.setup if row.moment == SnapshotMoment.SETUP else out.plant
        target[row.round_id].append((row.player_id, row.side, row.place, row.x, row.y, row.z))
    for row in session.execute(
        select(
            GrenadeThrow.round_id,
            GrenadeThrow.type,
            GrenadeThrow.thrower_side,
            GrenadeThrow.start_tick,
            GrenadeThrow.place,
        ).where(
            GrenadeThrow.round_id.in_(ids),
            GrenadeThrow.type.in_(SET_PLAY_GRENADES),
            GrenadeThrow.start_tick.is_not(None),
            GrenadeThrow.place != "",
        )
    ):
        out.grenades[row.round_id].append((row.type, row.thrower_side, row.start_tick, row.place))
    first = (
        select(KillEvent.round_id, func.min(KillEvent.tick).label("tick"))
        .where(KillEvent.round_id.in_(ids))
        .group_by(KillEvent.round_id)
        .subquery()
    )
    for row in session.execute(
        select(
            KillEvent.round_id,
            KillEvent.attacker_id,
            KillEvent.victim_id,
            KillEvent.attacker_side,
            KillEvent.attacker_place,
            KillEvent.victim_place,
            KillEvent.tick,
        ).join(first, (first.c.round_id == KillEvent.round_id) & (first.c.tick == KillEvent.tick))
    ):
        out.first_kill.setdefault(row.round_id, row)
    players = {p[0] for spots in out.setup.values() for p in spots}
    players |= {k.attacker_id for k in out.first_kill.values() if k.attacker_id}
    players |= {k.victim_id for k in out.first_kill.values()}
    if players:
        out.names = dict(
            session.execute(select(Player.id, Player.name).where(Player.id.in_(players))).all()
        )
    return out


def site_centroids(map_name: str) -> dict[str, tuple]:
    """Where each bombsite's plants land on this Map, across every parsed Team."""

    def compute():
        rows = (
            db()
            .execute(
                select(
                    BombEvent.bombsite,
                    func.avg(BombEvent.x),
                    func.avg(BombEvent.y),
                    func.avg(BombEvent.z),
                )
                .join(Round, Round.id == BombEvent.round_id)
                .join(MatchMap, MatchMap.id == Round.match_map_id)
                .join(GameMap, GameMap.id == MatchMap.game_map_id)
                .where(
                    GameMap.name == map_name,
                    BombEvent.event == BombEventType.PLANT,
                    BombEvent.bombsite.in_(("A", "B")),
                    BombEvent.x.is_not(None),
                )
                .group_by(BombEvent.bombsite)
            )
            .all()
        )
        return {site: (float(x), float(y), float(z or 0)) for site, x, y, z in rows}

    return memo(("pb_sites", map_name), compute)


def lean(point: tuple, sites: dict[str, tuple]) -> str:
    """``A``, ``B`` or ``mid`` for a position, ``""`` while a site's plants are unknown."""
    if "A" not in sites or "B" not in sites or None in point:
        return ""

    def dist(site):
        sx, sy, sz = sites[site]
        x, y, z = point
        return math.sqrt((x - sx) ** 2 + (y - sy) ** 2 + ((z - sz) * 2) ** 2)

    to_a, to_b = dist("A"), dist("B")
    if to_a < to_b * LEAN_RATIO:
        return "A"
    if to_b < to_a * LEAN_RATIO:
        return "B"
    return "mid"


# ------------------------------------------------------------- habits ------
def _side_rounds(team_id: int, rounds: list[_Round], side: str) -> list[_Round]:
    return [r for r in rounds if r.side_of(team_id) == side]


def _setups(team_id, rounds, side, detail, sites) -> dict[int, dict]:
    """``{round_id: {"spots": [(player, place, lean)], "count": {lean: n}}}``."""
    out = {}
    for r in rounds:
        spots = [
            (player, place, lean((x, y, z), sites))
            for player, s, place, x, y, z in detail.setup.get(r.id, ())
            if s == side
        ]
        if spots:
            count = Counter(lean_ for _p, _place, lean_ in spots)
            out[r.id] = {"spots": spots, "count": count}
    return out


def setup_habits(team_id, rounds, side, detail, sites) -> list[dict]:
    by_round = {r.id: r for r in rounds}
    setups = _setups(team_id, rounds, side, detail, sites)
    out = []
    if sites:
        full = {rid: s for rid, s in setups.items() if sum(s["count"].values()) >= 4}
        patterns = Counter(
            tuple(s["count"].get(lean_, 0) for lean_ in LEANS) for s in full.values()
        )
        if patterns:
            pattern, n = patterns.most_common(1)[0]
            if n >= MIN_HABIT_ROUNDS and n / len(full) >= SETUP_SHARE:
                hit = [
                    by_round[rid]
                    for rid, s in full.items()
                    if tuple(s["count"].get(lean_, 0) for lean_ in LEANS) == pattern
                ]
                out.append(
                    {
                        "kind": "setup",
                        "side": side,
                        "pattern": dict(zip(LEANS, pattern, strict=True)),
                        "evidence": _evidence(hit, len(full)),
                    }
                )
        for site in ("A", "B"):
            stacked = [
                by_round[rid] for rid, s in full.items() if s["count"].get(site, 0) >= STACK_FROM
            ]
            if len(stacked) >= MIN_HABIT_ROUNDS and len(stacked) / len(full) >= STACK_SHARE:
                out.append(
                    {
                        "kind": "stack",
                        "side": side,
                        "site": site,
                        "evidence": _evidence(stacked, len(full)),
                    }
                )
        if side == "ct" and len(full) >= MIN_HABIT_ROUNDS:
            avg = {
                site: statistics.mean(s["count"].get(site, 0) for s in full.values())
                for site in ("A", "B")
            }
            soft, hard = sorted(("A", "B"), key=lambda site: avg[site])
            if avg[hard] - avg[soft] >= SOFT_SITE_GAP:
                out.append(
                    {
                        "kind": "soft_site",
                        "side": side,
                        "site": soft,
                        "avg": {k: round(v, 1) for k, v in avg.items()},
                        "evidence": _evidence([by_round[rid] for rid in full], len(full)),
                    }
                )
    # Each player's usual Setup spot.
    seen: dict[int, list] = defaultdict(list)
    for rid, s in setups.items():
        for player, place, _lean in s["spots"]:
            if place:
                seen[player].append((by_round[rid], place))
    for player, spots in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        place, n = Counter(p for _r, p in spots).most_common(1)[0]
        if n >= MIN_HABIT_ROUNDS and n / len(spots) >= SPOT_SHARE:
            out.append(
                {
                    "kind": "spot",
                    "side": side,
                    "player": detail.names.get(player, "?"),
                    "player_id": player,
                    "place": place,
                    "evidence": _evidence([r for r, p in spots if p == place], len(spots)),
                }
            )
    return out


def map_pools(map_name: str | None) -> dict:
    """Every Team's plant sites (as T) and retakes (as CT) on this Map: what a
    site or retake habit is judged against (docs/plans TM-4).

    ``{"sites": {team: (A plants, plants, maps)}, "retakes": {team: (won, faced, maps)}}``.
    """

    def compute():
        if not map_name:
            return {"sites": {}, "retakes": {}}
        rows = (
            db()
            .execute(
                select(
                    Round.ct_team_id,
                    Round.t_team_id,
                    Round.winner_team_id,
                    Round.bomb_site,
                    Round.match_map_id,
                )  # fmt: skip
                .join(MatchMap, MatchMap.id == Round.match_map_id)
                .join(GameMap, GameMap.id == MatchMap.game_map_id)
                .where(GameMap.name == map_name, Round.bomb_plant_tick.is_not(None))
            )
            .all()
        )
        sites: dict[int, list] = defaultdict(lambda: [0, 0, set()])
        retakes: dict[int, list] = defaultdict(lambda: [0, 0, set()])
        for ct, t, winner, site, match_map_id in rows:
            if t is not None and site in ("A", "B"):
                sites[t][0] += site == "A"
                sites[t][1] += 1
                sites[t][2].add(match_map_id)
            if ct is not None:
                retakes[ct][0] += winner == ct
                retakes[ct][1] += 1
                retakes[ct][2].add(match_map_id)
        freeze = lambda d: {k: (x, n, len(m)) for k, (x, n, m) in d.items()}  # noqa: E731
        return {"sites": freeze(sites), "retakes": freeze(retakes)}

    return memo(("playbook_pools", map_name), compute)


def _effective(x: float, n: float, maps: int) -> tuple[float, float]:
    """``x`` of ``n`` events over ``maps`` Match Maps, counted as independent ones."""
    n_eff = stats.effective_n(n, n / max(maps, 1))
    return (x * n_eff / n if n else 0.0), n_eff


def _pool_judged(
    pool: dict, team_id: int, x: int, n: int, maps: int, min_spread: float
) -> stats.Shrunk | None:
    """This Team's rate pulled toward the other Teams' on the Map, or None when
    too few of them have enough plants to say what the Pool does."""
    others = [
        _effective(px, pn, pm)
        for team, (px, pn, pm) in pool.items()
        if team != team_id and pn >= POOL_MIN_EVENTS
    ]
    prior = stats.beta_prior(others, min_spread) if len(others) >= POOL_MIN_TEAMS else None
    if prior is None:
        return None
    return stats.shrink(*_effective(x, n, maps), prior)


def plant_habits(team_id, rounds, pools: dict | None = None) -> list[dict]:
    """Their T side: where the bomb goes, how fast, and how often it is a rush."""
    out = []
    planted = [r for r in rounds if r.plant]
    if not planted:
        return out
    sites = Counter(r.site for r in planted if r.site)
    on_sites = [r for r in planted if r.site in ("A", "B")]
    judged = None
    if pools is not None and len(on_sites) >= MIN_HABIT_ROUNDS:
        maps = len({r.match_map_id for r in on_sites})
        a = sum(1 for r in on_sites if r.site == "A")
        judged = _pool_judged(pools["sites"], team_id, a, len(on_sites), maps, SITE_MIN_SPREAD)
    if judged is not None:
        # Against the Pool: a site is theirs only when they go there clearly
        # more than Teams on this Map do (eight plants 6-2 is often chance).
        if judged.clear(LEAN_LFSR):
            site = "A" if judged.above else "B"
            pool_share = judged.pool if site == "A" else 1 - judged.pool
            out.append(
                {
                    "kind": "site",
                    "side": "t",
                    "site": site,
                    "rounds": len(rounds),
                    "pool_pct": round(100 * pool_share),
                    "lean": not judged.clear(HABIT_LFSR),
                    "evidence": _evidence([r for r in planted if r.site == site], len(planted)),
                }
            )
    elif sites:
        site, n = sites.most_common(1)[0]
        if n >= MIN_HABIT_ROUNDS and n / len(planted) >= SITE_SHARE:
            out.append(
                {
                    "kind": "site",
                    "side": "t",
                    "site": site,
                    "rounds": len(rounds),
                    "evidence": _evidence([r for r in planted if r.site == site], len(planted)),
                }
            )
    if len(planted) >= MIN_HABIT_ROUNDS:
        secs = [r.secs(r.plant) for r in planted]
        out.append(
            {
                "kind": "plant_time",
                "side": "t",
                "median": round(statistics.median(secs), 1),
                "evidence": _evidence(planted, len(rounds)),
            }
        )
    rushes = [r for r in planted if r.secs(r.plant) <= mapstrategy.RUSH_PLANT_SEC]
    if len(rushes) >= MIN_HABIT_ROUNDS:
        out.append(
            {
                "kind": "rush",
                "side": "t",
                "sites": dict(Counter(r.site for r in rushes)),
                "evidence": _evidence(rushes, len(rounds)),
            }
        )
    return out


def defence_habits(team_id, rounds, detail, sites, pools: dict | None = None) -> list[dict]:
    """Their CT side once the bomb is down: who is there, and do they get it back."""
    out = []
    faced = [r for r in rounds if r.plant]
    if len(faced) >= MIN_HABIT_ROUNDS:
        won = [r for r in faced if r.winner == team_id]
        pct = round(100 * len(won) / len(faced))
        maps = len({r.match_map_id for r in faced})
        judged = (
            _pool_judged(pools["retakes"], team_id, len(won), len(faced), maps, RETAKE_MIN_SPREAD)
            if pools is not None
            else None
        )
        # Most Teams lose most retakes; weak or strong is said against the Pool
        # on this Map, and only past chance. With no Pool, the fixed bars.
        if judged is not None:
            says = judged.clear(LEAN_LFSR)
        else:
            says = pct <= RETAKE_WEAK_PCT or pct >= RETAKE_STRONG_PCT
        if says:
            habit = {
                "kind": "retake",
                "side": "ct",
                "won": len(won),
                "faced": len(faced),
                "pct": pct,
                "evidence": _evidence(faced, len(rounds)),
            }
            if judged is not None:
                habit["pool_pct"] = round(100 * judged.pool)
                habit["weak"] = not judged.above
                habit["lean"] = not judged.clear(HABIT_LFSR)
            out.append(habit)
    if sites:
        for site in ("A", "B"):
            at = [r for r in faced if r.site == site]
            counts = []
            for r in at:
                spots = [
                    (x, y, z) for _p, s, _place, x, y, z in detail.plant.get(r.id, ()) if s == "ct"
                ]
                if spots:
                    counts.append((sum(1 for p in spots if lean(p, sites) == site), len(spots)))
            if len(counts) >= MIN_HABIT_ROUNDS:
                out.append(
                    {
                        "kind": "at_plant",
                        "side": "ct",
                        "site": site,
                        "on_site": round(statistics.mean(c[0] for c in counts), 1),
                        "alive": round(statistics.mean(c[1] for c in counts), 1),
                        "evidence": _evidence(at, len(faced)),
                    }
                )
    return out


def opening_habits(team_id, rounds, side, detail) -> list[dict]:
    """Where the Round's first duel involves them, and who wins it."""
    places: dict[str, list] = defaultdict(list)
    for r in rounds:
        k = detail.first_kill.get(r.id)
        if k is None:
            continue
        theirs_won = k.attacker_side == side
        place = k.attacker_place if theirs_won else k.victim_place
        if place:
            places[place].append((r, theirs_won))
    out = []
    for place, hits in sorted(places.items(), key=lambda kv: -len(kv[1]))[:2]:
        if len(hits) >= MIN_HABIT_ROUNDS and len(hits) / len(rounds) >= OPENING_SHARE:
            out.append(
                {
                    "kind": "opening",
                    "side": side,
                    "place": place,
                    "won": sum(1 for _r, w in hits if w),
                    "evidence": _evidence([r for r, _w in hits], len(rounds)),
                }
            )
    return out


def set_plays(team_id, rounds, side, detail) -> list[dict]:
    """Grenade patterns they repeat early in the Round (CONTEXT.md: Set play).

    A Round's tokens are its (grenade, Callout) pairs that land inside
    :data:`SET_PLAY_WINDOW`; the earliest one counts when a Callout gets two.
    Frequent combinations of two or more tokens are grown Apriori-style, then a
    Round only supports one if every token lands within :data:`SET_PLAY_SPREAD`
    of that token's median time across the supporting Rounds. Variants of one
    execute are one Set play: the most supported combination is kept, and any
    other that contains it or is contained in it is dropped.
    """
    times: dict[int, dict[tuple, float]] = {}
    for r in rounds:
        tokens: dict[tuple, float] = {}
        for kind, s, start, place in detail.grenades.get(r.id, ()):
            at = r.secs(start)
            if s == side and 0 <= at <= SET_PLAY_WINDOW:
                key = (kind, place)
                tokens[key] = min(at, tokens.get(key, at))
        if tokens:
            times[r.id] = tokens
    by_round = {r.id: r for r in rounds}
    common = {
        t
        for t, n in Counter(t for ts in times.values() for t in ts).items()
        if n >= MIN_HABIT_ROUNDS
    }

    def support(items: tuple) -> tuple[list[int], dict]:
        rids = [rid for rid, ts in times.items() if all(i in ts for i in items)]
        medians = (
            {i: statistics.median(times[rid][i] for rid in rids) for i in items} if rids else {}
        )
        kept = [
            rid
            for rid in rids
            if all(abs(times[rid][i] - medians[i]) <= SET_PLAY_SPREAD for i in items)
        ]
        return kept, medians

    found: dict[tuple, list[int]] = {}
    level = [tuple(sorted(c)) for c in combinations(sorted(common), 2)]
    while level:
        nxt = set()
        for items in level:
            kept, _m = support(items)
            if len(kept) >= MIN_HABIT_ROUNDS:
                found[items] = kept
                for extra in common - set(items):
                    nxt.add(tuple(sorted((*items, extra))))
        level = sorted(nxt)
    ranked = sorted(found, key=lambda items: (-len(found[items]), -len(items), items))
    chosen: list[tuple] = []
    for items in ranked:
        if len(chosen) == SET_PLAY_MAX:
            break
        # A wider variant that most of the same rounds share says more: take it instead.
        wider = [
            o for o in found if set(items) < set(o) and len(found[o]) >= 0.8 * len(found[items])
        ]
        if wider:
            continue
        if not any(set(items) <= set(c) or set(c) <= set(items) for c in chosen):
            chosen.append(items)
    out = []
    for items in chosen:
        kept, medians = support(items)
        hit = [by_round[rid] for rid in kept]
        planted = Counter(r.site for r in hit if r.plant and r.site)
        top = planted.most_common(1)
        target = top[0][0] if top and top[0][1] / sum(planted.values()) >= SITE_SHARE else ""
        out.append(
            {
                "kind": "set_play",
                "side": side,
                "target": target,
                "grenades": sorted(
                    (
                        {"type": kind, "place": place, "at": round(medians[(kind, place)], 1)}
                        for kind, place in items
                    ),
                    key=lambda g: g["at"],
                ),
                "won": sum(1 for r in hit if r.winner == team_id),
                "planted": dict(planted),
                "evidence": _evidence(hit, len(rounds)),
            }
        )
    return out


def side_habits(
    team_id: int, rounds: list[_Round], side: str, detail: _Detail, sites, pools=None
) -> list:
    """Every habit of one Team on one Side of a Map."""
    mine = _side_rounds(team_id, rounds, side)
    out = setup_habits(team_id, mine, side, detail, sites)
    if side == "t":
        out += plant_habits(team_id, mine, pools)
    else:
        out += defence_habits(team_id, mine, detail, sites, pools)
    out += set_plays(team_id, mine, side, detail)
    out += opening_habits(team_id, mine, side, detail)
    return out


# --------------------------------------------------------- pistol & money --
def pistols(team_id: int, rounds: list[_Round], detail: _Detail, sites) -> list[dict]:
    """Every pistol round of theirs on this Map, and what they bought next."""
    by_key = {(r.match_map_id, r.number): r for r in rounds}
    out = []
    for r in rounds:
        if r.number not in PISTOL_ROUNDS:
            continue
        side = r.side_of(team_id)
        setup = _setups(team_id, [r], side, detail, sites).get(r.id)
        after = by_key.get((r.match_map_id, r.number + 1))
        out.append(
            {
                "ref": r.ref,
                "side": side,
                "won": r.winner == team_id,
                "h2h": r.h2h,
                "site": r.site if side == "t" and r.plant else "",
                "pattern": {k: setup["count"].get(k, 0) for k in LEANS}
                if setup and sites
                else None,
                "next_buy": after.buy(team_id) if after else "",
                "next_won": after.winner == team_id if after else None,
            }
        )
    return out


BEATEN_MIN_ROUNDS = 5  # Rounds against one answer before it is worth a line
BEATEN_PRIOR = 10.0  # pseudo-Rounds of their usual rate an answer's record is pulled toward
BEATEN_LINES = 3
BEATEN_MIN_GAP = 0.05  # the pulled rate must sit this far below their usual one


def beaten_by(team_id: int, rounds: list[_Round], detail: _Detail, sites) -> dict:
    """GP-6: what the Teams that beat them on this Map did. Their T Rounds by the
    CT Setup they ran into, their CT Rounds by where and how fast the bomb came;
    each answer's record against them, pulled toward their usual rate, worst first."""

    def judge(groups: dict, their_rounds: list[_Round], describe) -> list[dict]:
        if not their_rounds:
            return []
        usual = sum(r.winner == team_id for r in their_rounds) / len(their_rounds)
        out = []
        for key, hit in groups.items():
            if len(hit) < BEATEN_MIN_ROUNDS:
                continue
            won = sum(r.winner == team_id for r in hit)
            pulled = (won + BEATEN_PRIOR * usual) / (len(hit) + BEATEN_PRIOR)
            if pulled > usual - BEATEN_MIN_GAP:
                continue
            out.append(
                {
                    "answer": describe(key),
                    "their_won": won,
                    "rounds": len(hit),
                    "their_pct": round(100 * won / len(hit), 1),
                    "usual_pct": round(100 * usual, 1),
                    "pulled_pct": round(100 * pulled, 1),
                    "evidence": _evidence(hit, len(their_rounds)),
                }
            )
        out.sort(key=lambda x: x["pulled_pct"])
        return out[:BEATEN_LINES]

    their_t = [r for r in rounds if r.side_of(team_id) == "t" and r.number not in PISTOL_ROUNDS]
    their_ct = [r for r in rounds if r.side_of(team_id) == "ct" and r.number not in PISTOL_ROUNDS]
    setups: dict[tuple, list[_Round]] = defaultdict(list)
    if sites:
        # The CT side's spots in their T Rounds are their opponents'.
        found = _setups(team_id, their_t, "ct", detail, sites)
        by_id = {r.id: r for r in their_t}
        for rid, s in found.items():
            if sum(s["count"].values()) >= 4:
                setups[tuple(s["count"].get(lean_, 0) for lean_ in LEANS)].append(by_id[rid])
    attacks: dict[tuple, list[_Round]] = defaultdict(list)
    # Against the Rounds the bomb went down in: a plant is lost CT ground already.
    planted = [r for r in their_ct if r.plant is not None]
    for r in planted:
        tempo = "rush" if r.secs(r.plant) <= mapstrategy.RUSH_PLANT_SEC else "default"
        attacks[(r.site or "?", tempo)].append(r)
    return {
        "t": judge(setups, list(their_t), lambda k: {"setup": dict(zip(LEANS, k, strict=True))}),
        "ct": judge(attacks, planted, lambda k: {"site": k[0], "tempo": k[1]}),
    }


PREDICTABLE_SHARE = 0.5  # one first move in half the Rounds is something to anti-strat
PREDICTABLE_ROUNDS = 10


def _spread(counts: Counter) -> dict:
    """How varied a set of first moves is: its top one's share, and how many
    equally likely moves would be as unpredictable (exp of the entropy)."""
    n = sum(counts.values())
    if not n:
        return {"rounds": 0, "top": None, "top_share": None, "options": None, "predictable": False}
    top, k = counts.most_common(1)[0]
    entropy = -sum(c / n * math.log(c / n) for c in counts.values() if c)
    share = k / n
    return {
        "rounds": n,
        "top": top,
        "top_share": round(share, 3),
        "options": round(math.exp(entropy), 1),
        "predictable": n >= PREDICTABLE_ROUNDS and share >= PREDICTABLE_SHARE,
    }


def t_spread_pool(map_name: str | None) -> float | None:
    """The 75th percentile of every Team's T top-move share on this Map (GP-11):
    a Team is readable only past what most Teams are."""

    def compute():
        if not map_name:
            return None
        rows = db().execute(
            select(Round.t_team_id, Round.match_map_id, Round.bomb_site, Round.bomb_plant_tick,
                   Round.freeze_end_tick, MatchMap.tickrate, Round.number)
            .join(MatchMap, MatchMap.id == Round.match_map_id)
            .join(GameMap, GameMap.id == MatchMap.game_map_id)
            .where(GameMap.name == map_name, Round.bomb_plant_tick.is_not(None))
        ).all()  # fmt: skip
        by_team: dict[int, Counter] = defaultdict(Counter)
        for team, _mm, site, plant, freeze, rate, number in rows:
            if team is None or number in PISTOL_ROUNDS or freeze is None:
                continue
            secs = (plant - freeze) / (rate or 64)
            tempo = "rush" if secs <= mapstrategy.RUSH_PLANT_SEC else "default"
            by_team[team][(site or "?", tempo)] += 1
        shares = sorted(
            c.most_common(1)[0][1] / sum(c.values())
            for c in by_team.values()
            if sum(c.values()) >= PREDICTABLE_ROUNDS
        )
        if len(shares) < 3:
            return None
        return shares[int(0.75 * (len(shares) - 1))]

    return memo(("playbook_t_spread_pool", map_name), compute)


def predictability(
    team_id: int, rounds: list[_Round], detail: _Detail, sites, map_name: str | None = None
) -> dict:
    """GP-11: how readable our first moves are on this Map: CT Setups, and T
    rounds by where and how fast the bomb went down (official Matches only)."""
    ct_rounds = [r for r in rounds if r.side_of(team_id) == "ct"]
    full = [
        s for s in _setups(team_id, ct_rounds, "ct", detail, sites).values()
        if sum(s["count"].values()) >= 4
    ]  # fmt: skip
    ct = (
        Counter(tuple(s["count"].get(lean_, 0) for lean_ in LEANS) for s in full)
        if sites
        else Counter()
    )
    # Where and how fast the bomb went down; a Round with no plant is an outcome,
    # not a move, so it is left out.
    t = Counter()
    for r in rounds:
        if r.side_of(team_id) != "t" or r.number in PISTOL_ROUNDS or r.plant is None:
            continue
        tempo = "rush" if r.secs(r.plant) <= mapstrategy.RUSH_PLANT_SEC else "default"
        t[(r.site or "?", tempo)] += 1
    ct_spread, t_spread = _spread(ct), _spread(t)
    # A site lean most Teams have is no tell: T is readable only past the Map's p75.
    bar = t_spread_pool(map_name)
    if bar is not None and t_spread["top_share"] is not None:
        t_spread["pool_p75"] = round(bar, 3)
        t_spread["predictable"] = t_spread["predictable"] and t_spread["top_share"] > bar
    if ct_spread["top"] is not None:
        ct_spread["top"] = dict(zip(LEANS, ct_spread["top"], strict=True))
    if t_spread["top"] is not None:
        t_spread["top"] = {"site": t_spread["top"][0], "tempo": t_spread["top"][1]}
    return {"ct": ct_spread, "t": t_spread}


def _conversion_rows(rows) -> dict[int, dict]:
    """Per Team: pistols won, then the next two Rounds (GP-5). ``rows`` are
    ``(match_map_id, number, winner, ct, t)`` in Round order."""
    by_map: dict[int, dict[int, tuple]] = defaultdict(dict)
    for mm, number, winner, ct, t in rows:
        by_map[mm][number] = (winner, ct, t)
    out: dict[int, dict] = defaultdict(
        lambda: {"pistols": 0, "pistols_won": 0, "chances": 0, "converted": 0,
                 "breaks": 0, "broken": 0, "both": 0, "both_map_won": 0}
    )  # fmt: skip
    for rounds in by_map.values():
        teams = {x for _w, ct, t in rounds.values() for x in (ct, t) if x}
        wins = Counter(w for w, _ct, _t in rounds.values() if w)
        won_pistols: Counter = Counter()
        for pistol in PISTOL_ROUNDS:
            if pistol not in rounds:
                continue
            winner = rounds[pistol][0]
            nxt = [rounds.get(pistol + 1), rounds.get(pistol + 2)]
            for team in teams:
                row = out[team]
                row["pistols"] += 1
                if winner == team:
                    row["pistols_won"] += 1
                    won_pistols[team] += 1
                    if all(nxt):
                        row["chances"] += 1
                        row["converted"] += all(r[0] == team for r in nxt)
                elif all(nxt):
                    row["breaks"] += 1
                    row["broken"] += any(r[0] == team for r in nxt)
        for team in teams:
            if won_pistols[team] == len([p for p in PISTOL_ROUNDS if p in rounds]) == 2:
                out[team]["both"] += 1
                others = [wins[o] for o in teams if o != team]
                out[team]["both_map_won"] += int(bool(others) and wins[team] > max(others))
    return out


def conversion(team_id: int, rounds: list[_Round]) -> dict:
    """GP-5: this Team's pistols on the Map and what it made of them."""
    rows = [(r.match_map_id, r.number, r.winner, r.ct_team, r.t_team) for r in rounds]
    return dict(_conversion_rows(rows)[team_id])


def conversion_pool(map_name: str | None) -> dict:
    """GP-5's baseline: the same over every Team's Match Maps on this Map."""

    def compute():
        if not map_name:
            return {}
        rows = db().execute(
            select(Round.match_map_id, Round.number, Round.winner_team_id, Round.ct_team_id,
                   Round.t_team_id)
            .join(MatchMap, MatchMap.id == Round.match_map_id)
            .join(GameMap, GameMap.id == MatchMap.game_map_id)
            .where(GameMap.name == map_name)
            .order_by(Round.match_map_id, Round.number)
        ).all()  # fmt: skip
        total: Counter = Counter()
        for row in _conversion_rows(rows).values():
            total.update(row)
        return dict(total)

    return memo(("playbook_conversion_pool", map_name), compute)


def economy(team_id: int, rounds: list[_Round]) -> dict:
    """How they spend, over every Map: force or save when short, and after a lost pistol."""
    known = [r for r in rounds if r.buy(team_id) and r.number not in PISTOL_ROUNDS]
    if not known:
        return {"known": False, "habits": []}
    buys = Counter(r.buy(team_id) for r in known)
    won = Counter(r.buy(team_id) for r in known if r.winner == team_id)
    short = [r for r in known if r.buy(team_id) in (BuyType.ECO, BuyType.FORCE)]
    forced = [r for r in short if r.buy(team_id) == BuyType.FORCE]
    saved = [r for r in short if r.buy(team_id) == BuyType.ECO]
    habits = []
    if len(forced) >= MIN_HABIT_ROUNDS and len(forced) / len(short) >= FORCE_SHARE:
        habits.append(
            {
                "kind": "forces",
                "won": won[BuyType.FORCE],
                "saved": len(saved),
                "evidence": _evidence(forced, len(short)),
            }
        )
    elif len(saved) >= MIN_HABIT_ROUNDS and len(saved) / len(short) >= SAVE_SHARE:
        habits.append({"kind": "saves", "evidence": _evidence(saved, len(short))})
    by_key = {(r.match_map_id, r.number): r for r in rounds}
    after_loss = [
        nxt
        for r in rounds
        if r.number in PISTOL_ROUNDS
        and r.winner is not None
        and r.winner != team_id
        and (nxt := by_key.get((r.match_map_id, r.number + 1))) is not None
        and nxt.buy(team_id)
    ]
    if after_loss:
        top, n = Counter(r.buy(team_id) for r in after_loss).most_common(1)[0]
        if n >= MIN_HABIT_ROUNDS:
            habits.append(
                {
                    "kind": "after_pistol_loss",
                    "buy": top,
                    "evidence": _evidence(
                        [r for r in after_loss if r.buy(team_id) == top], len(after_loss)
                    ),
                }
            )
    return {
        "known": True,
        "rounds": len(known),
        "buys": {
            str(b): {"n": buys[b], "won": won[b]}
            for b in (BuyType.ECO, BuyType.FORCE, BuyType.FULL)
        },
        "after_pistol_loss": dict(Counter(r.buy(team_id) for r in after_loss)),
        "habits": habits,
    }


# ----------------------------------------------------------------- matchups --
def matchups(opponent: Team, my_team: Team, rounds: list[_Round], detail: _Detail) -> list[dict]:
    """Each of their players on this Map: AWP, opening duels, usual spot, and our duels."""
    ids = [r.id for r in rounds]
    if not ids:
        return []
    side_of = {r.id: r.side_of(opponent.id) for r in rounds}
    rows = (
        db()
        .execute(
            select(
                PlayerRound.round_id,
                PlayerRound.player_id,
                PlayerRound.primary_weapon,
                PlayerRound.equip_value,
                PlayerRound.opening_kill,
                PlayerRound.opening_death,
            ).where(PlayerRound.round_id.in_(ids), PlayerRound.team_id == opponent.id)
        )
        .all()
    )
    stats: dict[int, dict] = defaultdict(
        lambda: {
            side: {"rounds": 0, "armed": 0, "awp": 0, "opening_kills": 0, "opening_deaths": 0}
            for side in ("ct", "t")
        }
    )
    for row in rows:
        side = side_of.get(row.round_id)
        if side not in ("ct", "t"):
            continue
        s = stats[row.player_id][side]
        s["rounds"] += 1
        if row.primary_weapon:
            s["armed"] += 1
            s["awp"] += row.primary_weapon == AWP
        s["opening_kills"] += row.opening_kill
        s["opening_deaths"] += row.opening_death
    spots: dict[int, dict[str, Counter]] = defaultdict(lambda: {"ct": Counter(), "t": Counter()})
    for r in rounds:
        side = side_of[r.id]
        for player, s, place, *_xyz in detail.setup.get(r.id, ()):
            if s == side and place:
                spots[player][side][place] += 1
    duels = _h2h_duels(opponent, my_team)
    names = dict(
        db().execute(select(Player.id, Player.name).where(Player.id.in_(list(stats)))).all()
    )
    out = []
    for player, by_side in stats.items():
        sides = {}
        for side, s in by_side.items():
            if not s["rounds"]:
                continue
            top = spots[player][side].most_common(1)
            sides[side] = {
                **s,
                "awper": bool(s["armed"]) and s["awp"] / s["armed"] >= AWP_SHARE,
                "spot": {
                    "place": top[0][0],
                    "n": top[0][1],
                    "of": sum(spots[player][side].values()),
                }
                if top
                else None,
            }
        out.append(
            {
                "player_id": player,
                "player": names.get(player, "?"),
                "sides": sides,
                "duels": duels.get(player, []),
            }
        )
    # Only their Lineup: a man who will not play is no matchup.
    fielded = lineup.fielded(opponent)
    out = [p for p in out if p["player_id"] in fielded]
    out.sort(key=lambda p: -sum(s["rounds"] for s in p["sides"].values()))
    return out


def _h2h_duels(opponent: Team, my_team: Team) -> dict[int, list[dict]]:
    """``{their player: [{ours, kills, deaths}]}`` over every Head-to-head Match Map."""
    maps = [m.id for m in mapstrategy.maps_in_window(opponent, opponent=my_team)]
    if not maps:
        return {}
    pairs: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0])
    for killer, victim, killer_team, kills in db().execute(
        select(
            PlayerMapDuel.killer_id,
            PlayerMapDuel.victim_id,
            PlayerMapDuel.killer_team_id,
            func.sum(PlayerMapDuel.kills),
        )
        .where(
            PlayerMapDuel.match_map_id.in_(maps),
            or_(
                PlayerMapDuel.killer_team_id == opponent.id,
                PlayerMapDuel.victim_team_id == opponent.id,
            ),
        )
        .group_by(PlayerMapDuel.killer_id, PlayerMapDuel.victim_id, PlayerMapDuel.killer_team_id)
    ):
        if killer_team == opponent.id:
            pairs[(killer, victim)][0] += int(kills or 0)
        else:
            pairs[(victim, killer)][1] += int(kills or 0)
    # Only our Lineup answers their man.
    fielded = lineup.fielded(my_team)
    pairs = {(t, o): kd for (t, o), kd in pairs.items() if o in fielded}
    ours = {o for _t, o in pairs}
    names = dict(
        db().execute(select(Player.id, Player.name).where(Player.id.in_(list(ours)))).all()
    )
    out: dict[int, list[dict]] = defaultdict(list)
    for (theirs, mine), (kills, deaths) in pairs.items():
        out[theirs].append({"player": names.get(mine, "?"), "kills": kills, "deaths": deaths})
    for rows in out.values():
        rows.sort(key=lambda d: d["kills"] - d["deaths"])
    return out


# --------------------------------------------------------------------- build --
def maps(board: list[dict]) -> list[dict]:
    """The Maps worth a Playbook, in the order the veto makes them likely.

    ``board`` is :func:`app.services.gameplan.map_board`'s. Our pick first, then
    the close maps a decider comes from, then the ones we would ban (their
    likely pick), then the ones only one side has played.
    """
    order = {"pick": 0, "contest": 1, "ban": 2, "avoid": 3, "blind": 4}
    out = []
    for row in board:
        call = row["verdict"]["call"]
        if call not in order:
            continue
        out.append(
            {
                "map": row["map"],
                "call": call,
                "why": row["verdict"]["why"],
                "mine": (row["mine"] or {}).get("maps", 0),
                "theirs": (row["theirs"] or {}).get("maps", 0),
                "h2h": (row["h2h"] or {}).get("maps", 0),
            }
        )
    out.sort(key=lambda m: (order[m["call"]], -(m["theirs"] + m["mine"]), m["map"]))
    return out


def _fielded_only(team: Team, habits: list[dict]) -> list[dict]:
    """Drop a usual-spot habit of anyone outside the Team's Lineup; it will not be there."""
    fielded = lineup.fielded(team)
    return [h for h in habits if h["kind"] != "spot" or h["player_id"] in fielded]


def build(my_team: Team, opponent: Team, map_name: str) -> dict:
    """One Map's Playbook, structured: what they do, what we do, and the evidence."""
    theirs = _team_rounds(opponent, my_team, map_name)
    mine = _team_rounds(my_team, opponent, map_name)
    sites = site_centroids(map_name)
    detail = _detail(list({r.id: r for r in (*theirs, *mine)}.values()))
    all_theirs = _team_rounds(opponent, my_team, None)
    pools = map_pools(map_name)

    def sample(team: Team, rounds: list[_Round]) -> dict:
        every = [
            m
            for m in mapstrategy.maps_in_window(team)
            if m.game_map and m.game_map.name == map_name
        ]
        return {
            "maps": len({r.match_map_id for r in rounds}),
            # Match Maps on this Map in the window, before the era narrowed them.
            "all_maps": len(every),
            "h2h_maps": len({r.match_map_id for r in rounds if r.h2h}),
            "rounds": {side: len(_side_rounds(team.id, rounds, side)) for side in ("ct", "t")},
            "economy": any(r.buy(team.id) and r.number not in PISTOL_ROUNDS for r in rounds),
        }

    return {
        "map": map_name,
        "sites_known": "A" in sites and "B" in sites,
        "sample": {"theirs": sample(opponent, theirs), "mine": sample(my_team, mine)},
        # Their T side is what my CT plan answers, and their CT side my T plan.
        "their_t": _fielded_only(
            opponent, side_habits(opponent.id, theirs, "t", detail, sites, pools)
        ),
        "their_ct": _fielded_only(
            opponent, side_habits(opponent.id, theirs, "ct", detail, sites, pools)
        ),
        "pistols": pistols(opponent.id, theirs, detail, sites),
        "conversion": {
            "theirs": conversion(opponent.id, theirs),
            "mine": conversion(my_team.id, mine),
            "pool": conversion_pool(map_name),
        },
        "economy": economy(opponent.id, all_theirs),
        "matchups": matchups(opponent, my_team, theirs, detail),
        "self_scout": {
            side: _fielded_only(my_team, side_habits(my_team.id, mine, side, detail, sites, pools))
            for side in ("t", "ct")
        },
        "predictability": predictability(my_team.id, mine, detail, sites, map_name),
        "beaten_by": beaten_by(opponent.id, theirs, detail, sites),
    }
