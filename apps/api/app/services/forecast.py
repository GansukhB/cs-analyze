"""Forecasts (CONTEXT.md: Forecast): how likely a Team is to beat another, Map by
Map and over a series, and what the veto does to it (docs/plans/03 FC-2, FC-3).

A Map's chance comes from the two Ratings (:mod:`app.services.rating`), turned
from a series into one Map (a Bo3 near even moves 1.5 times as far as one Map,
:data:`MAP_TO_SERIES`), plus each Team's offset on that Map: how far its stored
Match Maps there ran ahead of or behind what its Rating said at the time, pulled
toward zero by ``n/(n + OFFSET_N0)``. Maps are taken as independent, so a series
is the chance of winning most of them.

The veto is played out exactly in Valve's Major order (:data:`VETO`): ``minimax``
when both Teams ban and pick by these chances, ``expected`` when the opponent
bans and picks by how often it plays each Map and by its chances there (a soft
choice, :func:`_their_policy`) and we answer it best. Veto records would make the
expected line far better; they wait for HLTV's match pages (DATA-2).

Every number carries how far to trust it: how often past forecasts in its band
came true (``reliability`` in ``rating_params.json``) and its data limits (a Team
with few series, a Rating not moved for months, no Match Maps on a Map).
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cache, lru_cache

from sqlalchemy import select

from app.models import GameMap, Match, MatchMap, Team, TeamAlias
from app.services import map_pool, rating, stats
from app.services.dbctx import db, memo

MAP_TO_SERIES = 1.5
# A Map's chance moves ~4.1 times as far as its Round chance near even (MR12 with
# overtime, Rounds independent: 0.55 a Round is 0.706 a Map).
ROUND_TO_MAP = 4.1
OFFSET_N0 = 8.0  # Match Maps on a Map before its offset counts half
OFFSET_CAP = 0.6  # the most an offset moves a Map's logit
OFFSET_HALF_LIFE = 180.0  # days
MIN_MAPS_CHECKED = 200  # stored Match Maps the offsets must be checked on before they count
COLD_SERIES = 10  # fewer series than this and a Rating is still finding its level
STALE_DAYS = 90  # a Rating no series has moved for this long is old news
SHARE_DAYS = 180  # how far back "how often they play a Map" looks
FORMATS = {"bo1": 1, "bo3": 3, "bo5": 5}

# Valve's Major veto for a seven-Map pool: (who, what). "a" starts.
VETO = {
    "bo1": [("a", "ban"), ("a", "ban"), ("b", "ban"), ("b", "ban"), ("b", "ban"), ("a", "ban")],
    "bo3": [("a", "ban"), ("b", "ban"), ("a", "pick"), ("b", "pick"), ("a", "ban"), ("b", "ban")],
    "bo5": [("a", "ban"), ("b", "ban"), ("a", "pick"), ("b", "pick"), ("a", "pick"), ("b", "pick")],
}


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def map_slope() -> float:
    return rating.params().calibration / MAP_TO_SERIES


# ------------------------------------------------------------- the Teams ---
@dataclass(frozen=True)
class Standing:
    """A Team's Rating as the Forecast uses it, with what limits it."""

    name: str  # the name its results go under
    rating: float
    series: int
    last: date | None
    region: str | None = None
    lineup_changed: bool = False

    @property
    def cold(self) -> bool:
        return self.series < COLD_SERIES

    def stale(self, today: date) -> bool:
        return self.last is None or (today - self.last).days > STALE_DAYS


def _names(team: Team) -> list[str]:
    aliases = db().scalars(select(TeamAlias.clan_name).where(TeamAlias.team_id == team.id))
    return [team.name, *aliases]


def standing(team: Team, lineup: list[str] | None = None) -> Standing | None:
    """``team``'s Rating, under whichever of its names has the most results.

    With a ``lineup`` (Player names) that keeps fewer than three of the five its
    results were won with, the Rating is where those Players stood instead
    (CONTEXT.md, Rating), when at least three of them are known."""
    snap = rating.current()
    found = [(n, snap.teams.get(rating._key(n))) for n in _names(team)]
    found = [(n, t) for n, t in found if t is not None]
    if not found:
        return None
    name, t = max(found, key=lambda f: f[1].series)
    region = snap.regions.get(rating._key(name))
    p = rating.params()
    picked = {n.casefold() for n in lineup or [] if n}
    if len(picked) >= p.keep_core and t.roster and len(picked & t.roster) < p.keep_core:
        known = [snap.players[n] for n in picked if n in snap.players]
        if len(known) >= p.keep_core:
            mean = sum(known) / len(known)
            return Standing(name, mean, t.series, t.last, region, lineup_changed=True)
    return Standing(name, t.rating, t.series, t.last, region)


# ----------------------------------------------------------- Map offsets ---
def _stored_maps() -> list[tuple]:
    """Every stored Match Map with both Teams and a winner:
    (date, map, t1, t2, winner, t1 rounds, t2 rounds)."""

    def load():
        rows = (
            db()
            .execute(
                select(
                    Match.played_at,
                    GameMap.name,
                    MatchMap.team1_id,
                    MatchMap.team2_id,
                    MatchMap.winner_id,
                    MatchMap.team1_score,
                    MatchMap.team2_score,
                )
                .join(Match, Match.id == MatchMap.match_id)
                .join(GameMap, GameMap.id == MatchMap.game_map_id)
                .where(
                    MatchMap.team1_id.is_not(None),
                    MatchMap.team2_id.is_not(None),
                    MatchMap.winner_id.is_not(None),
                    Match.played_at.is_not(None),
                )
                .order_by(Match.played_at, MatchMap.map_number)
            )
            .all()
        )
        return [(r[0].date(), *r[1:]) for r in rows]

    return memo(("forecast_maps",), load)


def _team_names() -> dict[int, str]:
    """Team id -> the name its results go under (the alias with most results)."""

    def load():
        snap = rating.current()
        names: dict[int, list[str]] = defaultdict(list)
        for team_id, name in db().execute(select(Team.id, Team.name)):
            names[team_id].append(name)
        for name, team_id in db().execute(select(TeamAlias.clan_name, TeamAlias.team_id)):
            names[team_id].append(name)
        out = {}
        for team_id, options in names.items():
            known = [
                (n, snap.teams[rating._key(n)].series)
                for n in options
                if rating._key(n) in snap.teams
            ]
            if known:
                out[team_id] = max(known, key=lambda k: k[1])[0]
        return out

    return memo(("forecast_team_names",), load)


def _region_gap(snap):
    """(name, name) -> the regions' offset between them, on one Map."""
    regions = rating.regions()

    def between(a: str, b: str) -> float:
        ra, rb = snap.regions.get(rating._key(a)), snap.regions.get(rating._key(b))
        if not (ra and rb) or ra == rb:
            return 0.0
        return (regions.get(ra, 0.0) - regions.get(rb, 0.0)) / MAP_TO_SERIES

    return between


@dataclass(frozen=True)
class Offset:
    value: float  # logit, shrunk
    n: float  # recency-weighted Match Maps
    raw: float  # mean (won - expected) over them


def offsets(
    team_id: int, before: date | None = None, today: date | None = None, by: str = "rounds"
) -> dict[str, Offset]:
    """``team_id``'s offset on each Map from its stored Match Maps (before ``before``)."""
    snap = rating.current()
    names = _team_names()
    today = today or date.today()
    slope = map_slope() * math.log(10) / rating.SCALE
    region_gap = _region_gap(snap)
    sums: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    me = names.get(team_id)
    if me is None:
        return {}
    for played, map_name, t1, t2, winner, s1, s2 in _stored_maps():
        if before is not None and played >= before:
            break
        if team_id not in (t1, t2):
            continue
        other = names.get(t2 if t1 == team_id else t1)
        mine, theirs = snap.before(me, played), snap.before(other, played) if other else None
        if mine is None or theirs is None:
            continue
        expected = _sigmoid(slope * (mine - theirs) + region_gap(me, other))
        w = stats.recency((today - played).days, OFFSET_HALF_LIFE)
        won = 1.0 if winner == team_id else 0.0
        if by == "rounds" and (s1 or 0) + (s2 or 0) > 0:
            # The Round share says more than the result: as a Map share, near even.
            share = (s1 if t1 == team_id else s2) / (s1 + s2)
            resid = (share - 0.5) * ROUND_TO_MAP + 0.5 - expected
        else:
            resid = won - expected
        sums[map_name][0] += w * resid
        sums[map_name][1] += w
    out = {}
    for map_name, (resid, n) in sums.items():
        raw = resid / n if n else 0.0
        shrunk = n / (n + OFFSET_N0) * 4.0 * raw  # a share near even, as a logit
        out[map_name] = Offset(max(-OFFSET_CAP, min(OFFSET_CAP, shrunk)), round(n, 2), raw)
    return out


def gap(a: Standing, b: Standing) -> float:
    """``a``'s edge over ``b`` on a series, as a logit: the calibrated Rating gap
    plus the two regions' offsets (FC-2)."""
    regions = rating.regions()
    edge = rating.params().calibration * (a.rating - b.rating) * math.log(10) / rating.SCALE
    if a.region and b.region and a.region != b.region:
        edge += regions.get(a.region, 0.0) - regions.get(b.region, 0.0)
    return edge


def map_chance(series_gap: float, my_off: float = 0.0, their_off: float = 0.0) -> float:
    """Our chance on one Map, from the series edge and both Teams' offsets there."""
    return _sigmoid(series_gap / MAP_TO_SERIES + my_off - their_off)


def offsets_help() -> bool:
    """Whether the offsets beat the Rating alone on the stored Match Maps, checked
    walk-forward by ``npm run forecast:backtest`` (``maps`` in rating_params.json)."""
    check = _committed().get("maps") or {}
    plain, shifted = check.get("rating_only") or {}, check.get("with_offsets") or {}
    return plain.get("n", 0) >= MIN_MAPS_CHECKED and shifted.get("log_loss", math.inf) < plain.get(
        "log_loss", -math.inf
    )


# ------------------------------------------------------------- the series ---
def series_chance(ps: list[float], best_of: int) -> float:
    """The chance of winning most of ``best_of`` independent Maps."""
    need = best_of // 2 + 1
    dist = [1.0]  # dist[k]: chance of k wins so far
    for p in ps[:best_of]:
        nxt = [0.0] * (len(dist) + 1)
        for k, q in enumerate(dist):
            nxt[k + 1] += q * p
            nxt[k] += q * (1 - p)
        dist = nxt
    return sum(dist[need:])


def _their_policy(options: list[str], kind: str, p: dict[str, float], share: dict[str, float]):
    """How likely the opponent is to take each option: softly, by how often it plays
    the Map and by its own chance there (each counted once, on the log scale)."""
    utility = {m: math.log(share[m]) + math.log((1 - p[m]) / p[m]) for m in options}
    sign = 1.0 if kind == "pick" else -1.0
    top = max(sign * u for u in utility.values())
    weights = {m: math.exp(sign * utility[m] - top) for m in options}
    total = sum(weights.values())
    return {m: w / total for m, w in weights.items()}


def _solver(p: dict[str, float], share: dict[str, float], fmt: str, we_start: bool):
    """``value(left, played, i, mode)``: our series chance from step ``i`` on, with
    our best answer at our steps and, at theirs, their worst for us ("minimax")
    or their likely move ("expected")."""
    steps = VETO[fmt]
    best_of = FORMATS[fmt]
    us = "a" if we_start else "b"

    @cache
    def value(left: frozenset, played: tuple, i: int, mode: str) -> float:
        if i == len(steps):
            maps = list(played) + sorted(left)[: best_of - len(played)]
            return series_chance([p[m] for m in maps], best_of)
        who, kind = steps[i]
        options = sorted(left)

        def after(m):
            return value(left - {m}, played + ((m,) if kind == "pick" else ()), i + 1, mode)

        if who == us:
            return max(after(m) for m in options)
        if mode == "minimax":
            return min(after(m) for m in options)
        policy = _their_policy(options, kind, p, share)
        return sum(q * after(m) for m, q in policy.items())

    return value, steps, best_of, us


def _line(value, steps, us, p, share, left: frozenset, played: tuple, start: int) -> list:
    """From step ``start``: our best answer at each of our steps, their likeliest
    move at theirs."""
    line = []
    for i in range(start, len(steps)):
        who, kind = steps[i]
        options = sorted(left)
        if who == us:
            scored = []
            for m in options:
                nl, np_ = left - {m}, played + ((m,) if kind == "pick" else ())
                scored.append(
                    {
                        "map": m,
                        "expected": round(value(nl, np_, i + 1, "expected"), 4),
                        "minimax": round(value(nl, np_, i + 1, "minimax"), 4),
                    }
                )
            scored.sort(key=lambda r: (-r["expected"], -r["minimax"], r["map"]))
            choice = scored[0]["map"]
            line.append({"who": "mine", "kind": kind, "map": choice, "options": scored})
        else:
            policy = _their_policy(options, kind, p, share)
            choice = max(policy, key=lambda m: (policy[m], m))
            line.append(
                {"who": "theirs", "kind": kind, "map": choice, "chance": round(policy[choice], 3)}
            )
        left = left - {choice}
        if kind == "pick":
            played = played + (choice,)
    return line


def veto(p: dict[str, float], share: dict[str, float], fmt: str, we_start: bool) -> dict:
    """Play the veto out: our options at each of our steps, valued both ways."""
    return veto_from(p, share, fmt, we_start, [])


def veto_from(
    p: dict[str, float], share: dict[str, float], fmt: str, we_start: bool, done: list[str]
) -> dict:
    """The veto from where it stands, ``done`` the Maps taken at its first steps
    in order (GP-10): our chance now, every option at the next step valued, and
    the line played out from there."""
    value, steps, best_of, us = _solver(p, share, fmt, we_start)
    left, played = frozenset(p), ()
    for i, m in enumerate(done):
        if i >= len(steps) or m not in left:
            raise ValueError(f"step {i + 1}: {m} is not open")
        left = left - {m}
        if steps[i][1] == "pick":
            played = played + (m,)
    at = len(done)
    nxt = None
    if at < len(steps):
        who, kind = steps[at]
        options = []
        policy = _their_policy(sorted(left), kind, p, share) if who != us else {}
        for m in sorted(left):
            nl, np_ = left - {m}, played + ((m,) if kind == "pick" else ())
            options.append(
                {
                    "map": m,
                    "expected": round(value(nl, np_, at + 1, "expected"), 4),
                    "minimax": round(value(nl, np_, at + 1, "minimax"), 4),
                    "chance": round(policy[m], 3) if policy else None,
                }
            )
        options.sort(key=lambda r: (-r["expected"], r["map"]))
        nxt = {"who": "mine" if who == us else "theirs", "kind": kind, "options": options}
    line = _line(value, steps, us, p, share, left, played, at)
    projected_left, projected = left, played
    for step in line:
        projected_left = projected_left - {step["map"]}
        if step["kind"] == "pick":
            projected = projected + (step["map"],)
    decider = sorted(projected_left)[: best_of - len(projected)]
    return {
        "format": fmt,
        "we_start": we_start,
        "steps": [{"who": "mine" if w == us else "theirs", "kind": k} for w, k in steps],
        "done": list(done),
        "expected": round(value(left, played, at, "expected"), 4),
        "minimax": round(value(left, played, at, "minimax"), 4),
        "next": nxt,
        "line": line,
        "maps": list(projected) + decider,
        "decider": decider[0] if decider else None,
    }


def played(team_id: int, today: date | None = None) -> Counter:
    """How many stored Match Maps ``team_id`` played on each Map in the last SHARE_DAYS."""
    since = (today or date.today()) - timedelta(days=SHARE_DAYS)
    return Counter(
        m for day, m, t1, t2, *_ in _stored_maps() if team_id in (t1, t2) and since <= day
    )


def play_share(counts: Counter, maps: list[str]) -> dict[str, float]:
    """Each Map's share of ``counts``, smoothed by one Match Map each."""
    total = sum(counts[m] for m in maps)
    return {m: (counts[m] + 1) / (total + len(maps)) for m in maps}


# --------------------------------------------------------------- trusting ---
def _committed() -> dict:
    return _load_committed()


@lru_cache(maxsize=1)
def _load_committed() -> dict:
    if not rating.PARAMS_PATH.exists():
        return {}
    return json.loads(rating.PARAMS_PATH.read_text())


def reliability(p: float) -> dict | None:
    """How often past forecasts near ``p`` came true, from the backtest's bands
    (which are the favourite's): said from this side, ``p``'s."""
    fav = max(p, 1 - p)
    for band in _committed().get("reliability") or []:
        if band["lo"] <= fav < band["hi"] or (band["hi"] >= 1.0 and fav >= band["lo"]):
            if p >= 0.5:
                return dict(band)
            return {
                "lo": round(1 - band["hi"], 2),
                "hi": round(1 - band["lo"], 2),
                "n": band["n"],
                "won": round(1 - band["won"], 4),
                "low": round(1 - band["high"], 4),
                "high": round(1 - band["low"], 4),
            }
    return None


# --------------------------------------------------------------- the whole ---
def build(
    mine: Team,
    theirs: Team,
    *,
    my_lineup: list[str] | None = None,
    their_lineup: list[str] | None = None,
    today: date | None = None,
) -> dict:
    """The Fixture's Forecast: each Map, each format's veto, and its limits."""
    today = today or date.today()
    a, b = standing(mine, my_lineup), standing(theirs, their_lineup)
    limits = []
    for who, team, s in (("mine", mine, a), ("theirs", theirs, b)):
        if s is None:
            limits.append({"code": "unrated", "who": who, "team": team.name})
            continue
        if s.cold:
            limits.append({"code": "cold", "who": who, "team": team.name, "series": s.series})
        if s.stale(today):
            limits.append({"code": "stale", "who": who, "team": team.name, "last": s.last})
        if s.lineup_changed:
            limits.append({"code": "lineup", "who": who, "team": team.name})
    out = {
        "ratings": {
            "mine": _standing_json(a),
            "theirs": _standing_json(b),
        },
        "model": rating.params().version,
        "limits": limits,
        "maps": [],
        "series": {},
        "veto": {},
    }
    if a is None or b is None:
        return out

    pool = list(map_pool.active_duty())
    edge = gap(a, b)
    use_offsets = offsets_help()
    mine_off, theirs_off = offsets(mine.id, today=today), offsets(theirs.id, today=today)
    mine_n, theirs_n = played(mine.id, today), played(theirs.id, today)
    p = {}
    for m in pool:
        mo, to = mine_off.get(m), theirs_off.get(m)
        if use_offsets:
            p[m] = map_chance(edge, mo.value if mo else 0.0, to.value if to else 0.0)
        else:
            p[m] = map_chance(edge)
        out["maps"].append(
            {
                "map": m,
                "p": round(p[m], 4),
                # Shown only once they are shown to help (offsets_help).
                "offset_mine": round(mo.value, 3) if mo and use_offsets else None,
                "offset_theirs": round(to.value, 3) if to and use_offsets else None,
                "played_mine": mine_n[m],
                "played_theirs": theirs_n[m],
            }
        )
    out["maps"].sort(key=lambda r: (-r["p"], -r["played_mine"], r["map"]))
    out["series_edge"] = round(_sigmoid(edge), 4)
    out["even_map"] = round(map_chance(edge), 4)
    out["offsets_used"] = use_offsets
    if not use_offsets:
        check = _committed().get("maps") or {}
        limits.append(
            {
                "code": "maps_even",
                "n": (check.get("rating_only") or {}).get("n", 0),
                "rating_only": (check.get("rating_only") or {}).get("log_loss"),
                "with_offsets": (check.get("with_offsets") or {}).get("log_loss"),
            }
        )
    share = play_share(theirs_n, pool)
    for fmt, best_of in FORMATS.items():
        if use_offsets and len(pool) == 7:
            ours, theirs_first = veto(p, share, fmt, True), veto(p, share, fmt, False)
            out["veto"][fmt] = {"we_start": ours, "they_start": theirs_first}
            expected = (ours["expected"] + theirs_first["expected"]) / 2
            minimax = (ours["minimax"] + theirs_first["minimax"]) / 2
        else:
            expected = minimax = series_chance([map_chance(edge)] * best_of, best_of)
        out["series"][fmt] = {
            "expected": round(expected, 4),
            "minimax": round(minimax, 4),
            "reliability": reliability(expected),
        }
    return out


def _standing_json(s: Standing | None) -> dict | None:
    if s is None:
        return None
    return {
        "name": s.name,
        "rating": round(s.rating, 1),
        "series": s.series,
        "last": s.last,
        "cold": s.cold,
        "region": s.region,
        "lineup_changed": s.lineup_changed,
    }


# ---------------------------------------------------------------- checking ---
def check_maps() -> dict:
    """Score the Map model walk-forward on every stored Match Map: each one from
    the Ratings and offsets known before its day."""
    names = _team_names()
    snap = rating.current()
    slope = map_slope() * math.log(10) / rating.SCALE
    region_gap = _region_gap(snap)
    rows = []
    for played, map_name, t1, t2, winner, *_ in _stored_maps():
        n1, n2 = names.get(t1), names.get(t2)
        r1 = snap.before(n1, played) if n1 else None
        r2 = snap.before(n2, played) if n2 else None
        if r1 is None or r2 is None:
            continue
        o1 = offsets(t1, before=played, today=played).get(map_name)
        o2 = offsets(t2, before=played, today=played).get(map_name)
        base = slope * (r1 - r2) + region_gap(n1, n2)
        plain = _sigmoid(base)
        shifted = _sigmoid(base + (o1.value if o1 else 0.0) - (o2.value if o2 else 0.0))
        rows.append((played, plain, shifted, int(winner == t1)))
    plain = [(d, q, y) for d, q, _s, y in rows]
    shifted = [(d, s, y) for d, _q, s, y in rows]
    return {
        "rating_only": rating.score(plain),
        "with_offsets": rating.score(shifted),
        "coin": rating.score([(d, 0.5, y) for d, _q, y in plain]),
        "map_slope": round(map_slope(), 4),
        "checked_at": datetime.now().date().isoformat(),
    }
