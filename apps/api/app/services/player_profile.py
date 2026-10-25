"""One Player's profile for the v2 pages (screen 04).

His numbers over the Match Maps he played, set against every Player of the Pool
with :data:`MIN_ROUNDS` Rounds or more: seven axes (firepower, entry, trade,
utility, clutch, survival, opening), each the mean of where his component
numbers stand among them (0-100); his Player rating Map by Map and per Side;
his aim (PL-5); his duels by distance and by the Round's clock; where he killed
and died on one Map and Side; his guns. The Pool's lines are computed once per
parse (``pool_cache``) under the scope the request had before it asked for
Scrims, so a Scrim never enters them (docs/adr/0010).

Bind a session with ``dbctx.using``.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import Integer, and_, cast, func, select

from app.models import (
    DamageEvent,
    KillEvent,
    MapRoster,
    Match,
    MatchKind,
    MatchMap,
    Player,
    PlayerMap,
    PlayerMapUtility,
    PlayerRound,
    Round,
)
from app.services import aim, pool_cache, radar, review_pool
from app.services import scope as visibility
from app.services.analysis_store import weapon_family
from app.services.dbctx import db
from app.services.demo_parser import TRADE_SECONDS
from app.services.player_rating import Line, per_map, rating

POOL_SCHEMA = 1
MIN_ROUNDS = 100
AXES = ("firepower", "entry", "trade", "utility", "clutch", "survival", "opening")
# Each axis is the mean percentile of these per-Round numbers (higher is better).
AXIS_PARTS = {
    "firepower": ("kpr", "adr", "multi"),
    "entry": ("entries",),
    "trade": ("trade_kpr",),
    "utility": ("util_dmg", "flash_assists"),
    "clutch": ("clutch",),
    "survival": ("survival",),
    "opening": ("opening",),
}
FORM = 20
# Duels by how far apart (the kill feed's distance, in metres) and when in the Round.
NEAR, FAR = 10.0, 25.0
EARLY, LATE = 30.0, 60.0
WEAPON_NAMES = {
    "ak47": "AK-47", "m4a1": "M4A4 / M4A1-S", "awp": "AWP", "usp/p2000": "USP-S / P2000",
    "glock": "Glock-18", "galilar": "Galil AR", "deagle": "Desert Eagle",
    "famas": "FAMAS", "mp9": "MP9", "mac10": "MAC-10", "tec9": "Tec-9", "fiveseven": "Five-SeveN",
    "p250": "P250", "hkp2000": "P2000", "cz75a": "CZ75-Auto", "ssg08": "SSG 08", "mp7": "MP7",
    "ump45": "UMP-45", "p90": "P90", "hegrenade": "HE", "inferno": "Molotov", "sg556": "SG 553",
    "aug": "AUG", "elite": "Dual Berettas", "revolver": "R8", "mag7": "MAG-7", "xm1014": "XM1014",
    "nova": "Nova", "knife": "Knife",
}  # fmt: skip


# ------------------------------------------------------------------ the numbers


def _raw(map_ids: list[int], player_ids: Iterable[int] | None = None) -> dict[int, dict]:
    """Per Player, the sums every axis and KPI is read from, over these Match Maps."""
    session = db()
    if not map_ids:
        return {}
    wanted = set(player_ids) if player_ids is not None else None
    out: dict[int, dict] = defaultdict(lambda: defaultdict(float))
    q = (
        select(
            PlayerRound.player_id,
            PlayerRound.round_id,
            PlayerRound.team_id,
            PlayerRound.kills,
            PlayerRound.deaths,
            PlayerRound.assists,
            PlayerRound.damage,
            PlayerRound.kast,
            PlayerRound.survived,
            PlayerRound.traded,
            PlayerRound.opening_kill,
            PlayerRound.opening_death,
        )
        .join(Round, Round.id == PlayerRound.round_id)
        .where(Round.match_map_id.in_(map_ids))
    )
    teams: dict[int, dict[int, int]] = defaultdict(dict)
    for pid, rid, tid, k, d, a, dmg, kast, surv, traded, ok, od in session.execute(q):
        teams[rid][pid] = tid
        if wanted is not None and pid not in wanted:
            continue
        o = out[pid]
        o["rounds"] += 1
        o["kills"] += k
        o["deaths"] += d
        o["assists"] += a
        o["damage"] += dmg
        o["kast"] += 1 if kast else 0
        o["survived"] += 1 if surv else 0
        o["traded_deaths"] += 1 if (d and traded) else 0
        o["died"] += 1 if d else 0
        o["ok"] += 1 if ok else 0
        o["od"] += 1 if od else 0
        o["multi"] += 1 if k >= 2 else 0
    for pid, fa, fire, he in session.execute(
        select(
            PlayerMapUtility.player_id,
            func.sum(PlayerMapUtility.flash_assists),
            func.sum(PlayerMapUtility.fire_damage),
            func.sum(PlayerMapUtility.he_damage),
        )
        .where(PlayerMapUtility.match_map_id.in_(map_ids))
        .group_by(PlayerMapUtility.player_id)
    ):
        if pid in out:
            out[pid]["flash_assists"] += float(fa or 0)
            out[pid]["util_damage"] += float(fire or 0) + float(he or 0)
    for pid, hs in session.execute(
        select(PlayerMap.player_id, func.sum(PlayerMap.headshots))
        .where(PlayerMap.match_map_id.in_(map_ids))
        .group_by(PlayerMap.player_id)
    ):
        if pid in out:
            out[pid]["headshots"] += float(hs or 0)
    _sequences(map_ids, teams, out)
    return {pid: dict(v) for pid, v in out.items()}


def _sequences(map_ids: list[int], teams: dict[int, dict[int, int]], out: dict) -> None:
    """Trade kills and clutches, read off each Round's kills in order."""
    session = db()
    rates = dict(
        session.execute(
            select(MatchMap.id, MatchMap.tickrate).where(MatchMap.id.in_(map_ids))
        ).all()
    )
    winners = dict(
        session.execute(
            select(Round.id, Round.winner_team_id).where(Round.match_map_id.in_(map_ids))
        ).all()
    )
    by_round: dict[int, list] = defaultdict(list)
    for rid, mm, tick, attacker, victim in session.execute(
        select(KillEvent.round_id, Round.match_map_id, KillEvent.tick, KillEvent.attacker_id,
               KillEvent.victim_id)
        .join(Round, Round.id == KillEvent.round_id)
        .where(Round.match_map_id.in_(map_ids))
        .order_by(KillEvent.round_id, KillEvent.tick)
    ):  # fmt: skip
        by_round[rid].append((tick, attacker, victim, rates.get(mm) or 64))
    for rid, seq in by_round.items():
        team = teams.get(rid, {})
        for i, (tick, attacker, victim, rate) in enumerate(seq):
            if attacker is None or attacker not in out:
                continue
            for ptick, pattacker, pvictim, _r in reversed(seq[:i]):
                if tick - ptick > TRADE_SECONDS * rate:
                    break
                if pattacker == victim and team.get(pvictim) == team.get(attacker):
                    out[attacker]["trade_kills"] += 1
                    break
        alive = set(team)
        seen: set[int] = set()
        for _tick, _attacker, victim, _rate in seq:
            alive.discard(victim)
            for tid in set(team.values()):
                mine = [p for p in alive if team[p] == tid]
                if len(mine) == 1 and any(team[p] != tid for p in alive) and mine[0] not in seen:
                    seen.add(mine[0])
                    if mine[0] in out:
                        out[mine[0]]["clutch_of"] += 1
                        out[mine[0]]["clutch_won"] += 1 if winners.get(rid) == tid else 0


def derive(r: dict) -> dict:
    """The per-Round numbers and KPIs from one Player's sums."""
    n = r.get("rounds") or 0
    if not n:
        return {}
    g = r.get
    duels = g("ok", 0) + g("od", 0)
    line = rating(int(n), int(g("kills", 0)), int(g("deaths", 0)), int(g("assists", 0)),
                  int(g("damage", 0)), 100.0 * g("kast", 0) / n)  # fmt: skip
    return {
        "rounds": int(n),
        "rating": round(line, 3),
        "kpr": g("kills", 0) / n,
        "adr": g("damage", 0) / n,
        "multi": g("multi", 0) / n,
        "entries": duels / n,
        "trade_kpr": g("trade_kills", 0) / n,
        "util_dmg": g("util_damage", 0) / n,
        "flash_assists": g("flash_assists", 0) / n,
        # Pulled toward a quarter won by four tries' worth, so one won clutch is not a talent.
        "clutch": (g("clutch_won", 0) + 1) / (g("clutch_of", 0) + 4),
        "survival": g("survived", 0) / n,
        "opening": (g("ok", 0) + 2) / (duels + 4),
        "kast": 100.0 * g("kast", 0) / n,
        "hs": 100.0 * g("headshots", 0) / g("kills") if g("kills") else None,
        "opening_pct": 100.0 * g("ok", 0) / duels if duels else None,
        "traded_pct": 100.0 * g("traded_deaths", 0) / g("died") if g("died") else None,
        "clutch_won": int(g("clutch_won", 0)),
        "clutch_of": int(g("clutch_of", 0)),
    }


def pool() -> dict[str, dict]:
    """Every Pool Player's derived numbers, by Player id (as a string: JSON keys)."""
    key = f"v2:players:v{POOL_SCHEMA}:{pool_cache.parse_stamp()}{visibility.cache_part(db())}"

    def compute():
        ids = list(
            db().scalars(
                select(MatchMap.id)
                .join(Match, Match.id == MatchMap.match_id)
                .where(MatchMap.parsed_at.is_not(None), Match.kind != MatchKind.SCRIM)
            )
        )
        raw = _raw(ids)
        return {str(pid): derive(r) for pid, r in raw.items() if r.get("rounds", 0) >= MIN_ROUNDS}

    return pool_cache.remember(key, compute)


def axes(mine: dict, population: dict[str, dict]) -> dict[str, float | None]:
    """Where each of ``mine``'s axes stands among the Pool's Players, 0-100."""
    out: dict[str, float | None] = {}
    others = list(population.values())
    for axis, parts in AXIS_PARTS.items():
        scores = []
        for part in parts:
            if mine.get(part) is None:
                continue
            values = [o[part] for o in others if o.get(part) is not None]
            if values:
                below = sum(1 for v in values if v < mine[part])
                same = sum(1 for v in values if v == mine[part])
                scores.append(100.0 * (below + same / 2) / len(values))
        out[axis] = round(sum(scores) / len(scores)) if scores else None
    return out


def median(population: dict[str, dict], key: str) -> float | None:
    values = [o[key] for o in population.values() if o.get(key) is not None]
    return statistics.median(values) if values else None


# ------------------------------------------------------------------ the page


def maps_of(player_id: int) -> list[MatchMap]:
    """The Match Maps he played that this session sees, oldest first."""
    from sqlalchemy.orm import joinedload

    return list(
        db()
        .scalars(
            select(MatchMap)
            .join(MapRoster, MapRoster.match_map_id == MatchMap.id)
            .join(Match, Match.id == MatchMap.match_id)
            .where(MapRoster.player_id == player_id, MatchMap.parsed_at.is_not(None))
            .options(
                joinedload(MatchMap.match),
                joinedload(MatchMap.game_map),
                joinedload(MatchMap.team1),
                joinedload(MatchMap.team2),
            )  # fmt: skip
            .order_by(Match.played_at, MatchMap.map_number)
        )
        .unique()
    )


def form(player: Player, maps: list[MatchMap]) -> dict:
    """His Player rating on his last Maps, and by kind and Side."""
    lines = per_map(m.id for m in maps)
    rows = []
    for m in maps:
        got = lines.get((m.id, player.id))
        if not got:
            continue
        line, team_id = got
        opp = m.team2 if m.team1_id == team_id else m.team1
        rows.append(
            {
                "match_id": m.match_id,
                "map_number": m.map_number,
                "map": m.game_map.name if m.game_map else "?",
                "played_at": m.match.played_at,
                "opponent": opp.name if opp else m.match.opponent_label,
                "scrim": m.match.kind == MatchKind.SCRIM,
                "won": m.winner_id == team_id if m.winner_id and team_id else None,
                "rating": round(line.rating or 0, 3),
            }
        )
    official, scrim = Line(), Line()
    for m in maps:
        got = lines.get((m.id, player.id))
        if got:
            (scrim if m.match.kind == MatchKind.SCRIM else official).merge(got[0])
    last = [r["rating"] for r in rows[-FORM:]]
    return {
        "maps": rows[-FORM:],
        "sigma": round(statistics.pstdev(last), 3) if len(last) >= 3 else None,
        "official": round(official.rating, 3) if official.rating is not None else None,
        "scrim": round(scrim.rating, 3) if scrim.rating is not None else None,
        **_sides(player.id, [m.id for m in maps]),
    }


def _sides(player_id: int, map_ids: list[int]) -> dict:
    out = {"t": None, "ct": None}
    if not map_ids:
        return out
    rows = db().execute(
        select(
            PlayerRound.side,
            func.count(),
            func.sum(PlayerRound.kills),
            func.sum(PlayerRound.deaths),
            func.sum(PlayerRound.assists),
            func.sum(PlayerRound.damage),
            func.sum(cast(PlayerRound.kast, Integer)),
        )
        .join(Round, Round.id == PlayerRound.round_id)
        .where(PlayerRound.player_id == player_id, Round.match_map_id.in_(map_ids))
        .group_by(PlayerRound.side)
    )
    for side, n, k, d, a, dmg, kast in rows:
        if side in out and n:
            out[side] = round(rating(n, int(k or 0), int(d or 0), int(a or 0), int(dmg or 0),
                                     100.0 * float(kast or 0) / n), 3)  # fmt: skip
    return out


def duel_grid(player_id: int, map_ids: list[int]) -> list[dict]:
    """His duels with an enemy, won or lost, by distance and the Round's clock."""
    if not map_ids:
        return []
    session = db()
    cells: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    q = (
        select(KillEvent.attacker_id, KillEvent.distance, KillEvent.tick, Round.freeze_end_tick,
               MatchMap.tickrate)
        .join(Round, Round.id == KillEvent.round_id)
        .join(MatchMap, MatchMap.id == Round.match_map_id)
        .where(
            Round.match_map_id.in_(map_ids),
            KillEvent.attacker_side != KillEvent.victim_side,
            KillEvent.attacker_id.is_not(None),
            (KillEvent.attacker_id == player_id) | (KillEvent.victim_id == player_id),
        )
    )  # fmt: skip
    for attacker, distance, tick, freeze, rate in session.execute(q):
        if distance is None:
            continue
        span = "near" if distance < NEAR else "far" if distance > FAR else "mid"
        t = (tick - freeze) / (rate or 64)
        phase = "early" if t < EARLY else "mid" if t < LATE else "late"
        cell = cells[(span, phase)]
        cell[0 if attacker == player_id else 1] += 1
    return [
        {"distance": span, "phase": phase, "won": w, "lost": lost}
        for (span, phase), (w, lost) in cells.items()
    ]


def positions(player_id: int, maps: list[MatchMap], map_name: str | None, side: str) -> dict:
    """Where he killed and died on one Map and Side, as shares of its radar."""
    counts: dict[str, int] = defaultdict(int)
    for m in maps:
        if m.game_map:
            counts[m.game_map.name] += 1
    choices = sorted(counts, key=lambda k: -counts[k])
    chosen = map_name if map_name in counts else (choices[0] if choices else None)
    out = {"maps": [{"map": k, "n": counts[k]} for k in choices], "map": chosen, "side": side,
           "url": None, "kills": [], "deaths": []}  # fmt: skip
    plate = radar.plate(chosen) if chosen else None
    if not plate:
        return out
    out["url"] = plate["url"]
    x0, x1, y0, y1 = plate["extent"]
    ids = [m.id for m in maps if m.game_map and m.game_map.name == chosen]
    rows = db().execute(
        select(KillEvent.attacker_id, KillEvent.attacker_x, KillEvent.attacker_y,
               KillEvent.victim_id, KillEvent.victim_x, KillEvent.victim_y, KillEvent.attacker_side,
               KillEvent.victim_side)
        .join(Round, Round.id == KillEvent.round_id)
        .where(Round.match_map_id.in_(ids or [0]),
               (KillEvent.attacker_id == player_id) | (KillEvent.victim_id == player_id))
    )  # fmt: skip

    def at(x, y):
        return [round((x - x0) / (x1 - x0), 4), round((y1 - y) / (y1 - y0), 4)]

    for attacker, ax, ay, victim, vx, vy, aside, vside in rows:
        if aside == vside:
            continue
        if attacker == player_id and aside == side and ax is not None:
            out["kills"].append(at(ax, ay))
        if victim == player_id and vside == side and vx is not None:
            out["deaths"].append(at(vx, vy))
    return out


def weapons(player_id: int, map_ids: list[int]) -> list[dict]:
    """His kills by gun, with headshots, distance and damage per Round."""
    if not map_ids:
        return []
    session = db()
    rounds = session.scalar(
        select(func.count())
        .select_from(PlayerRound)
        .join(Round, Round.id == PlayerRound.round_id)
        .where(PlayerRound.player_id == player_id, Round.match_map_id.in_(map_ids))
    ) or 0  # fmt: skip
    # The damage feed names the M4s and the USP/P2000 alike: count by family.
    kills: dict[str, list[float]] = defaultdict(lambda: [0, 0, 0.0, 0])
    for weapon, hs, distance in session.execute(
        select(KillEvent.weapon, KillEvent.headshot, KillEvent.distance)
        .join(Round, Round.id == KillEvent.round_id)
        .where(Round.match_map_id.in_(map_ids), KillEvent.attacker_id == player_id,
               KillEvent.attacker_side != KillEvent.victim_side)
    ):  # fmt: skip
        k = kills[weapon_family(weapon)]
        k[0] += 1
        k[1] += 1 if hs else 0
        if distance is not None:
            k[2] += distance
            k[3] += 1
    damage: dict[str, float] = defaultdict(float)
    for weapon, dmg in session.execute(
        select(DamageEvent.weapon, func.sum(DamageEvent.damage))
        .join(Round, Round.id == DamageEvent.round_id)
        .where(Round.match_map_id.in_(map_ids), DamageEvent.attacker_id == player_id,
               DamageEvent.attacker_side != DamageEvent.victim_side)
        .group_by(DamageEvent.weapon)
    ):  # fmt: skip
        damage[weapon_family(weapon)] += float(dmg or 0)
    total = sum(k[0] for k in kills.values()) or 1
    out = [
        {
            "weapon": WEAPON_NAMES.get(w, w),
            "kills": int(n),
            "hs": round(100.0 * hs / n, 1) if n else None,
            "distance": round(dsum / dn, 1) if dn else None,
            "share": round(100.0 * n / total, 1),
            "dpr": round(damage.get(w, 0.0) / rounds, 1) if rounds else None,
        }
        for w, (n, hs, dsum, dn) in kills.items()
    ]
    out.sort(key=lambda r: -r["kills"])
    return out[:8]


def mechanics(sid: str, map_ids: set[int]) -> dict | None:
    """His aim (PL-5) beside the median of every Player past the bar."""
    got = aim.player(sid, map_ids)
    if not got:
        return None
    data = review_pool.data()
    others = [aim.summarise(list(maps.values())) for maps in data.aims.values()]
    others = [o for o in others if o and o["engagements"] >= aim.MIN_ENGAGEMENTS]
    medians = {}
    for key in ("ttd_ms", "xhair_deg", "counter_strafe_pct", "first_hit_pct"):
        values = [o[key] for o in others if o[key] is not None]
        medians[key] = statistics.median(values) if values else None
    return {**got, "medians": medians}


def teammates(team_id: int, exclude: int) -> list[Player]:
    """The Team's five on its latest parsed Match Map, but him."""
    latest = db().scalar(
        select(MatchMap.id)
        .join(Match, Match.id == MatchMap.match_id)
        .join(MapRoster, and_(MapRoster.match_map_id == MatchMap.id, MapRoster.team_id == team_id))
        .where(MatchMap.parsed_at.is_not(None))
        .order_by(Match.played_at.desc(), MatchMap.map_number.desc())
        .limit(1)
    )
    if latest is None:
        return []
    return list(
        db().scalars(
            select(Player)
            .join(MapRoster, MapRoster.player_id == Player.id)
            .where(
                MapRoster.match_map_id == latest, MapRoster.team_id == team_id, Player.id != exclude
            )  # fmt: skip
            .order_by(Player.name)
        )
    )
