"""Ratings (CONTEXT.md): how strong a Team is, read from its results (docs/plans FC-1).

An Elo over every series Valve Regional Standings counted (``series_results``),
in date order. A Team is followed by its name; it keeps its Rating while at
least three of its five Players stay (CONTEXT.md, Rating), and with fewer it
starts again from where its new Players stood. A Team seen for the first time
starts from its Valve points of the latest snapshot before (VRS is mostly a
prize and LAN prior, docs/plans 12 §2), pulled toward the middle since VRS is
overconfident; an unranked one starts low. A Team that stops playing drifts
back toward that start.

v1 is a series Rating: Valve's tables carry the winner of each series, not its
Maps or Rounds, so the plan's margin multiplier and Map offsets wait for the
Map results (DATA-2's HLTV match pages).

The parameters are fitted by :func:`backtest` (``npm run forecast:backtest``)
and committed in ``app/data/rating_params.json``, like the Win probability
(docs/adr/0007): a new result moves the Ratings, never the method.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select

from app.models import SeriesResult, VrsStanding
from app.services import stats
from app.services.dbctx import db, memo

PARAMS_PATH = Path(__file__).resolve().parent.parent / "data" / "rating_params.json"
SCALE = 400.0
LN10 = math.log(10)


@dataclass(frozen=True)
class Params:
    k: float = 24.0  # Elo points a series moves, at an even match
    prior_center: float = 1000.0  # where the VRS-based start is pulled toward
    prior_slope: float = 0.5  # how much of a Team's distance from the center its VRS points keep
    unranked: float = 600.0  # the start of a Team that VRS never ranked
    idle_half_life: float = 180.0  # days for an idle Team to drift halfway back to its start
    keep_core: int = 3  # Players that must stay for a Team to keep its Rating
    calibration: float = 1.0  # slope on the logit, fitted walk-forward
    version: str = "default"


def params() -> Params:
    return _params()


@lru_cache(maxsize=1)
def _params() -> Params:
    if not PARAMS_PATH.exists():
        return Params()
    data = json.loads(PARAMS_PATH.read_text())
    fields = set(Params.__dataclass_fields__)
    return Params(**{k: v for k, v in data.get("params", {}).items() if k in fields})


def expected(delta: float, calibration: float = 1.0) -> float:
    """The chance the side ``delta`` Elo points ahead wins the series."""
    z = calibration * delta * LN10 / SCALE
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def _key(name: str) -> str:
    return name.casefold().strip()


@dataclass
class _Team:
    rating: float
    start: float
    last: date | None = None
    roster: set[str] = field(default_factory=set)
    series: int = 0


@dataclass
class Snapshot:
    """Every Team's Rating as of the end of the replay, plus what it was fed."""

    teams: dict[str, _Team]
    history: dict[str, list[tuple[date, float]]]
    predictions: list[tuple[date, float, int]]  # (date, p for team_a, a won) before each series
    as_of: date | None
    players: dict[str, float] = field(default_factory=dict)  # casefold name -> his Team's Rating
    regions: dict[str, str] = field(default_factory=dict)  # casefold Team name -> VRS region

    def before(self, name: str, on: date) -> float | None:
        """A Team's Rating going into ``on``: after its last series before that day."""
        rows = self.history.get(_key(name)) or []
        i = bisect_right(rows, (on, -math.inf)) - 1
        return rows[i][1] if i >= 0 else None


class _Vrs:
    """VRS points by name, as of any date: the latest snapshot on or before it."""

    def __init__(self, rows: Iterable[tuple]):
        by_name: dict[str, list[tuple[date, float]]] = defaultdict(list)
        self.regions: dict[str, str] = {}
        for snap, name, points, *region in sorted(rows, key=lambda r: r[0]):
            by_name[_key(name)].append((snap, points))
            if region and region[0]:
                self.regions[_key(name)] = region[0]  # the latest snapshot's
        self.by_name = {k: sorted(v) for k, v in by_name.items()}

    def region(self, name: str) -> str | None:
        return self.regions.get(_key(name))

    def points(self, name: str, on: date) -> float | None:
        rows = self.by_name.get(_key(name))
        if not rows:
            return None
        i = bisect_right(rows, (on, math.inf)) - 1
        return rows[i][1] if i >= 0 else None


def _start(p: Params, vrs: _Vrs, name: str, on: date) -> float:
    points = vrs.points(name, on)
    if points is None:
        return p.unranked
    return p.prior_center + p.prior_slope * (points - p.prior_center)


def replay(
    series: list[tuple[date, str, str, bool, list[str], list[str]]],
    vrs: _Vrs,
    p: Params,
    until: date | None = None,
) -> Snapshot:
    """Run the Elo over ``series`` (date order), stopping before ``until``."""
    teams: dict[str, _Team] = {}
    players: dict[str, float] = {}  # each Player's Team Rating at his last series
    history: dict[str, list[tuple[date, float]]] = defaultdict(list)
    predictions = []
    as_of = None

    def team(name: str, on: date, roster: list[str]) -> _Team:
        key = _key(name)
        lineup = {pl.casefold() for pl in roster}
        found = teams.get(key)
        if found is None or (lineup and found.roster and len(lineup & found.roster) < p.keep_core):
            # New, or a new core: start from where its Players stood, else its VRS.
            known = [players[pl] for pl in lineup if pl in players]
            start = _start(p, vrs, name, on)
            rating = sum(known) / len(known) if len(known) >= p.keep_core else start
            found = _Team(rating=rating, start=start, roster=lineup)
            teams[key] = found
        elif found.last is not None:
            idle = (on - found.last).days
            if idle > 30:
                pull = 0.5 ** ((idle - 30) / p.idle_half_life)
                found.rating = found.start + pull * (found.rating - found.start)
        if lineup:
            found.roster = lineup
        return found

    for played, a_name, b_name, a_won, roster_a, roster_b in series:
        if until is not None and played >= until:
            break
        a, b = team(a_name, played, roster_a), team(b_name, played, roster_b)
        e = expected(a.rating - b.rating)
        predictions.append((played, expected(a.rating - b.rating, p.calibration), int(a_won)))
        move = p.k * ((1.0 if a_won else 0.0) - e)
        a.rating += move
        b.rating -= move
        for t, roster, name in ((a, roster_a, a_name), (b, roster_b, b_name)):
            t.last = played
            t.series += 1
            history[_key(name)].append((played, round(t.rating, 1)))
            for pl in roster:
                players[pl.casefold()] = t.rating
        as_of = played
    return Snapshot(teams, dict(history), predictions, as_of, players, vrs.regions)


def load_series(session=None) -> list[tuple]:
    session = session or db()
    rows = session.execute(
        select(
            SeriesResult.played_on,
            SeriesResult.team_a,
            SeriesResult.team_b,
            SeriesResult.a_won,
            SeriesResult.roster_a,
            SeriesResult.roster_b,
        ).order_by(SeriesResult.played_on, SeriesResult.id)
    ).all()
    return [tuple(r) for r in rows]


def load_vrs(session=None) -> _Vrs:
    session = session or db()
    return _Vrs(
        session.execute(
            select(
                VrsStanding.snapshot,
                VrsStanding.team_name,
                VrsStanding.points,
                VrsStanding.region,
            )
        )
    )


_LATEST: dict = {}


def stamp(session=None) -> tuple:
    """Moves whenever a result or a standing is added or changed."""
    session = session or db()
    series = session.execute(
        select(func.count(SeriesResult.id), func.max(SeriesResult.updated_at))
    ).one()
    standings = session.execute(
        select(func.count(VrsStanding.id), func.max(VrsStanding.updated_at))
    ).one()
    return (*series, *standings, params().version)


def current() -> Snapshot:
    """The Ratings as of the newest result: replayed once per change, kept in the process."""

    def build() -> Snapshot:
        now = stamp()
        if _LATEST.get("stamp") != now:
            _LATEST.update(stamp=now, snap=replay(load_series(), load_vrs(), params()))
        return _LATEST["snap"]

    return memo(("ratings",), build)


def of(name: str) -> dict | None:
    """One Team's Rating and its history, or None when no result names it."""
    snap = current()
    found = snap.teams.get(_key(name))
    if found is None:
        return None
    return {
        "rating": round(found.rating, 1),
        "series": found.series,
        "last": found.last,
        "history": snap.history.get(_key(name), []),
    }


# ---------------------------------------------------------------- fitting ---
def score(predictions: Iterable[tuple[date, float, int]]) -> dict:
    """Log loss, Brier and accuracy of ``(date, p, outcome)`` predictions."""
    rows = list(predictions)
    if not rows:
        return {"n": 0}
    eps = 1e-6
    ll = -sum(
        y * math.log(max(q, eps)) + (1 - y) * math.log(max(1 - q, eps)) for _, q, y in rows
    ) / len(rows)
    brier = sum((q - y) ** 2 for _, q, y in rows) / len(rows)
    acc = sum((q > 0.5) == bool(y) for _, q, y in rows if q != 0.5) / max(
        1, sum(1 for _, q, _ in rows if q != 0.5)
    )
    return {
        "n": len(rows),
        "log_loss": round(ll, 4),
        "brier": round(brier, 4),
        "accuracy": round(acc, 4),
    }


def fit_regions(rows: list[tuple[float, int, str | None, str | None]]) -> dict[str, float]:
    """A logit offset per region, centred on zero, that best explains the series
    between regions: ``(p, won, region a, region b)``. Gradient descent on log loss."""
    names = sorted({r for row in rows for r in row[2:] if r})
    delta = dict.fromkeys(names, 0.0)
    cross = [(math.log(q / (1 - q)), y, a, b) for q, y, a, b in rows if a and b and a != b]
    if not cross:
        return {}
    for _ in range(300):
        grad = dict.fromkeys(names, 0.0)
        for z, y, a, b in cross:
            e = 1 / (1 + math.exp(-(z + delta[a] - delta[b]))) - y
            grad[a] += e
            grad[b] -= e
        for r in names:
            delta[r] -= 0.5 * grad[r] / len(cross)
        mean = sum(delta.values()) / len(delta)
        for r in names:
            delta[r] -= mean
    return {r: round(v, 4) for r, v in delta.items()}


def with_regions(q: float, a: str | None, b: str | None, regions: dict[str, float]) -> float:
    """``q`` moved by the two regions' offsets (none when either is unknown)."""
    if not (a and b) or a == b or not (0 < q < 1):
        return q
    z = math.log(q / (1 - q)) + regions.get(a, 0.0) - regions.get(b, 0.0)
    return 1 / (1 + math.exp(-z))


def regions() -> dict[str, float]:
    """The committed region offsets (logit, on a series)."""
    return _region_offsets()


@lru_cache(maxsize=1)
def _region_offsets() -> dict[str, float]:
    if not PARAMS_PATH.exists():
        return {}
    return json.loads(PARAMS_PATH.read_text()).get("regions") or {}


BAND = 0.05
WILSON_Z = 1.2816  # an 80% interval


def bands(predictions: Iterable[tuple[date, float, int]]) -> list[dict]:
    """How often the favourite won, in 5-point bands of its chance (FC-2's
    reliability table): each band's count, rate and 80% Wilson interval."""
    groups: dict[int, list[int]] = defaultdict(list)
    for _d, q, y in predictions:
        fav, won = (q, y) if q >= 0.5 else (1 - q, 1 - y)
        groups[min(int((fav - 0.5) / BAND), int(0.5 / BAND) - 1)].append(won)
    out = []
    for i in sorted(groups):
        won = groups[i]
        n, rate = len(won), sum(won) / len(won)
        z = WILSON_Z
        mid = (rate + z * z / (2 * n)) / (1 + z * z / n)
        half = z * math.sqrt(rate * (1 - rate) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        out.append(
            {
                "lo": round(0.5 + i * BAND, 2),
                "hi": round(0.5 + (i + 1) * BAND, 2),
                "n": n,
                "won": round(rate, 4),
                "low": round(mid - half, 4),
                "high": round(mid + half, 4),
            }
        )
    return out


def _loss(q: float, y: int) -> float:
    q = min(max(q, 1e-6), 1 - 1e-6)
    return -(y * math.log(q) + (1 - y) * math.log(1 - q))


def compare(model: list[tuple], baseline: list[tuple]) -> dict:
    """Paired log loss gain of ``model`` over ``baseline`` on the same series, with
    the INTERVAL range when whole weeks are resampled (a night's series share news)."""
    weeks: dict[tuple, list[float]] = defaultdict(list)
    for (d, q, y), (_d, b, _y) in zip(model, baseline, strict=True):
        weeks[d.isocalendar()[:2]].append(_loss(b, y) - _loss(q, y))
    groups = list(weeks.values())

    def mean_gain(sample: list[list[float]]) -> float:
        flat = [g for week in sample for g in week]
        return sum(flat) / len(flat)

    low, high = stats.bootstrap(groups, mean_gain, draws=400)
    return {
        "log_loss_gain": round(mean_gain(groups), 4),
        "low": round(low, 4),
        "high": round(high, 4),
        "weeks": len(groups),
    }


def _fit_calibration(rows: list[tuple[date, float, int]], base: Params) -> float:
    """The slope on the raw logit that minimises log loss (a 1-D search)."""
    raw = [(math.log(q / (1 - q)), y) for _, q, y in rows if 0 < q < 1]

    def loss(c: float) -> float:
        total = 0.0
        for z, y in raw:
            q = 1 / (1 + math.exp(-c * z))
            q = min(max(q, 1e-6), 1 - 1e-6)
            total -= y * math.log(q) + (1 - y) * math.log(1 - q)
        return total

    lo, hi = 0.2, 2.0
    for _ in range(60):  # golden-section search
        m1, m2 = lo + (hi - lo) * 0.382, lo + (hi - lo) * 0.618
        if loss(m1) < loss(m2):
            hi = m2
        else:
            lo = m1
    return round((lo + hi) / 2, 4)


def backtest(series: list[tuple], vrs: _Vrs, split: date, burn_in: date) -> dict:
    """Tune on series before ``split`` (after ``burn_in``), report on those after.

    Every prediction is made from the Ratings before its series (walk-forward),
    so nothing a prediction scores was known when it was made."""
    grid = [
        Params(k=k, prior_slope=b, idle_half_life=h, unranked=u)
        for k in (24.0, 40.0, 56.0, 72.0)
        for b in (0.7, 1.0, 1.3)
        for h in (90.0, 180.0, 365.0)
        for u in (600.0, 700.0, 800.0, 900.0)
    ]
    best, best_ll = None, math.inf
    for p in grid:
        preds = replay(series, vrs, p).predictions
        tune = [r for r in preds if burn_in <= r[0] < split]
        s = score(tune)
        if s["n"] and s["log_loss"] < best_ll:
            best, best_ll = p, s["log_loss"]
    preds = replay(series, vrs, best).predictions
    tune = [r for r in preds if burn_in <= r[0] < split]
    calibration = _fit_calibration(tune, best)
    fitted = replace(best, calibration=calibration)
    preds = replay(series, vrs, fitted).predictions
    # FC-2's last layer: an offset per region, fitted on the tuning span's series
    # between regions (Elo inside a region knows little about the others).
    pairs = [(vrs.region(s[1]), vrs.region(s[2])) for s in series]
    regions = fit_regions(
        [(q, y, *pr) for (d, q, y), pr in zip(preds, pairs, strict=True) if burn_in <= d < split]
    )
    plain = [r for r in preds if r[0] >= split]
    test = [
        (d, with_regions(q, ra, rb, regions), y)
        for (d, q, y), (ra, rb) in zip(preds, pairs, strict=True)
        if d >= split
    ]

    # Baselines on the same test series: a coin, and Valve's points alone (with
    # their own calibration fitted on the tuning span, so the comparison is fair).
    coin = [(d, 0.5, y) for d, _q, y in test]

    def vrs_raw(span):
        out = []
        for played, a, b, a_won, _ra, _rb in series:
            if not span(played):
                continue
            pa, pb = vrs.points(a, played), vrs.points(b, played)
            q = 0.5 if pa is None or pb is None else expected(pa - pb, 1.0)
            out.append((played, q, int(a_won)))
        return out

    vrs_slope = _fit_calibration(vrs_raw(lambda d: burn_in <= d < split), best)
    vrs_only = [
        (d, 1 / (1 + math.exp(-vrs_slope * math.log(q / (1 - q)))) if 0 < q < 1 else q, y)
        for d, q, y in vrs_raw(lambda d: d >= split)
    ]
    return {
        "params": asdict(fitted),
        "regions": regions,
        "reliability": bands(test),
        "tune": score(tune),
        "test": score(test),
        "test_without_regions": score(plain),
        "between_regions": {
            "without": score(
                r
                for r, (ra, rb) in zip(preds, pairs, strict=True)
                if r[0] >= split and ra and rb and ra != rb
            ),
            "with": score(
                (d, with_regions(q, ra, rb, regions), y)
                for (d, q, y), (ra, rb) in zip(preds, pairs, strict=True)
                if d >= split and ra and rb and ra != rb
            ),
        },
        "baselines": {"coin": score(coin), "vrs_points": score(vrs_only)},
        "vs_vrs_points": compare(test, vrs_only),
        "split": split.isoformat(),
        "burn_in": burn_in.isoformat(),
    }
