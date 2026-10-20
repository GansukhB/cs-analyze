"""What job was each player actually doing, and were they any good at it.

A coach's questions sit one level above the scoreboard: what role is this player
actually playing (what the demo says, not the org's website); is he any good at
it (a role is only judged against the people doing the same job); should someone
move; is the new guy better than the one he replaced (only comparable in role
terms).

Everything is derived from the analysis tables; no awpy, no parquet. The
classification is **evidence-first**: every role assignment carries the signals
that produced it and the sample it was measured over, with a confidence and the
runner-up role rather than a certainty the sample cannot support.

Ported from cstat's ``hltv/services/roles.py`` (minus the recruitment entry
points, which no page here uses yet).
"""

from __future__ import annotations

import hashlib
import logging
import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence

from sqlalchemy import and_, select
from sqlalchemy.orm import joinedload

from app.models import (
    DamageEvent,
    KillEvent,
    MapRoster,
    MatchMap,
    Player,
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
from app.services import pool_cache, stats
from app.services.dbctx import count_if, db, memo, total

logger = logging.getLogger(__name__)

# A rate over fewer rounds than this is a rumour; roles are habits.
MIN_ROUNDS_FOR_ROLE = 40
# Below this the role is still reported, flagged, and never used for advice.
MIN_ROUNDS_TO_REPORT = 12

# Calibrated on the parsed sample: the first damage lands at a median of 14.7 s,
# the opening duel resolves at 29.5 s, the median kill happens at 59.3 s. "Early"
# means before the opening duel is usually over; "late" sits well above the
# median kill or it flags half the server.
EARLY_CONTACT_SEC = 25.0
LATE_CONTACT_SEC = 75.0
# Matches demo_parser.TRADE_SECONDS.
TRADE_SECONDS = 5.0

AWP = "awp"
UTILITY_TYPES = ("smoke", "inferno")


# --------------------------------------------------------------- taxonomy ---
# Each role is a side-specific *job*, defined by the signals that betray it and
# judged by a different set of numbers. `signals` are (key, weight, direction).
# The score is a weighted sum of z-scores against the pool being classified, so a
# role is always relative -- there is no absolute "entry fragger" threshold.
ROLES: dict[str, dict] = {
    "awper": {
        "label": "AWPer",
        "sides": ("ct", "t"),
        "blurb": "Holds the rifle budget. Judged on opening picks and whether the "
        "AWP survives to hold the next round.",
        "signals": [("awp_share", 3.0, +1), ("opening_rate", 0.5, +1)],
        # A hard gate: real AWPers sit at 0.22-0.47 AWP share, every rifler at or
        # below 0.05; there is no ambiguous middle to protect.
        "gate": lambda s: s["awp_share"] >= 0.15 and s["awp_kills"] >= 5,
        "kpis": ("awp_kills_per_round", "opening_win_pct", "adr", "multi_kill_rate"),
    },
    "entry": {
        "label": "Entry / opener",
        "sides": ("t",),
        "blurb": "Takes first contact so the others enter behind him. Judged on how "
        "often he opens and whether the round survives when he dies.",
        "signals": [
            ("opening_rate", 2.5, +1),
            ("contact_delay_sec", 2.0, -1),
            ("trade_kill_share", 0.5, -1),
            ("util_per_round", 0.5, -1),
        ],
        "kpis": ("opening_rate", "opening_win_pct", "open_round_win_pct", "traded_death_pct"),
    },
    "support": {
        "label": "Support",
        "sides": ("ct", "t"),
        "blurb": "Buys the space someone else takes. Judged on utility volume and "
        "on what the team does in the rounds he throws it.",
        "signals": [
            ("util_per_round", 2.5, +1),
            ("flash_assists_per_round", 1.5, +1),
            ("assists_per_round", 1.0, +1),
            ("opening_rate", 1.0, -1),
        ],
        "kpis": ("util_per_round", "flash_assists_per_round", "smoke_win_pct", "assists_per_round"),
    },
    "lurker": {
        "label": "Lurker",
        "sides": ("t",),
        "blurb": "Plays away from the five-man, late and alone. Judged on what the "
        "isolation buys -- late kills and rounds saved, not raw frags.",
        "signals": [
            ("contact_delay_sec", 2.5, +1),
            ("late_kill_share", 2.0, +1),
            ("opening_rate", 1.5, -1),
            ("traded_death_pct", 1.0, -1),
        ],
        "kpis": ("late_kill_share", "contact_delay_sec", "kd_ratio", "adr"),
    },
    "trader": {
        "label": "Second contact / trader",
        "sides": ("t", "ct"),
        "blurb": "Enters on the entry's shoulder and cashes the trade. Judged on "
        "how much of his damage arrives inside the trade window.",
        "signals": [
            ("trade_kill_share", 2.5, +1),
            ("contact_delay_sec", 1.0, -1),
            ("opening_rate", 0.5, -1),
        ],
        "kpis": ("trade_kill_share", "adr", "kast_pct", "kd_ratio"),
    },
    "anchor": {
        "label": "Anchor",
        "sides": ("ct",),
        "blurb": "Holds one site, usually outnumbered, until help arrives. Judged on "
        "time bought and multi-kills, never on ADR.",
        "signals": [
            ("place_concentration", 2.5, +1),
            ("opening_rate", 1.0, -1),
            ("contact_delay_sec", 1.0, +1),
        ],
        "kpis": ("place_concentration", "multi_kill_rate", "kd_ratio", "adr"),
    },
    "rotator": {
        "label": "Rotator / roamer",
        "sides": ("ct",),
        "blurb": "Plays the map, not a site -- takes map control early and rotates. "
        "Judged on aggression that pays: early picks without early deaths.",
        "signals": [
            ("place_concentration", 2.0, -1),
            ("opening_rate", 1.5, +1),
            ("contact_delay_sec", 1.0, -1),
        ],
        "kpis": ("opening_win_pct", "place_spread", "adr", "kd_ratio"),
    },
}

# Roles a five-man needs covered: a vacancy is a question for the coach.
EXPECTED_COVERAGE = {
    "t": ("entry", "awper", "support", "lurker"),
    "ct": ("awper", "anchor", "rotator", "support"),
}


# ---------------------------------------------------------------- signals ---
def role_signals(
    team: Team, match_maps: Iterable[MatchMap], feed: _Feed | None = None
) -> dict[int, dict]:
    """Every measurable role signal, per player, split by side.

    Returns ``{player_id: {"name", "sides": {"ct": {...}, "t": {...}}, "overall"}}``.
    The per-round work that cannot be a GROUP BY (first contact, trades) is done
    in Python over a few thousand rows, read from ``feed`` when the caller has
    already read them for many teams at once.
    """
    match_maps = list(match_maps)
    map_ids = [m.id for m in match_maps]
    if not map_ids:
        return {}
    session = db()

    players = dict(
        session.execute(
            select(MapRoster.player_id, Player.name)
            .join(Player, Player.id == MapRoster.player_id)
            .where(MapRoster.match_map_id.in_(map_ids), MapRoster.team_id == team.id)
        ).all()
    )
    if not players:
        return {}
    pids = list(players)
    tickrates = {m.id: m.tickrate for m in match_maps}

    per_side: dict[int, dict[str, dict]] = defaultdict(lambda: defaultdict(dict))

    # -- the round rollup: everything already resolved at ingest
    in_rounds = (
        PlayerRound.round_id.in_(select(Round.id).where(Round.match_map_id.in_(map_ids))),
        PlayerRound.player_id.in_(pids),
        PlayerRound.side != "",
    )
    for row in session.execute(
        select(
            PlayerRound.player_id,
            PlayerRound.side,
            count_if(PlayerRound.id.is_not(None)),
            total(PlayerRound.kills),
            total(PlayerRound.deaths),
            total(PlayerRound.assists),
            total(PlayerRound.damage),
            count_if(PlayerRound.opening_kill),
            count_if(PlayerRound.opening_death),
            count_if(PlayerRound.kast),
            count_if(PlayerRound.traded),
        )
        .where(*in_rounds)
        .group_by(PlayerRound.player_id, PlayerRound.side)
    ):
        pid, side, n, kills, deaths, assists, damage, ok, od, kast, traded = (
            row[0],
            row[1],
            *(int(v or 0) for v in row[2:]),
        )
        per_side[pid][side] = {
            "rounds": n,
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "damage": damage,
            "adr": _div(damage, n),
            "kd_ratio": round(kills / deaths, 2) if deaths else float(kills),
            "kast_pct": _pct(kast, n),
            "opening_kills": ok,
            "opening_deaths": od,
            "opening_attempts": ok + od,
            "opening_rate": _div(ok + od, n, 3),
            "opening_win_pct": _pct(ok, ok + od),
            "traded_death_pct": _pct(traded, deaths),
            "assists_per_round": _div(assists, n, 3),
        }

    for pid, side, n in session.execute(
        select(PlayerRound.player_id, PlayerRound.side, count_if(PlayerRound.kills >= 3))
        .where(*in_rounds)
        .group_by(PlayerRound.player_id, PlayerRound.side)
    ):
        if int(n or 0):
            _set(per_side, pid, side, "multi_kill_rounds", int(n))

    # The entry's last KPI: how often the Round is won once he has opened it.
    for pid, side, opened, won in session.execute(
        select(
            PlayerRound.player_id,
            PlayerRound.side,
            count_if(PlayerRound.opening_kill),
            count_if(and_(PlayerRound.opening_kill, Round.winner_side == PlayerRound.side)),
        )
        .join(Round, Round.id == PlayerRound.round_id)
        .where(*in_rounds)
        .group_by(PlayerRound.player_id, PlayerRound.side)
    ):
        if int(opened or 0):
            _set(per_side, pid, side, "open_round_win_pct", _pct(int(won or 0), int(opened)))

    # -- weapons: the AWP question, and it is only ever the AWP
    for pid, side, weapon, kills in session.execute(
        select(
            PlayerMapWeapon.player_id,
            PlayerMapWeapon.side,
            PlayerMapWeapon.weapon,
            total(PlayerMapWeapon.kills),
        )
        .where(
            PlayerMapWeapon.match_map_id.in_(map_ids),
            PlayerMapWeapon.player_id.in_(pids),
            PlayerMapWeapon.side != "",
        )
        .group_by(PlayerMapWeapon.player_id, PlayerMapWeapon.side, PlayerMapWeapon.weapon)
    ):
        bucket = per_side[pid].get(side)
        if bucket is not None:
            bucket.setdefault("weapon_kills", {})[weapon] = int(kills or 0)

    # -- utility: volume, and whether anyone was blinded by it
    for pid, side, smokes, infernos, flashes, smoke_rounds, smoke_won in session.execute(
        select(
            PlayerMapUtility.player_id,
            PlayerMapUtility.side,
            total(PlayerMapUtility.smokes),
            total(PlayerMapUtility.infernos),
            total(PlayerMapUtility.flash_assists),
            total(PlayerMapUtility.smoke_rounds),
            total(PlayerMapUtility.smoke_rounds_won),
        )
        .where(
            PlayerMapUtility.match_map_id.in_(map_ids),
            PlayerMapUtility.player_id.in_(pids),
            PlayerMapUtility.side != "",
        )
        .group_by(PlayerMapUtility.player_id, PlayerMapUtility.side)
    ):
        bucket = per_side[pid].get(side)
        if bucket is None:
            continue
        bucket["smokes"] = int(smokes or 0)
        bucket["infernos"] = int(infernos or 0)
        bucket["flash_assists"] = int(flashes or 0)
        bucket["smoke_rounds"] = int(smoke_rounds or 0)
        bucket["smoke_rounds_won"] = int(smoke_won or 0)

    # -- where they kill from, kept per map: "BombsiteA" on Mirage and on Nuke are
    # different rooms, so concentration is measured inside one map and averaged.
    places: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for pid, side, place, map_id, n in session.execute(
        select(
            PlayerMapPosition.player_id,
            PlayerMapPosition.side,
            PlayerMapPosition.place,
            PlayerMapPosition.match_map_id,
            total(PlayerMapPosition.count),
        )
        .where(
            PlayerMapPosition.match_map_id.in_(map_ids),
            PlayerMapPosition.player_id.in_(pids),
            PlayerMapPosition.kind == PositionKind.KILL_FROM,
            PlayerMapPosition.side != "",
            PlayerMapPosition.place != "",
        )
        .group_by(
            PlayerMapPosition.player_id,
            PlayerMapPosition.side,
            PlayerMapPosition.place,
            PlayerMapPosition.match_map_id,
        )
    ):
        places[pid][side][map_id].append((place, int(n or 0)))

    # -- timing and trades: needs the raw feed, one pass each
    contact = _first_contact(map_ids, pids, tickrates, feed)
    trades = _trade_share(map_ids, pids, tickrates, feed)
    lateness = _kill_timing(map_ids, pids, tickrates, feed)

    out: dict[int, dict] = {}
    for pid, name in players.items():
        sides = {}
        for side, bucket in per_side.get(pid, {}).items():
            n = bucket["rounds"]
            weapon_kills = bucket.get("weapon_kills", {})
            gun_kills = sum(weapon_kills.values())
            awp_kills = weapon_kills.get(AWP, 0)
            util = bucket.get("smokes", 0) + bucket.get("infernos", 0)
            by_map = places.get(pid, {}).get(side, {})
            place_rows = _pooled_places(by_map)
            fc = contact.get((pid, side), {})
            bucket.update(
                {
                    "awp_kills": awp_kills,
                    "awp_share": _div(awp_kills, gun_kills, 3) if gun_kills else 0.0,
                    "awp_kills_per_round": _div(awp_kills, n, 3),
                    "util_thrown": util,
                    "util_per_round": _div(util, n, 3),
                    "flash_assists_per_round": _div(bucket.get("flash_assists", 0), n, 3),
                    "smoke_win_pct": _pct(
                        bucket.get("smoke_rounds_won", 0), bucket.get("smoke_rounds", 0)
                    ),
                    "multi_kill_rate": _div(bucket.get("multi_kill_rounds", 0), n, 3),
                    "place_concentration": _mean_hhi(by_map),
                    "place_spread": _mean_spread(by_map),
                    "top_places": [{"place": p, "kills": c} for p, c in place_rows[:4]],
                    "first_contact_sec": fc.get("median"),
                    "early_contact_share": fc.get("early_share", 0.0),
                    "contact_rounds": fc.get("n", 0),
                    "contact_delay_sec": fc.get("delay"),
                    "trade_kill_share": trades.get((pid, side), {}).get("share", 0.0),
                    "trade_kills": trades.get((pid, side), {}).get("trades", 0),
                    "late_kill_share": lateness.get((pid, side), {}).get("late_share", 0.0),
                    "median_kill_sec": lateness.get((pid, side), {}).get("median"),
                }
            )
            bucket.pop("weapon_kills", None)
            # A player who never took a fight has no timing: treat it as the middle
            # of the round so it pulls him towards neither entry nor lurker.
            if bucket["first_contact_sec"] is None:
                bucket["first_contact_sec"] = (EARLY_CONTACT_SEC + LATE_CONTACT_SEC) / 2
                bucket["first_contact_estimated"] = True
            sides[side] = bucket
        if not sides:
            continue
        out[pid] = {"player_id": pid, "name": name, "sides": sides, "overall": _merge_sides(sides)}
    return out


def _round_freeze(map_ids) -> dict:
    return {
        rid: (freeze, map_id)
        for rid, freeze, map_id in db().execute(
            select(Round.id, Round.freeze_end_tick, Round.match_map_id).where(
                Round.match_map_id.in_(map_ids)
            )
        )
    }


def _events(model, map_ids):
    return db().execute(
        select(
            model.round_id,
            model.tick,
            model.attacker_id,
            model.victim_id,
            model.attacker_side,
            model.victim_side,
        ).where(model.round_id.in_(select(Round.id).where(Round.match_map_id.in_(map_ids))))
    )


class _Feed:
    """Every round's clock and its kill and damage feed for many Match Maps, read once.

    :func:`pool_signals` measures every team in the Pool. Asked team by team, each
    Match Map's feed was read once for each team that played it and again for each
    signal: 731k rows through the driver for 355 Match Maps, most of a minute.
    Read here once, a third of that, and each team's :func:`role_signals` takes its
    own maps' share. Within a round the rows keep the database's order, which is
    what :func:`_trade_share` breaks a same-tick tie by.
    """

    def __init__(self, map_ids):
        self._freeze = _round_freeze(map_ids)
        self._events: dict = {}
        for model in (DamageEvent, KillEvent):
            by_map: dict[int, list] = defaultdict(list)
            for row in _events(model, map_ids):
                by_map[self._freeze[row[0]][1]].append(tuple(row))
            self._events[model] = by_map

    def rounds(self, map_ids) -> dict:
        wanted = set(map_ids)
        return {rid: value for rid, value in self._freeze.items() if value[1] in wanted}

    def events(self, model, map_ids) -> list:
        return [row for map_id in map_ids for row in self._events[model].get(map_id, ())]


def _first_contact(map_ids, pids, tickrates, feed=None) -> dict[tuple, dict]:
    """Seconds from freeze end to a player's first fight, per (player, side).

    Damage is the better clock than kills (being shot at is contact), so both feeds
    are read and the earlier one wins. Median, so one eco nobody left spawn on
    does not drag an entry's clock into lurker territory.
    """
    freeze = feed.rounds(map_ids) if feed else _round_freeze(map_ids)
    pids_set = set(pids)
    earliest: dict[tuple, int] = {}

    def offer(round_id, pid, side, tick):
        if pid not in pids_set or not side or round_id not in freeze:
            return
        key = (round_id, pid, side)
        if key not in earliest or tick < earliest[key]:
            earliest[key] = tick

    for model in (DamageEvent, KillEvent):
        rows = feed.events(model, map_ids) if feed else _events(model, map_ids)
        for round_id, tick, attacker, victim, a_side, v_side in rows:
            offer(round_id, attacker, a_side, tick)
            offer(round_id, victim, v_side, tick)

    # Lateness is measured against the team's own first contact in the round: 40 s
    # is late in an execute and early in a full default; relative to his own four
    # team-mates it is unambiguous.
    team_first: dict[tuple, int] = {}
    for (round_id, _pid, side), tick in earliest.items():
        key = (round_id, side)
        if key not in team_first or tick < team_first[key]:
            team_first[key] = tick

    seconds: dict[tuple, list] = defaultdict(list)
    delays: dict[tuple, list] = defaultdict(list)
    for (round_id, pid, side), tick in earliest.items():
        freeze_tick, map_id = freeze[round_id]
        rate = tickrates.get(map_id) or 64
        secs = (tick - freeze_tick) / rate
        if secs < 0:
            continue  # pre-freeze-end damage: warmup or a knife in the buy.
        seconds[(pid, side)].append(secs)
        delays[(pid, side)].append((tick - team_first[(round_id, side)]) / rate)

    out = {}
    for key, values in seconds.items():
        early = sum(1 for v in values if v <= EARLY_CONTACT_SEC)
        out[key] = {
            "median": round(statistics.median(values), 1),
            "early_share": round(early / len(values), 3),
            "delay": round(statistics.median(delays[key]), 1) if delays.get(key) else 0.0,
            "n": len(values),
        }
    return out


def _trade_share(map_ids, pids, tickrates, feed=None) -> dict[tuple, dict]:
    """Share of a player's kills that are Trades (CONTEXT.md): killing the enemy who
    killed a *team-mate* within TRADE_SECONDS before.

    Team-mate is decided by side within the round, which stays correct across the
    half swap without a roster join. A kill that merely follows a team-mate's
    death, on someone else, is not a Trade (the Review and ingest agree).
    """
    pids_set = set(pids)
    freeze = feed.rounds(map_ids) if feed else _round_freeze(map_ids)
    map_of = {rid: map_id for rid, (_f, map_id) in freeze.items()}
    by_round: dict[int, list] = defaultdict(list)
    rows = feed.events(KillEvent, map_ids) if feed else _events(KillEvent, map_ids)
    for round_id, tick, attacker, victim, a_side, v_side in rows:
        by_round[round_id].append(
            {
                "tick": tick,
                "attacker_id": attacker,
                "victim_id": victim,
                "attacker_side": a_side,
                "victim_side": v_side,
            }
        )

    tally: dict[tuple, dict] = defaultdict(lambda: {"kills": 0, "trades": 0})
    for round_id, events in by_round.items():
        rate = tickrates.get(map_of.get(round_id)) or 64
        window = TRADE_SECONDS * rate
        events.sort(key=lambda e: e["tick"])
        for i, ev in enumerate(events):
            aid, side = ev["attacker_id"], ev["attacker_side"]
            if aid not in pids_set or not side:
                continue
            key = (aid, side)
            tally[key]["kills"] += 1
            for prior in events[:i]:
                if prior["tick"] < ev["tick"] - window:
                    continue
                if (
                    prior["victim_side"] == side
                    and prior["victim_id"] != aid
                    and prior["attacker_id"] == ev["victim_id"]
                ):
                    tally[key]["trades"] += 1
                    break
    return {
        key: {"kills": v["kills"], "trades": v["trades"], "share": _div(v["trades"], v["kills"], 3)}
        for key, v in tally.items()
    }


def _kill_timing(map_ids, pids, tickrates, feed=None) -> dict[tuple, dict]:
    """When in the round a player's kills happen -- the lurker's signature."""
    if feed:
        freeze = feed.rounds(map_ids)
        pids_set = set(pids)
        kills = (
            (round_id, tick, attacker, side)
            for round_id, tick, attacker, _victim, side, _v_side in feed.events(KillEvent, map_ids)
            if attacker in pids_set and side
        )
    else:
        freeze = _round_freeze(map_ids)
        kills = db().execute(
            select(
                KillEvent.round_id, KillEvent.tick, KillEvent.attacker_id, KillEvent.attacker_side
            ).where(
                KillEvent.round_id.in_(list(freeze)),
                KillEvent.attacker_id.in_(list(pids)),
                KillEvent.attacker_side != "",
            )
        )
    seconds: dict[tuple, list] = defaultdict(list)
    for round_id, tick, attacker, side in kills:
        freeze_tick, map_id = freeze[round_id]
        rate = tickrates.get(map_id) or 64
        secs = (tick - freeze_tick) / rate
        if secs >= 0:
            seconds[(attacker, side)].append(secs)

    out = {}
    for key, values in seconds.items():
        late = sum(1 for v in values if v >= LATE_CONTACT_SEC)
        out[key] = {
            "median": round(statistics.median(values), 1),
            "late_share": round(late / len(values), 3),
            "n": len(values),
        }
    return out


# -------------------------------------------------------------- arithmetic ---
def _div(numerator, denominator, nd: int = 1) -> float:
    return round(numerator / denominator, nd) if denominator else 0.0


def _pct(numerator, denominator, nd: int = 1) -> float:
    return round(numerator / denominator * 100, nd) if denominator else 0.0


def _hhi(counts: Sequence[int]) -> float:
    """Herfindahl index over kill locations: 1.0 is one room, ~0 is everywhere."""
    whole = sum(counts)
    if not whole:
        return 0.0
    return round(sum((c / whole) ** 2 for c in counts), 3)


def _mean_hhi(by_map: dict[int, list]) -> float:
    """Concentration averaged over maps, weighted by the kills on each (never pooled)."""
    weighted, kills_total = 0.0, 0
    for rows in by_map.values():
        kills = sum(c for _, c in rows)
        if not kills:
            continue
        weighted += _hhi([c for _, c in rows]) * kills
        kills_total += kills
    return round(weighted / kills_total, 3) if kills_total else 0.0


def _mean_spread(by_map: dict[int, list]) -> float:
    """Distinct callouts used per map, averaged. The rotator's tell."""
    counts = [len(rows) for rows in by_map.values() if rows]
    return round(sum(counts) / len(counts), 2) if counts else 0.0


def _pooled_places(by_map: dict[int, list]) -> list:
    """Kill locations pooled for display only -- never for concentration."""
    pooled: dict[str, int] = defaultdict(int)
    for rows in by_map.values():
        for place, count in rows:
            pooled[place] += count
    return sorted(pooled.items(), key=lambda r: -r[1])


def _set(store, pid, side, key, value):
    bucket = store[pid].get(side)
    if bucket is not None:
        bucket[key] = value


def _merge_sides(sides: dict[str, dict]) -> dict:
    """Both halves added, for the numbers where adding is meaningful."""
    rounds = sum(s["rounds"] for s in sides.values())
    kills = sum(s["kills"] for s in sides.values())
    deaths = sum(s["deaths"] for s in sides.values())
    damage = sum(s["damage"] for s in sides.values())
    ok = sum(s["opening_kills"] for s in sides.values())
    od = sum(s["opening_deaths"] for s in sides.values())
    return {
        "rounds": rounds,
        "kills": kills,
        "deaths": deaths,
        "adr": _div(damage, rounds),
        "kd_ratio": round(kills / deaths, 2) if deaths else float(kills),
        "opening_kills": ok,
        "opening_deaths": od,
        "opening_rate": _div(ok + od, rounds, 3),
        "opening_win_pct": _pct(ok, ok + od),
        "awp_kills": sum(s.get("awp_kills", 0) for s in sides.values()),
        "util_per_round": _div(sum(s.get("util_thrown", 0) for s in sides.values()), rounds, 3),
    }


# --------------------------------------------------------------- baseline ---
BASELINE_SIGNALS = (
    "opening_rate",
    "opening_win_pct",
    "awp_share",
    "util_per_round",
    "flash_assists_per_round",
    "assists_per_round",
    "contact_delay_sec",
    "first_contact_sec",
    "late_kill_share",
    "trade_kill_share",
    "traded_death_pct",
    "place_concentration",
    "place_spread",
    "adr",
    "kast_pct",
    "kd_ratio",
    "multi_kill_rate",
)


# Bump when a role signal is measured differently: the Pool's signals are kept in
# Redis under this and the Match Maps they were measured on (`pool_cache`).
POOL_SCHEMA = 2


def pool_signals(match_maps: Iterable[MatchMap], signals: list | None = None) -> list:
    """``[(team, player_signals), ...]`` for every team in the pool.

    Shared by :func:`league_baseline` and :func:`role_cohorts`, which otherwise
    each ran `role_signals` over the whole database for the same answer. Computed
    once for these Match Maps as they were parsed, by whichever process asks first
    (the worker warms it after each parse), and shared through Redis.
    """
    if signals is not None:
        return signals
    match_maps = list(match_maps)
    key = _pool_key(match_maps)

    def compute():
        rows = pool_cache.remember(key, lambda: _pool_rows(match_maps))
        wanted = {tid for tid, _player in rows}
        teams = {t.id: t for t in db().scalars(select(Team).where(Team.id.in_(wanted)))}
        return [(teams[tid], player) for tid, player in rows if tid in teams]

    return memo(("pool_signals", key), compute)


def _pool_key(match_maps: list[MatchMap]) -> str:
    """Names the Match Maps, each as parsed and with its two teams."""
    digest = hashlib.sha1()
    for m in sorted(match_maps, key=lambda m: m.id):
        parsed = m.parsed_at.isoformat() if m.parsed_at else ""
        digest.update(f"{m.id}:{parsed}:{m.team1_id}:{m.team2_id};".encode())
    return f"pool:roles:v{POOL_SCHEMA}:{digest.hexdigest()}"


def _pool_rows(match_maps: list[MatchMap]) -> list:
    """``[[team_id, player_signals], ...]``: :func:`pool_signals` before the teams are loaded."""
    by_team: dict[int, list] = defaultdict(list)
    for m in match_maps:
        for tid in (m.team1_id, m.team2_id):
            if tid:
                by_team[tid].append(m)
    teams = {t.id: t for t in db().scalars(select(Team).where(Team.id.in_(list(by_team))))}
    feed = _Feed([m.id for m in match_maps])
    out = []
    for tid, maps in by_team.items():
        team = teams.get(tid)
        if team is None:
            continue
        for player in role_signals(team, maps, feed).values():
            out.append([tid, player])
    return out


def league_baseline(
    match_maps: Iterable[MatchMap],
    min_rounds: int = MIN_ROUNDS_TO_REPORT,
    signals: list | None = None,
) -> dict[str, dict]:
    """Mean and spread of every signal, per side, over everyone parsed.

    Ranking five team-mates against each other guarantees one "entry fragger" on a
    team that never opens; scoring against everyone asks whether he is an entry *by
    the standards of the teams we have parsed*. The spread is floored so a
    near-constant signal cannot manufacture huge z-scores.
    """
    pools: dict = defaultdict(lambda: defaultdict(list))
    for _team, player in pool_signals(match_maps, signals):
        for side, bucket in player["sides"].items():
            if bucket["rounds"] < min_rounds:
                continue
            for key in BASELINE_SIGNALS:
                value = bucket.get(key)
                if isinstance(value, int | float):
                    pools[side][key].append(float(value))

    out: dict[str, dict] = {}
    for side, side_signals in pools.items():
        side_stats = {}
        for key, values in side_signals.items():
            if len(values) < 2:
                continue
            mean = statistics.fmean(values)
            sd = statistics.pstdev(values)
            floor = max(abs(mean) * 0.10, 0.01)
            side_stats[key] = {
                "mean": round(mean, 4),
                "sd": round(max(sd, floor), 4),
                "n": len(values),
            }
        out[side] = side_stats
    return out


def _z(value, stat) -> float:
    if stat is None or not isinstance(value, int | float):
        return 0.0
    return (float(value) - stat["mean"]) / stat["sd"]


# --------------------------------------------------------- classification ---
def classify_player(bucket: dict, side: str, baseline: dict[str, dict]) -> dict:
    """Which job this player's numbers say he was doing, on one side.

    The runner-up is not decoration: a player who scores 2.1 as a lurker and 2.0 as
    a trader is genuinely both.
    """
    side_stats = baseline.get(side, {})
    scores = []
    for key, spec in ROLES.items():
        if side not in spec["sides"]:
            continue
        gate = spec.get("gate")
        if gate and not gate(bucket):
            continue
        evidence, score_total, weight_sum = [], 0.0, 0.0
        for signal, weight, direction in spec["signals"]:
            z = _z(bucket.get(signal), side_stats.get(signal))
            contribution = z * weight * direction
            score_total += contribution
            weight_sum += weight
            evidence.append(
                {
                    "signal": signal,
                    "value": bucket.get(signal),
                    "z": round(z, 2),
                    "pushes": round(contribution, 2),
                }
            )
        evidence.sort(key=lambda e: -abs(e["pushes"]))
        scores.append(
            {
                "role": key,
                "label": ROLES[key]["label"],
                "score": round(score_total / weight_sum, 3) if weight_sum else 0.0,
                "evidence": evidence,
            }
        )

    if not scores:
        return {
            "role": None,
            "label": "unclassified",
            "confidence": "none",
            "score": 0.0,
            "runner_up": None,
            "evidence": [],
            "rounds": bucket.get("rounds", 0),
        }

    scores.sort(key=lambda s: -s["score"])
    best, runner_up = scores[0], (scores[1] if len(scores) > 1 else None)
    gap = best["score"] - runner_up["score"] if runner_up else best["score"]
    rounds = bucket.get("rounds", 0)

    if rounds < MIN_ROUNDS_TO_REPORT:
        confidence = "none"
    elif rounds < MIN_ROUNDS_FOR_ROLE:
        confidence = "thin"
    elif gap >= 0.5 and best["score"] > 0.2:
        confidence = "clear"
    elif gap >= 0.2:
        confidence = "likely"
    else:
        confidence = "split"

    return {
        "role": best["role"],
        "label": best["label"],
        "score": best["score"],
        "confidence": confidence,
        "rounds": rounds,
        "gap": round(gap, 3),
        "runner_up": {
            "role": runner_up["role"],
            "label": runner_up["label"],
            "score": runner_up["score"],
        }
        if runner_up
        else None,
        "evidence": best["evidence"][:3],
        "all_scores": [{"role": s["role"], "score": s["score"]} for s in scores],
    }


def team_roles(team: Team, match_maps: Iterable[MatchMap], baseline=None) -> dict:
    """The full role picture for one team: who does what, and what is missing."""
    match_maps = list(match_maps)
    signals = role_signals(team, match_maps)
    if baseline is None:
        baseline = league_baseline(match_maps)

    players = []
    for player in signals.values():
        assigned = {
            side: classify_player(bucket, side, baseline)
            for side, bucket in player["sides"].items()
        }
        players.append(
            {
                "player_id": player["player_id"],
                "name": player["name"],
                "overall": player["overall"],
                "sides": player["sides"],
                "roles": assigned,
                "summary": _role_summary(player["name"], assigned),
            }
        )
    players.sort(key=lambda p: -p["overall"]["rounds"])
    return {
        "team": {"id": team.id, "name": team.name},
        "players": players,
        "coverage": _coverage(players),
        "baseline_sides": sorted(baseline),
        "maps": len(match_maps),
    }


def _role_summary(name: str, assigned: dict[str, dict]) -> str:
    parts = []
    for side in ("t", "ct"):
        role = assigned.get(side)
        if not role or not role["role"]:
            continue
        hedge = {
            "clear": "",
            "likely": "probably ",
            "split": "arguably ",
            "thin": "on a thin sample, ",
            "none": "on almost no sample, ",
        }[role["confidence"]]
        parts.append(f"{side.upper()}: {hedge}{role['label'].lower()}")
    return f"{name} — " + "; ".join(parts) if parts else f"{name} — not enough rounds to classify."


def _coverage(players: list[dict]) -> dict[str, dict]:
    """Which expected jobs are filled, doubled up, or vacant (vacant is the finding)."""
    out = {}
    for side, expected in EXPECTED_COVERAGE.items():
        holders: dict[str, list] = defaultdict(list)
        for p in players:
            role = p["roles"].get(side)
            if role and role["role"] and role["confidence"] not in ("none",):
                holders[role["role"]].append(
                    {"name": p["name"], "confidence": role["confidence"], "score": role["score"]}
                )
        out[side] = {
            "filled": {r: holders[r] for r in expected if r in holders},
            "missing": [r for r in expected if r not in holders],
            "doubled": {r: holders[r] for r in expected if r in holders and len(holders[r]) > 1},
            "labels": {r: ROLES[r]["label"] for r in expected},
        }
    return out


# ---------------------------------------------------------------- role fit ---
# What identifies a role and what makes someone good at it are different
# questions: an entry is identified by how often he opens, judged on winning it.
KPI_DIRECTION = {
    "opening_rate": +1,
    "opening_win_pct": +1,
    "open_round_win_pct": +1,
    "traded_death_pct": +1,
    "adr": +1,
    "kast_pct": +1,
    "kd_ratio": +1,
    "multi_kill_rate": +1,
    "awp_kills_per_round": +1,
    "util_per_round": +1,
    "flash_assists_per_round": +1,
    "smoke_win_pct": +1,
    "assists_per_round": +1,
    "late_kill_share": +1,
    "trade_kill_share": +1,
    "place_concentration": +1,
    "place_spread": +1,
    "contact_delay_sec": +1,
}

KPI_LABELS = {
    "opening_rate": "opening duels taken /round",
    "opening_win_pct": "opening duels won",
    "open_round_win_pct": "round win% when he opens",
    "traded_death_pct": "deaths that got traded",
    "adr": "ADR",
    "kast_pct": "KAST",
    "kd_ratio": "K/D",
    "multi_kill_rate": "3+ kill rounds /round",
    "awp_kills_per_round": "AWP kills /round",
    "util_per_round": "smokes+molotovs /round",
    "flash_assists_per_round": "flash assists /round",
    "smoke_win_pct": "round win% when he smokes",
    "assists_per_round": "assists /round",
    "late_kill_share": "kills after 75s",
    "trade_kill_share": "kills inside the trade window",
    "place_concentration": "position concentration",
    "place_spread": "callouts used per map",
    "contact_delay_sec": "seconds behind the team's first contact",
}


# PL-3 (docs/plans/04): a KPI that is a rate is judged against the cohort by
# empirical Bayes (stats.beta_prior/shrink, Rounds of one Match Map discounted);
# a continuous one is pulled toward the cohort by n/(n + k).
# kpi -> (the bucket's denominator, the value's scale: 100 for a percent)
RATE_KPIS = {
    "opening_win_pct": ("opening_attempts", 100.0),
    "traded_death_pct": ("deaths", 100.0),
    "kast_pct": ("rounds", 100.0),
    "open_round_win_pct": ("opening_kills", 100.0),
    "smoke_win_pct": ("smoke_rounds", 100.0),
    "multi_kill_rate": ("rounds", 1.0),
    "opening_rate": ("rounds", 1.0),
    "assists_per_round": ("rounds", 1.0),
    "awp_kills_per_round": ("rounds", 1.0),
    "flash_assists_per_round": ("rounds", 1.0),
    "trade_kill_share": ("kills", 1.0),
    "late_kill_share": ("kills", 1.0),
}
# Rounds of evidence that count half (n/(n+k) = 1/2), from split-half reliability
# over the local Pool on 2026-10-21 (48 Players with 6+ Match Maps: ADR r 0.60,
# K/D r 0.81 at 356 Rounds); the others have not been measured.
CONTINUOUS_K = {"adr": 239.0, "kd_ratio": 83.0}
DEFAULT_K = 150.0
ROUNDS_PER_HALF = 12  # one Side of one Match Map
MIN_EVENTS = 8  # events under a rate before it can be called above or below


def _rate(bucket: dict, kpi: str) -> tuple[float, float] | None:
    """``(successes, effective trials)`` for a rate KPI, or None."""
    spec = RATE_KPIS.get(kpi)
    value = _kpi_value(bucket, kpi)
    if spec is None or value is None:
        return None
    n = float(bucket.get(spec[0]) or 0)
    if n <= 0:
        return None
    x = min(max(value / spec[1] * n, 0.0), n)
    halves = max(1.0, float(bucket.get("rounds") or 0) / ROUNDS_PER_HALF)
    n_eff = stats.effective_n(n, n / halves)
    return x * n_eff / n, n_eff


def role_cohorts(match_maps: Iterable[MatchMap], baseline=None, signals=None) -> dict[tuple, dict]:
    """KPI distributions for everyone doing the same job, keyed ``(side, role)``.

    A support with 55 ADR is not underperforming; he is a support. The only fair
    comparison is against the others classified into the same role.
    """
    match_maps = list(match_maps)
    signals = pool_signals(match_maps, signals)
    if baseline is None:
        baseline = league_baseline(match_maps, signals=signals)

    pools: dict = defaultdict(lambda: defaultdict(list))
    rates: dict = defaultdict(lambda: defaultdict(list))
    members: dict[tuple, list] = defaultdict(list)
    for team, player in signals:
        for side, bucket in player["sides"].items():
            if bucket["rounds"] < MIN_ROUNDS_TO_REPORT:
                continue
            verdict = classify_player(bucket, side, baseline)
            if not verdict["role"]:
                continue
            key = (side, verdict["role"])
            members[key].append(
                {"name": player["name"], "team": team.name, "rounds": bucket["rounds"]}
            )
            for kpi in ROLES[verdict["role"]]["kpis"]:
                value = _kpi_value(bucket, kpi)
                if value is not None:
                    pools[key][kpi].append(value)
                rate = _rate(bucket, kpi)
                if rate is not None:
                    rates[key][kpi].append((*rate, player["player_id"]))

    out = {}
    for key, kpis in pools.items():
        kpi_stats = {}
        for kpi, values in kpis.items():
            if len(values) < 2:
                continue
            mean = statistics.fmean(values)
            sd = statistics.pstdev(values)
            kpi_stats[kpi] = {
                "mean": round(mean, 3),
                "sd": round(max(sd, max(abs(mean) * 0.10, 0.01)), 4),
                "n": len(values),
            }
        out[key] = {
            "kpis": kpi_stats,
            "rates": {kpi: list(rows) for kpi, rows in rates[key].items()},
            "members": members[key],
            "n": len(members[key]),
        }
    return out


def _kpi_value(bucket: dict, kpi: str):
    if kpi in bucket:
        value = bucket[kpi]
        return float(value) if isinstance(value, int | float) else None
    return None


def _judge(bucket: dict, kpi: str, stat: dict, cohort: dict, player_id) -> dict | None:
    """One KPI against the cohort, shrunk: its ``z`` and ``verdict``."""
    direction = KPI_DIRECTION.get(kpi, +1)
    rate = _rate(bucket, kpi)
    others = [(x, n) for x, n, pid in (cohort.get("rates") or {}).get(kpi, []) if pid != player_id]
    prior = stats.beta_prior(others) if rate is not None and len(others) >= 2 else None
    if rate is not None and prior is not None:
        x, n = rate
        post = stats.shrink(x, n, prior)
        spread = (prior.mean * (1 - prior.mean) / (prior.strength + 1)) ** 0.5
        z = (post.mean - prior.mean) / spread * direction if spread else 0.0
        clear = post.clear() and float(bucket.get(RATE_KPIS[kpi][0]) or 0) >= MIN_EVENTS
        better = (post.mean > prior.mean) == (direction > 0)
        verdict = ("above" if better else "below") if clear else "par"
        return {"z": z, "verdict": verdict, "shrunk": post.mean * RATE_KPIS[kpi][1],
                "lfsr": round(post.lfsr, 3)}  # fmt: skip
    value = _kpi_value(bucket, kpi)
    if value is None:
        return None
    n = float(bucket.get("rounds") or 0)
    pulled = stats.shrink_mean(value, n, stat["mean"], CONTINUOUS_K.get(kpi, DEFAULT_K))
    z = (pulled - stat["mean"]) / stat["sd"] * direction
    verdict = "above" if z >= 0.5 else ("below" if z <= -0.5 else "par")
    return {"z": z, "verdict": verdict, "shrunk": pulled, "lfsr": None}


def role_fit(
    bucket: dict, side: str, role: str, cohorts: dict[tuple, dict], player_id=None
) -> dict:
    """How this player rates against everyone else doing the same job.

    The verdict is deliberately coarse (strong / solid / below par / struggling):
    with a cohort of four or five a decimal place is false precision.
    """
    cohort = cohorts.get((side, role))
    if not cohort or cohort["n"] < 2:
        return {
            "verdict": "no cohort",
            "score": None,
            "kpis": [],
            "cohort_size": cohort["n"] if cohort else 0,
        }

    rows, score_total, n = [], 0.0, 0
    for kpi in ROLES[role]["kpis"]:
        stat = cohort["kpis"].get(kpi)
        value = _kpi_value(bucket, kpi)
        if stat is None or value is None:
            continue
        judged = _judge(bucket, kpi, stat, cohort, player_id)
        if judged is None:
            continue
        z = judged["z"]
        score_total += z
        n += 1
        rows.append(
            {
                "kpi": kpi,
                "label": KPI_LABELS.get(kpi, kpi),
                "value": round(value, 3),
                "shrunk": round(judged["shrunk"], 3),
                "cohort_mean": stat["mean"],
                "z": round(z, 2),
                "lfsr": judged["lfsr"],
                "verdict": judged["verdict"],
            }
        )

    if not n:
        return {"verdict": "no cohort", "score": None, "kpis": [], "cohort_size": cohort["n"]}

    score = score_total / n
    if score >= 0.6:
        verdict = "strong"
    elif score >= -0.2:
        verdict = "solid"
    elif score >= -0.8:
        verdict = "below par"
    else:
        verdict = "struggling"

    rows.sort(key=lambda r: r["z"])
    return {
        "verdict": verdict,
        "score": round(score, 2),
        "kpis": rows,
        "weakest": rows[0] if rows else None,
        "strongest": rows[-1] if rows else None,
        "cohort_size": cohort["n"],
        "cohort": [m["name"] for m in cohort["members"]],
    }


def rate_team(team: Team, match_maps: Iterable[MatchMap], baseline=None, cohorts=None) -> dict:
    """Roles plus fit for one team -- who is doing what, and who is doing it well."""
    match_maps = list(match_maps)
    if baseline is None:
        baseline = league_baseline(match_maps)
    if cohorts is None:
        cohorts = role_cohorts(match_maps, baseline)

    picture = team_roles(team, match_maps, baseline=baseline)
    for player in picture["players"]:
        fits = {}
        for side, bucket in player["sides"].items():
            role = player["roles"][side]["role"]
            if role:
                fits[side] = role_fit(bucket, side, role, cohorts, player.get("player_id"))
        player["fit"] = fits
        player["rating"] = _overall_rating(fits)
    # Which of these men are still fielded: ranking a player who left months ago
    # alongside the current five is a trap.
    current = _current_lineup(team, match_maps)
    for player in picture["players"]:
        player["in_current_lineup"] = (not current) or player["name"] in current
    picture["current_lineup"] = sorted(current)
    picture["players"].sort(
        key=lambda p: p["rating"] if p["rating"] is not None else -9, reverse=True
    )
    fielded = [p for p in picture["players"] if p["in_current_lineup"]]
    picture["best"] = [p for p in fielded if p["rating"] is not None][:2]
    picture["worst"] = [
        p
        for p in reversed(fielded)
        if p["rating"] is not None and p["overall"]["rounds"] >= MIN_ROUNDS_FOR_ROLE
    ][:2]
    return picture


def _current_lineup(team: Team, match_maps: Iterable[MatchMap]) -> set:
    """The Team's Lineup: the Players picked for it, else the five fielded in the
    most recent match in this sample."""
    return lineups.names(team, lambda: _latest_in_sample(team, match_maps))


def _latest_in_sample(team: Team, match_maps: Iterable[MatchMap]) -> set:
    dated = [m for m in match_maps if m.match and m.match.played_at]
    if not dated:
        return set()
    latest = max(m.match.played_at for m in dated)
    latest_maps = [m.id for m in dated if m.match.played_at == latest]
    return set(
        db().scalars(
            select(Player.name)
            .join(MapRoster, MapRoster.player_id == Player.id)
            .where(MapRoster.match_map_id.in_(latest_maps), MapRoster.team_id == team.id)
        )
    )


def _overall_rating(fits: dict[str, dict]) -> float | None:
    scores = [f["score"] for f in fits.values() if f.get("score") is not None]
    return round(statistics.fmean(scores), 2) if scores else None


def _mean_or_none(values) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


# ------------------------------------------------------- position & path -----
MIN_ROUTE_ROUNDS_FOR_ADVICE = 3
MIN_PLACE_EVENTS = 4
BAD_ROUTE_NET = -0.34
GOOD_ROUTE_NET = 0.34
# Rounds' worth of "nothing happened" mixed into every route before judging it,
# so a path walked three times for 0-3 does not outrank one walked twelve for 3-9.
ROUTE_PRIOR_ROUNDS = 3


def _position_rows(where) -> list:
    return list(
        db().execute(
            select(
                PlayerMapPosition.player_id,
                Player.name,
                PlayerMapPosition.match_map_id,
                PlayerMapPosition.team_id,
                Team.name,
                PlayerMapPosition.side,
                PlayerMapPosition.place,
                PlayerMapPosition.kind,
                total(PlayerMapPosition.count),
            )
            .join(Player, Player.id == PlayerMapPosition.player_id)
            .outerjoin(Team, Team.id == PlayerMapPosition.team_id)
            .where(*where, PlayerMapPosition.side != "", PlayerMapPosition.place != "")
            .group_by(
                PlayerMapPosition.player_id,
                Player.name,
                PlayerMapPosition.match_map_id,
                PlayerMapPosition.team_id,
                Team.name,
                PlayerMapPosition.side,
                PlayerMapPosition.place,
                PlayerMapPosition.kind,
            )
        )
    )


def position_leaks(team: Team, match_maps: Iterable[MatchMap], limit: int = 5) -> list[dict]:
    """Places a player keeps dying in without killing from, per map and side.

    A spot he trades evenly is fine even if he dies there often (an anchor is
    supposed to die on his site); one that takes deaths and gives nothing back is
    worth flagging.
    """
    match_maps = list(match_maps)
    map_ids = [m.id for m in match_maps]
    if not map_ids:
        return []
    maps_by_id = {m.id: m for m in match_maps}

    tally: dict[tuple, dict] = defaultdict(lambda: {"kills": 0, "deaths": 0})
    for pid, name, map_id, _tid, _tname, side, place, kind, n in _position_rows(
        (PlayerMapPosition.match_map_id.in_(map_ids), PlayerMapPosition.team_id == team.id)
    ):
        if kind == PositionKind.KILL_FROM:
            field = "kills"
        elif kind == PositionKind.DEATH_AT:
            field = "deaths"
        else:
            continue  # victim_at describes the man he killed, not where he stood.
        tally[(pid, name, map_id, side, place)][field] += int(n or 0)

    leaks = []
    for (pid, name, map_id, side, place), counts in tally.items():
        events = counts["kills"] + counts["deaths"]
        if events < MIN_PLACE_EVENTS or counts["deaths"] <= counts["kills"]:
            continue
        match_map = maps_by_id.get(map_id)
        leaks.append(
            {
                "player_id": pid,
                "name": name,
                "map": match_map.game_map.name if match_map and match_map.game_map else "?",
                "match_map_id": map_id,
                "side": side,
                "place": place,
                "kills": counts["kills"],
                "deaths": counts["deaths"],
                "net": counts["kills"] - counts["deaths"],
                "note": (
                    f"{name} is {counts['kills']}-{counts['deaths']} at {place} on {side.upper()}"
                ),
            }
        )
    leaks.sort(key=lambda r: (r["net"], -r["deaths"]))
    return leaks[:limit]


def match_position_report(match_map: MatchMap, limit: int = 6) -> dict:
    """Weak and strong positions for *this* map, both teams, split by side."""
    tally: dict[tuple, dict] = defaultdict(lambda: {"kills": 0, "deaths": 0})
    meta: dict[tuple, tuple] = {}
    for pid, name, _map, team_id, team_name, side, place, kind, n in _position_rows(
        (PlayerMapPosition.match_map_id == match_map.id,)
    ):
        if kind == PositionKind.KILL_FROM:
            field = "kills"
        elif kind == PositionKind.DEATH_AT:
            field = "deaths"
        else:
            continue
        key = (pid, side, place)
        tally[key][field] += int(n or 0)
        meta[key] = (name, team_id, team_name)

    weak, strong = [], []
    for (pid, side, place), counts in tally.items():
        events = counts["kills"] + counts["deaths"]
        if events < MIN_PLACE_EVENTS or counts["kills"] == counts["deaths"]:
            continue
        name, team_id, team_name = meta[(pid, side, place)]
        row = {
            "player_id": pid,
            "name": name,
            "team_id": team_id,
            "team": team_name,
            "side": side,
            "place": place,
            "kills": counts["kills"],
            "deaths": counts["deaths"],
            "net": counts["kills"] - counts["deaths"],
            "note": f"{name} is {counts['kills']}-{counts['deaths']} at {place} on {side.upper()}",
        }
        (weak if counts["deaths"] > counts["kills"] else strong).append(row)

    weak.sort(key=lambda r: (r["net"], -r["deaths"]))
    strong.sort(key=lambda r: (-r["net"], -r["kills"]))

    def by_side(rows: list[dict]) -> dict[str, list]:
        # Split rather than a global top-N, so one loud side cannot starve the other.
        out: dict[str, list] = {"ct": [], "t": []}
        for r in rows:
            bucket = out.get(r["side"])
            if bucket is not None and len(bucket) < limit:
                bucket.append(r)
        return out

    return {"weak": by_side(weak), "strong": by_side(strong)}


def route_advice(team: Team, match_maps: Iterable[MatchMap], limit: int = 6) -> list[dict]:
    """Paths that cost a player rounds, and the team-mate who walks them better.

    Only inside one map and one side, and only between routes that cover the same
    ground (an overlap test, since two men rarely walk the identical sequence).
    """
    match_maps = list(match_maps)
    map_ids = [m.id for m in match_maps]
    if not map_ids:
        return []
    maps_by_id = {m.id: m for m in match_maps}

    rows = list(
        db().scalars(
            select(PlayerMapRoute)
            .options(joinedload(PlayerMapRoute.player))
            .where(
                PlayerMapRoute.match_map_id.in_(map_ids),
                PlayerMapRoute.team_id == team.id,
                PlayerMapRoute.rounds >= MIN_ROUTE_ROUNDS_FOR_ADVICE,
                PlayerMapRoute.side != "",
            )
            .order_by(
                PlayerMapRoute.match_map_id, PlayerMapRoute.player_id, PlayerMapRoute.rounds.desc()
            )
        )
    )
    by_scope: dict[tuple, list] = defaultdict(list)
    for r in rows:
        by_scope[(r.match_map_id, r.side)].append(r)

    advice = []
    for (map_id, side), scope_rows in by_scope.items():
        match_map = maps_by_id.get(map_id)
        map_name = match_map.game_map.name if match_map and match_map.game_map else "?"
        for bad in scope_rows:
            bad_score = _shrunk_net(bad)
            if bad_score > BAD_ROUTE_NET:
                continue
            better = None
            for other in scope_rows:
                if other.player_id == bad.player_id or _shrunk_net(other) < GOOD_ROUTE_NET:
                    continue
                overlap = _place_overlap(bad.places, other.places)
                if overlap < 0.4:
                    continue
                if better is None or _shrunk_net(other) > _shrunk_net(better[0]):
                    better = (other, overlap)
            advice.append(
                {
                    "player_id": bad.player_id,
                    "name": bad.player.name,
                    "map": map_name,
                    "match_map_id": map_id,
                    "side": side,
                    "route": bad.label,
                    "rounds": bad.rounds,
                    "kills": bad.kills,
                    "deaths": bad.deaths,
                    "net_per_round": bad.net_per_round,
                    "adjusted_net": bad_score,
                    "win_pct": bad.win_pct,
                    "alternative": (
                        {
                            "name": better[0].player.name,
                            "route": better[0].label,
                            "rounds": better[0].rounds,
                            "net_per_round": better[0].net_per_round,
                            "adjusted_net": _shrunk_net(better[0]),
                            "win_pct": better[0].win_pct,
                            "overlap": round(better[1], 2),
                        }
                        if better
                        else None
                    ),
                    "note": _route_note(bad, better, map_name, side),
                }
            )
    advice.sort(key=lambda r: (r["adjusted_net"], -r["rounds"]))
    return advice[:limit]


def _shrunk_net(route) -> float:
    """``(k - d) / (rounds + prior)``: kills minus deaths per round, pulled toward zero."""
    return round((route.kills - route.deaths) / (route.rounds + ROUTE_PRIOR_ROUNDS), 2)


def _place_overlap(a: Sequence[str], b: Sequence[str]) -> float:
    """Jaccard overlap of two callout sequences -- do they cover the same ground."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _route_note(bad, better, map_name: str, side: str) -> str:
    head = (
        f"{bad.player.name} is {bad.kills}-{bad.deaths} over {bad.rounds} rounds "
        f"taking {bad.label} on {map_name} {side.upper()} ({bad.net_per_round:+.2f}/round)"
    )
    if not better:
        return head + (
            " — no team-mate covers that ground profitably either, so it may be "
            "the approach, not the man."
        )
    other, _overlap = better
    return (
        head + f". {other.player.name} walks the same ground ({other.label}) at "
        f"{other.net_per_round:+.2f}/round over {other.rounds} rounds — worth swapping "
        "who takes it."
    )


# --------------------------------------------------------- role movement -----
def role_moves(picture: dict, baseline: dict[str, dict]) -> list[dict]:
    """Players rated below par in their role whose signals fit a role nobody fills.

    Anything looser is a suggestion to reshuffle a working team on noise.
    """
    moves = []
    coverage = picture["coverage"]
    for player in picture["players"]:
        for side, verdict in player["roles"].items():
            fit = player.get("fit", {}).get(side)
            if not verdict["role"] or not fit or fit.get("score") is None:
                continue
            if fit["score"] > -0.2 or player["sides"][side]["rounds"] < MIN_ROUNDS_FOR_ROLE:
                continue
            missing = set(coverage.get(side, {}).get("missing", []))
            for alt in verdict["all_scores"]:
                if alt["role"] == verdict["role"] or alt["score"] <= verdict["score"]:
                    continue
                if alt["role"] not in missing:
                    continue
                moves.append(
                    {
                        "player_id": player["player_id"],
                        "name": player["name"],
                        "side": side,
                        "from_role": verdict["role"],
                        "from_label": verdict["label"],
                        "from_fit": fit["score"],
                        "from_verdict": fit["verdict"],
                        "to_role": alt["role"],
                        "to_label": ROLES[alt["role"]]["label"],
                        "role_score_gain": round(alt["score"] - verdict["score"], 2),
                        "rounds": player["sides"][side]["rounds"],
                        "weakest_kpi": fit.get("weakest"),
                        "note": (
                            f"{player['name']} rates {fit['verdict']} ({fit['score']:+.2f}) as "
                            f"{verdict['label'].lower()} on {side.upper()}, and no one on the "
                            f"team fills {ROLES[alt['role']]['label'].lower()} — his own signals "
                            f"score him higher there ({alt['score']:+.2f} vs "
                            f"{verdict['score']:+.2f})."
                        ),
                    }
                )
                break
    moves.sort(key=lambda m: m["from_fit"])
    return moves


def _role_phrase(roles_by_side: dict[str, str]) -> str:
    if not roles_by_side:
        return "unclassified"
    return "/".join(f"{s.upper()} {label.lower()}" for s, label in sorted(roles_by_side.items()))


def player_dossier(
    player_id: int, match_maps: Iterable[MatchMap], baseline=None, cohorts=None
) -> dict | None:
    """One player's record everywhere he has been parsed, split by team.

    A player's numbers are a property of the player *in a system*: a man who lurked
    for one team and entried for the next has two statistical lives.
    """
    match_maps = list(match_maps)
    if baseline is None:
        baseline = league_baseline(match_maps)
    if cohorts is None:
        cohorts = role_cohorts(match_maps, baseline)

    appearances = list(
        db().scalars(
            select(MapRoster)
            .options(joinedload(MapRoster.team), joinedload(MapRoster.player))
            .where(
                MapRoster.player_id == player_id,
                MapRoster.match_map_id.in_([m.id for m in match_maps]),
            )
        )
    )
    if not appearances:
        return None

    name = appearances[0].player.name
    by_team: dict[int, list] = defaultdict(list)
    teams: dict[int, Team] = {}
    maps_by_id = {m.id: m for m in match_maps}
    for row in appearances:
        if row.team_id:
            by_team[row.team_id].append(maps_by_id[row.match_map_id])
            teams[row.team_id] = row.team

    spells = []
    for team_id, maps in by_team.items():
        team = teams[team_id]
        signals = role_signals(team, maps).get(player_id)
        if not signals:
            continue
        entry = {
            "team": team.name,
            "team_id": team_id,
            "maps": len(maps),
            "overall": signals["overall"],
            "sides": {},
            "roles": {},
            "fit": {},
        }
        for side, bucket in signals["sides"].items():
            verdict = classify_player(bucket, side, baseline)
            entry["sides"][side] = bucket
            entry["roles"][side] = verdict
            if verdict["role"]:
                entry["fit"][side] = role_fit(
                    bucket, side, verdict["role"], cohorts, signals.get("player_id")
                )
        entry["rating"] = _overall_rating(entry["fit"])
        dated = [m.match.played_at for m in maps if m.match and m.match.played_at]
        entry["from"] = min(dated).isoformat() if dated else None
        entry["to"] = max(dated).isoformat() if dated else None
        spells.append(entry)

    spells.sort(key=lambda s: s["from"] or "")
    return {
        "player_id": player_id,
        "name": name,
        "spells": spells,
        "teams": [s["team"] for s in spells],
    }


def role_glossary() -> list[dict]:
    """What each role means, so a page can explain its own vocabulary."""
    return [
        {"key": key, "label": spec["label"], "blurb": spec["blurb"], "sides": list(spec["sides"])}
        for key, spec in ROLES.items()
    ]


# ------------------------------------------------------------ roster churn ---
def roster_eras(team: Team, match_maps: Iterable[MatchMap]) -> list[dict]:
    """The team's lineups over time, in the order they were fielded.

    A roster change is not announced in the data; it has to be read off the
    demos. Maps are walked in match order and a new era begins whenever the
    five-man differs from the one before it. Stand-ins produce a one-match era,
    which is correct -- a stand-in *is* a different lineup.
    """
    maps = sorted(
        (m for m in match_maps if m.match and m.match.played_at),
        key=lambda m: (m.match.played_at, m.map_number),
    )
    if not maps:
        return []

    by_map: dict[int, set] = defaultdict(set)
    names: dict[int, str] = {}
    for row in db().scalars(
        select(MapRoster)
        .options(joinedload(MapRoster.player))
        .where(MapRoster.match_map_id.in_([m.id for m in maps]), MapRoster.team_id == team.id)
    ):
        by_map[row.match_map_id].add(row.player_id)
        names[row.player_id] = row.player.name

    eras: list[dict] = []
    for m in maps:
        fielded = by_map.get(m.id)
        if not fielded:
            continue
        if eras and eras[-1]["lineup"] == fielded:
            eras[-1]["maps"].append(m)
        else:
            eras.append({"lineup": fielded, "maps": [m]})

    out = []
    for i, era in enumerate(eras):
        prior = eras[i - 1]["lineup"] if i else set()
        out.append(
            {
                "index": i,
                "players": sorted(names[p] for p in era["lineup"]),
                "player_ids": sorted(era["lineup"]),
                "maps": len(era["maps"]),
                "match_maps": era["maps"],
                "from": era["maps"][0].match.played_at,
                "to": era["maps"][-1].match.played_at,
                "joined": sorted(names[p] for p in (era["lineup"] - prior)) if i else [],
                "left": sorted(names[p] for p in (prior - era["lineup"])) if i else [],
            }
        )
    return out


def roster_change_report(
    team: Team,
    match_maps: Iterable[MatchMap],
    baseline: dict[str, dict] | None = None,
    cohorts: dict[tuple, dict] | None = None,
    min_maps: int = 2,
) -> dict:
    """Did the change work -- in role terms, which is the only fair way to ask.

    Compares the eras on role coverage (which jobs the old lineup filled that
    the new one does not), like-for-like (each arrival against the departure
    whose role he came closest to inheriting) and the lineup's mean fit. Eras
    shorter than ``min_maps`` are reported but never used for a verdict.
    """
    match_maps = list(match_maps)
    if baseline is None:
        baseline = league_baseline(match_maps)
    if cohorts is None:
        cohorts = role_cohorts(match_maps, baseline)

    eras = roster_eras(team, match_maps)
    if not eras:
        return {
            "team": team.name,
            "eras": [],
            "changes": [],
            "current": None,
            "note": "No parsed maps in this window.",
        }

    rated = []
    for era in eras:
        picture = rate_team(team, era["match_maps"], baseline=baseline, cohorts=cohorts)
        rated.append(
            {
                "era": era,
                "picture": picture,
                "by_name": {p["name"]: p for p in picture["players"]},
                "mean_fit": _mean_or_none(
                    [p["rating"] for p in picture["players"] if p["rating"] is not None]
                ),
            }
        )

    if len(eras) < 2:
        return {
            "team": team.name,
            "eras": [_era_row(r) for r in rated],
            "changes": [],
            "current": rated[-1]["picture"],
            "note": "Only one lineup appears in this sample — nothing to compare it against.",
        }

    changes = []
    for i in range(1, len(rated)):
        before, after = rated[i - 1], rated[i]
        if not (before["era"]["joined"] or after["era"]["joined"] or after["era"]["left"]):
            continue
        changes.append(_compare_eras(before, after, cohorts, min_maps))

    return {
        "team": team.name,
        "eras": [_era_row(r) for r in rated],
        "changes": changes,
        "current": rated[-1]["picture"],
        "note": "",
    }


def _era_row(rated: dict) -> dict:
    """One era, without the MatchMap objects and with its fit attached."""
    era = rated["era"]
    return {k: v for k, v in era.items() if k != "match_maps"} | {"mean_fit": rated["mean_fit"]}


def _compare_eras(before: dict, after: dict, cohorts: dict[tuple, dict], min_maps: int) -> dict:
    """One lineup change, read as a set of jobs gained and lost."""
    left, joined = after["era"]["left"], after["era"]["joined"]

    def role_map(entry):
        out = {}
        for p in entry["picture"]["players"]:
            for side, verdict in p["roles"].items():
                if verdict["role"]:
                    out.setdefault((side, verdict["role"]), []).append(p["name"])
        return out

    before_roles, after_roles = role_map(before), role_map(after)

    # A job can only be called vacant on a side the new lineup actually played
    # enough of; and a job left by someone still in the side is drift, not departure.
    after_rounds = _side_rounds(after["picture"])
    still_here = set(after["by_name"])
    lost_jobs, unverifiable, gained_jobs = [], [], []
    for key in before_roles:
        if key in after_roles:
            continue
        side, role = key
        holders = before_roles[key]
        remaining = [h for h in holders if h in still_here]
        row = {
            "side": side,
            "role": role,
            "label": ROLES[role]["label"],
            "was": holders,
            "after_rounds": after_rounds.get(side, 0),
            "cause": "drift" if remaining else "departure",
            "drifted": [
                {"name": h, "now": after["by_name"][h]["roles"].get(side, {}).get("label")}
                for h in remaining
            ],
        }
        if after_rounds.get(side, 0) >= MIN_ROUNDS_FOR_ROLE:
            lost_jobs.append(row)
        else:
            unverifiable.append(row)
    for key in after_roles:
        if key not in before_roles:
            side, role = key
            gained_jobs.append(
                {"side": side, "role": role, "label": ROLES[role]["label"], "now": after_roles[key]}
            )

    # Match arrivals to departures, best role overlap first and each departure
    # spent only once.
    candidates = []
    for newcomer in joined:
        new_p = after["by_name"].get(newcomer)
        if not new_p:
            continue
        for departed in left:
            old_p = before["by_name"].get(departed)
            if not old_p:
                continue
            overlap = sum(
                1
                for side in ("t", "ct")
                if old_p["roles"].get(side, {}).get("role")
                and old_p["roles"][side]["role"] == new_p["roles"].get(side, {}).get("role")
            )
            candidates.append((overlap, newcomer, departed))
    candidates.sort(key=lambda c: -c[0])
    taken_new, taken_old = set(), set()
    matched: dict[str, tuple] = {}
    for overlap, newcomer, departed in candidates:
        if newcomer in taken_new or departed in taken_old:
            continue
        taken_new.add(newcomer)
        taken_old.add(departed)
        matched[newcomer] = (departed, overlap)
    pairs = []
    for newcomer in joined:
        new_p = after["by_name"].get(newcomer)
        if not new_p:
            continue
        departed, overlap = matched.get(newcomer, (None, 0))
        old_p = before["by_name"].get(departed) if departed else None
        pairs.append(_pair_verdict(new_p, old_p, overlap))

    thin = after["era"]["maps"] < min_maps or before["era"]["maps"] < min_maps
    return {
        "from": before["era"]["players"],
        "to": after["era"]["players"],
        "at": after["era"]["from"].isoformat() if after["era"]["from"] else None,
        "left": left,
        "joined": joined,
        "maps_before": before["era"]["maps"],
        "maps_after": after["era"]["maps"],
        "mean_fit_before": before["mean_fit"],
        "mean_fit_after": after["mean_fit"],
        "fit_delta": (
            round(after["mean_fit"] - before["mean_fit"], 2)
            if before["mean_fit"] is not None and after["mean_fit"] is not None
            else None
        ),
        "jobs_lost": lost_jobs,
        "jobs_unverifiable": unverifiable,
        "jobs_gained": gained_jobs,
        "pairs": pairs,
        "thin": thin,
        "verdict": _change_verdict(
            lost_jobs, unverifiable, pairs, before["mean_fit"], after["mean_fit"], thin
        ),
    }


def _pair_verdict(new_p: dict, old_p: dict | None, overlap: int) -> dict:
    """One arrival against the man whose job he took."""
    row = {
        "joined": new_p["name"],
        "replaced": old_p["name"] if old_p else None,
        "role_overlap_sides": overlap if overlap > 0 else 0,
        "new_roles": {s: v["label"] for s, v in new_p["roles"].items() if v["role"]},
        "old_roles": (
            {s: v["label"] for s, v in old_p["roles"].items() if v["role"]} if old_p else {}
        ),
        "new_rating": new_p["rating"],
        "old_rating": old_p["rating"] if old_p else None,
        "sides": [],
    }
    if old_p:
        for side in ("t", "ct"):
            nf, of = new_p["fit"].get(side), old_p["fit"].get(side)
            if not nf or not of or nf.get("score") is None or of.get("score") is None:
                continue
            same_role = new_p["roles"][side]["role"] == old_p["roles"][side]["role"]
            row["sides"].append(
                {
                    "side": side,
                    "new_role": new_p["roles"][side]["label"],
                    "old_role": old_p["roles"][side]["label"],
                    "same_role": same_role,
                    "new_score": nf["score"],
                    "old_score": of["score"],
                    "delta": round(nf["score"] - of["score"], 2),
                    # Only comparable inside one cohort.
                    "comparable": same_role,
                }
            )
    if row["new_rating"] is not None and row["old_rating"] is not None:
        row["rating_delta"] = round(row["new_rating"] - row["old_rating"], 2)
    else:
        row["rating_delta"] = None
    return row


def _change_verdict(lost_jobs, unverifiable, pairs, before_fit, after_fit, thin) -> str:
    """The sentence a coach reads first.

    A rating delta between two men in *different* roles is two numbers from two
    cohorts, so it is worded as a change of role, never as an upgrade.
    """
    bits = []
    departures = [j for j in lost_jobs if j["cause"] == "departure"]
    drifts = [j for j in lost_jobs if j["cause"] == "drift"]
    if departures:
        jobs = ", ".join(f"{j['label']} on {j['side'].upper()}" for j in departures)
        bits.append(f"no one now fills: {jobs}")
    for job in drifts:
        who = ", ".join(
            f"{d['name']} now reads as {d['now'].lower()}"
            if d["now"]
            else f"{d['name']} is now unclassified"
            for d in job["drifted"]
        )
        bits.append(
            f"{job['label']} on {job['side'].upper()} is no longer covered — "
            f"not because anyone left, but because {who}"
        )
    for p in pairs:
        delta = p["rating_delta"]
        if delta is None or abs(delta) <= 0.2:
            continue
        if any(s["comparable"] for s in p["sides"]):
            bits.append(f"{p['joined']} rates {delta:+.2f} on {p['replaced']}")
        else:
            bits.append(
                f"{p['joined']} took a different job from {p['replaced']} "
                f"({_role_phrase(p['old_roles'])} → {_role_phrase(p['new_roles'])}), "
                f"and rates {delta:+.2f} in it"
            )
    if before_fit is not None and after_fit is not None:
        bits.append(f"lineup fit {before_fit:+.2f} → {after_fit:+.2f}")
    if not bits:
        return "No measurable change in role coverage or fit."
    sentence = "; ".join(bits) + "."
    if unverifiable:
        jobs = ", ".join(f"{j['label']} on {j['side'].upper()}" for j in unverifiable)
        sentence += (
            f" Cannot tell whether the new lineup still fills {jobs} — "
            "too few rounds on that side since the change."
        )
    if thin:
        sentence += " Too few maps on one side of the change to trust this."
    return sentence


def _side_rounds(picture: dict) -> dict[str, int]:
    """Rounds the lineup actually played on each side, for sample guards."""
    out: dict[str, int] = defaultdict(int)
    for player in picture["players"]:
        for side, bucket in player["sides"].items():
            out[side] = max(out[side], bucket.get("rounds", 0))
    return dict(out)


# ------------------------------------------------------------ report entry ---
def build_role_report(
    my_team: Team,
    opponent: Team,
    my_maps: Iterable[MatchMap],
    opp_maps: Iterable[MatchMap],
    pool: Iterable[MatchMap] | None = None,
) -> dict:
    """The role section of a scouting report, for both teams at once.

    The baseline and the cohorts are built once from every parsed map and then
    shared: two teams scored against two different baselines cannot be put on
    the same page. ``pool`` defaults to every parsed map, because a five-man
    pool makes the top man an "entry fragger" by construction.
    """
    my_maps, opp_maps = list(my_maps), list(opp_maps)
    if pool is None:
        pool = list(
            db()
            .scalars(
                select(MatchMap)
                .where(MatchMap.parsed_at.is_not(None))
                .options(joinedload(MatchMap.match), joinedload(MatchMap.game_map))
            )
            .unique()
        )
    else:
        pool = list(pool)
    if not pool:
        return {"available": False, "note": "No parsed maps, so no roles could be read."}

    baseline = league_baseline(pool)
    cohorts = role_cohorts(pool, baseline)

    section = {"available": True, "pool_maps": len(pool), "roles": role_glossary()}
    for key, team, maps in (("my_team", my_team, my_maps), ("opponent", opponent, opp_maps)):
        if not maps:
            section[key] = {
                "team": team.name,
                "available": False,
                "note": f"No parsed maps for {team.name}.",
            }
            continue
        picture = rate_team(team, maps, baseline=baseline, cohorts=cohorts)
        section[key] = {
            "team": team.name,
            "available": True,
            "maps": len(maps),
            "players": [_slim_player(p) for p in picture["players"]],
            "coverage": picture["coverage"],
            "current_lineup": picture["current_lineup"],
            "best": [p["name"] for p in picture["best"]],
            "worst": [p["name"] for p in picture["worst"]],
            "changes": roster_change_report(team, maps, baseline=baseline, cohorts=cohorts)[
                "changes"
            ],
            "moves": role_moves(picture, baseline),
            "leaks": position_leaks(team, maps),
            "routes": route_advice(team, maps),
        }
    return section


def _slim_player(player: dict) -> dict:
    """A player row trimmed to what a reader needs."""
    sides = {}
    for side, verdict in player["roles"].items():
        bucket = player["sides"][side]
        fit = player.get("fit", {}).get(side) or {}
        sides[side] = {
            "role": verdict["role"],
            "label": verdict["label"],
            "confidence": verdict["confidence"],
            "rounds": bucket["rounds"],
            "evidence": verdict["evidence"],
            "runner_up": verdict["runner_up"],
            "fit_score": fit.get("score"),
            "fit_verdict": fit.get("verdict"),
            "cohort_size": fit.get("cohort_size"),
            "kpis": fit.get("kpis", []),
            "weakest": fit.get("weakest"),
            "strongest": fit.get("strongest"),
        }
    return {
        "player_id": player["player_id"],
        "name": player["name"],
        "rating": player["rating"],
        "rounds": player["overall"]["rounds"],
        "adr": player["overall"]["adr"],
        "kd_ratio": player["overall"]["kd_ratio"],
        "in_current_lineup": player.get("in_current_lineup", True),
        "summary": player["summary"],
        "sides": sides,
    }
