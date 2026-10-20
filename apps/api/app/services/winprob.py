"""Win probability (CONTEXT.md): a Side's chance of winning a Round from one moment.

The state is what a caster would read off the HUD: how many are alive on each
Side, what the living carry, whether the bomb is down, how much time is left on
the round clock (or the bomb's, once it is planted) and how many living CTs have
a kit. Two logistic models, one before the plant and one after, are fitted on
every parsed Round by :func:`fit` and committed as ``app/data/winprob.json``
(docs/adr/0007): a parse never refits them, so a Review's numbers don't drift.
``python -m app.cli fit-winprob`` (``npm run review:fit``) refits and bumps
:data:`VERSION`, which marks every stored Review stale.

Each model is a base on the man count (CT minus T, and each side's count), a
ridge-penalised offset per man-count cell so the 36 cells can bend away from the
base where the data says so, the equipment of the living, the clock, and a
ridge-penalised offset per Map (Nuke and Inferno lean CT). States the game
itself decides are not modelled: no CT alive is a T win, no T alive before a
plant is a CT win, the clock running out decides by whether the bomb is down.

Version 2 (RV-4) adds what the HUD shows beyond that: the living's average
health, the grenades they still carry, which side made the last kill, after
the plant the defuse race (the bomb's clock less the nearest CT's run to it and
his defuse), and before it a ridge-penalised offset per pair of buys. It is
fitted on the states the Review itself reads (:func:`app.services.review.states`),
so the model and the Review can't drift apart, and :func:`fit` reports its
calibration (Brier, AUC, ECE, reliability) by phase, Map, buys and clock.
A version 1 model still reads: the features it lacks weigh nothing.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "winprob.json"

ROUND_SECONDS = 115.0  # CS2 competitive round clock
BOMB_SECONDS = 40.0
DEFUSE_SECONDS = 10.0
DEFUSE_KIT_SECONDS = 5.0
# Samples between events, so the clock is learned and not only the kills.
SAMPLE_EVERY_SECONDS = 2.0
CELL_RIDGE = 4.0
MAP_RIDGE = 8.0
BUY_RIDGE = 8.0
BASE_RIDGE = 0.01
# A buy pair gets its own offset with this many samples behind it.
BUY_MIN_SAMPLES = 2000
# Running speed with a knife out, for the defuse race (units/s).
RUN_SPEED = 250.0
RACE_SCALE = 10.0  # seconds
RACE_CAP = 2.0
RELIABILITY_BINS = 10
# A probability is kept off 0 and 1 so a Swing is never a certainty's artefact.
FLOOR = 0.005


@dataclass(frozen=True)
class State:
    """One moment of a Round, from both Sides."""

    ct_alive: int
    t_alive: int
    ct_equip: float  # summed equipment value of the living CTs
    t_equip: float
    planted: bool
    seconds_left: float  # on the round clock, or the bomb's once planted
    ct_kits: int = 0  # living CTs with a defuse kit
    map_name: str = ""
    # A defuse already under way (the Review knows the ones that finished): the
    # clock no longer has to fit a whole defuse, only what is left of this one.
    defusing: bool = False
    # Version 2 (RV-4); 0, None or "" where unknown, which weighs nothing.
    ct_hp: float = 0.0  # summed health of the living CTs
    t_hp: float = 0.0
    ct_util: int = 0  # grenades the living carry
    t_util: int = 0
    last: int = 0  # +1 the CTs made the last kill, -1 the Ts, 0 none yet
    race: float | None = None  # after the plant: the bomb's clock - the nearest defuse
    ct_buy: str = ""
    t_buy: str = ""


def _cells() -> list[tuple[int, int]]:
    return [(c, t) for c in range(0, 6) for t in range(0, 6)]


def features(state: State, maps: list[str], buys: list[str] = ()) -> dict[str, float]:
    """The named features of ``state``; the model for its phase picks its own."""
    ct, t = state.ct_alive, state.t_alive
    clock = max(0.0, state.seconds_left) / (BOMB_SECONDS if state.planted else ROUND_SECONDS)
    out = {
        "bias": 1.0,
        "diff": float(ct - t),
        "ct": float(ct),
        "t": float(t),
        "equip": math.log((state.ct_equip + 1000.0) / (state.t_equip + 1000.0)),
        "clock": clock,
        "clock_ct": clock * ct,
        "clock_t": clock * t,
        f"cell:{ct}v{t}": 1.0,
    }
    if state.planted:
        kit = 1.0 if state.ct_kits > 0 else 0.0
        out["kit"] = kit
        out["kit_clock"] = kit * clock
        if state.race is not None:
            out["race"] = max(-RACE_CAP, min(RACE_CAP, state.race / RACE_SCALE))
    if ct and t and (state.ct_hp or state.t_hp):
        out["hp"] = (state.ct_hp / ct - state.t_hp / t) / 100.0
    out["util"] = (state.ct_util - state.t_util) / 5.0
    out["last"] = float(state.last)
    pair = buy_key(state)
    if not state.planted and pair in buys:
        out[f"buy:{pair}"] = 1.0
    name = _map_key(state.map_name)
    if name in maps:
        out[f"map:{name}"] = 1.0
    return out


def buy_key(state: State) -> str:
    return f"{state.ct_buy}v{state.t_buy}" if state.ct_buy and state.t_buy else ""


def _map_key(name: str) -> str:
    return (name or "").strip().lower().removeprefix("de_")


V1 = ["bias", "diff", "ct", "t", "equip", "clock", "clock_ct", "clock_t"]
V2 = ["hp", "util", "last"]


def _names(planted: bool, maps: list[str], buys: list[str] = (), version: int = 2) -> list[str]:
    base = list(V1)
    if planted:
        base += ["kit", "kit_clock"]
    if version >= 2:
        base += V2 + (["race"] if planted else [])
    names = base + [f"cell:{c}v{t}" for c, t in _cells()] + [f"map:{m}" for m in maps]
    if version >= 2 and not planted:
        names += [f"buy:{b}" for b in buys]
    return names


def _ridge(name: str) -> float:
    if name.startswith("cell:"):
        return CELL_RIDGE
    if name.startswith("map:"):
        return MAP_RIDGE
    if name.startswith("buy:"):
        return BUY_RIDGE
    return BASE_RIDGE


def terminal(state: State) -> float | None:
    """The CT's chance when the game has already decided, else None."""
    if state.ct_alive <= 0:
        return 0.0
    if not state.planted:
        if state.t_alive <= 0 or state.seconds_left <= 0:
            return 1.0
    # A defuse takes 10 s, 5 with a kit: less than that left and nobody can,
    # unless one is already running.
    elif not state.defusing and state.seconds_left < (
        DEFUSE_KIT_SECONDS if state.ct_kits > 0 else DEFUSE_SECONDS
    ):
        return 0.0
    return None


# ----------------------------------------------------------------- the model ---
@lru_cache(maxsize=1)
def model() -> dict:
    """The committed model, or an empty one (every state 50/50 by man count)."""
    if not MODEL_PATH.exists():
        logger.warning("no win probability model at %s; run `npm run review:fit`", MODEL_PATH)
        return {"version": "none", "maps": [], "pre": {}, "post": {}}
    return json.loads(MODEL_PATH.read_text())


def version() -> str:
    return str(model().get("version") or "none")


def ct_win(state: State) -> float:
    """The CT Side's Win probability in ``state``, in [FLOOR, 1 - FLOOR] unless decided."""
    decided = terminal(state)
    if decided is not None:
        return decided
    spec = model()
    coef = spec.get("post" if state.planted else "pre") or {}
    if not coef:  # no model: the man count alone, softly
        z = 0.8 * (state.ct_alive - state.t_alive) + (-1.0 if state.planted else 0.0)
    else:
        found = features(state, spec.get("maps", []), spec.get("buys", []))
        z = sum(coef.get(k, 0.0) * v for k, v in found.items())
    p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
    return min(1.0 - FLOOR, max(FLOOR, p))


def win(state: State, side: str) -> float:
    p = ct_win(state)
    return p if side == "ct" else 1.0 - p


# ----------------------------------------------------------------- fitting ---
@dataclass
class Sample:
    state: State
    ct_won: bool
    weight: float
    group: int  # the Match Map, for cross-validation


def samples_from_reviews(db, progress=None) -> list[Sample]:
    """Every Match Map's states as its Review reads them (version 2, RV-4):
    health, utility and positions come from the Tick Data. Each Round weighs the
    same. Only Tick Data with the economy and the Loadout counts: without them
    the buys and the grenades read as nothing, which no live state is."""
    from sqlalchemy import select

    from app.models import MatchMap, TickDataset
    from app.services import review, tickdata

    out: list[Sample] = []
    ids = [
        d.match_map_id
        for d in db.execute(
            select(TickDataset.match_map_id, TickDataset.tables).order_by(TickDataset.match_map_id)
        )
        if tickdata.reparseable(d)
    ]
    for i, mid in enumerate(ids):
        match_map = db.get(MatchMap, mid)
        for timeline, ct_won in review.states(db, match_map):
            if not timeline:
                continue
            weight = 1.0 / len(timeline)
            out += [Sample(state, ct_won, weight, mid) for state in timeline]
        db.expunge_all()  # a Match Map's rows are not needed again
        if progress:
            progress(i + 1, len(ids))
    return out


def _design(samples: list[Sample], planted: bool, maps: list[str], buys=(), version: int = 2):
    names = _names(planted, maps, buys, version)
    index = {n: i for i, n in enumerate(names)}
    rows = [s for s in samples if s.state.planted == planted and terminal(s.state) is None]
    x = np.zeros((len(rows), len(names)))
    for r, s in enumerate(rows):
        for k, v in features(s.state, maps, buys).items():
            if k in index:
                x[r, index[k]] = v
    y = np.array([1.0 if s.ct_won else 0.0 for s in rows])
    w = np.array([s.weight for s in rows])
    g = np.array([s.group for s in rows])
    return names, x, y, w, g, rows


def _irls(x, y, w, ridge, iterations: int = 50) -> np.ndarray:
    beta = np.zeros(x.shape[1])
    for _ in range(iterations):
        z = np.clip(x @ beta, -30, 30)
        p = 1.0 / (1.0 + np.exp(-z))
        grad = x.T @ (w * (p - y)) + ridge * beta
        hess = (x * (w * p * (1 - p))[:, None]).T @ x + np.diag(ridge)
        step = np.linalg.solve(hess, grad)
        beta -= step
        if np.abs(step).max() < 1e-7:
            break
    return beta


def _logloss(x, y, w, beta) -> float:
    p = np.clip(1.0 / (1.0 + np.exp(-np.clip(x @ beta, -30, 30))), 1e-6, 1 - 1e-6)
    return float(-(w * (y * np.log(p) + (1 - y) * np.log(1 - p))).sum() / w.sum())


def _predict(x, beta) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x @ beta, -30, 30)))


def _auc(p: np.ndarray, y: np.ndarray) -> float | None:
    """Rank AUC: the chance a won state reads higher than a lost one."""
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return None
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def calibration(p: np.ndarray, y: np.ndarray, w: np.ndarray) -> dict:
    """Log loss, Brier, AUC, ECE and the reliability bins of held-out predictions."""
    if not len(p):
        return {}
    q = np.clip(p, 1e-6, 1 - 1e-6)
    total = w.sum()
    bins = np.minimum((p * RELIABILITY_BINS).astype(int), RELIABILITY_BINS - 1)
    reliability, ece = [], 0.0
    for b in range(RELIABILITY_BINS):
        m = bins == b
        if not m.any():
            continue
        mass = w[m].sum()
        said, seen = float((w[m] * p[m]).sum() / mass), float((w[m] * y[m]).sum() / mass)
        ece += mass / total * abs(said - seen)
        reliability.append([round(said, 3), round(seen, 3), round(float(mass / total), 4)])
    auc = _auc(p, y)
    return {
        "logloss": round(float(-(w * (y * np.log(q) + (1 - y) * np.log(1 - q))).sum() / total), 4),
        "brier": round(float((w * (p - y) ** 2).sum() / total), 4),
        "auc": round(auc, 4) if auc is not None else None,
        "ece": round(float(ece), 4),
        "reliability": reliability,
    }


def _clock_bucket(state: State) -> str:
    limit = BOMB_SECONDS if state.planted else ROUND_SECONDS
    used = 1.0 - max(0.0, state.seconds_left) / limit
    return ("early", "middle", "late")[min(2, int(used * 3))]


def fit(samples: list[Sample], folds: int = 5, version: int = 2) -> dict:
    """Both models on ``samples``, with their cross-validated calibration: overall,
    by Map, by pair of buys and by clock, against the man count alone."""
    counts: dict[str, int] = defaultdict(int)
    pairs: dict[str, int] = defaultdict(int)
    for s in samples:
        counts[_map_key(s.state.map_name)] += 1
        if not s.state.planted and buy_key(s.state):
            pairs[buy_key(s.state)] += 1
    maps = sorted(m for m, n in counts.items() if m and n >= 2000)
    buys = sorted(b for b, n in pairs.items() if n >= BUY_MIN_SAMPLES) if version >= 2 else []
    spec: dict = {"features": version, "maps": maps, "buys": buys, "metrics": {}}
    for phase, planted in (("pre", False), ("post", True)):
        names, x, y, w, g, rows = _design(samples, planted, maps, buys, version)
        ridge = np.array([_ridge(n) for n in names])
        beta = _irls(x, y, w, ridge)
        spec[phase] = {n: round(float(b), 5) for n, b in zip(names, beta, strict=True)}
        groups = np.unique(g)
        rng = np.random.default_rng(7)
        rng.shuffle(groups)
        held_p = np.full(len(y), np.nan)
        base_p = np.full(len(y), np.nan)
        cols = [names.index(c) for c in ("bias", "diff")]
        for k in range(folds):
            held = np.isin(g, groups[k::folds])
            if held.sum() == 0 or (~held).sum() == 0:
                continue
            b = _irls(x[~held], y[~held], w[~held], ridge)
            held_p[held] = _predict(x[held], b)
            # The man count alone, for comparison.
            simple = _irls(x[~held][:, cols], y[~held], w[~held], ridge[cols])
            base_p[held] = _predict(x[held][:, cols], simple)
        ok = ~np.isnan(held_p)
        overall = calibration(held_p[ok], y[ok], w[ok])
        metrics = {
            "samples": int(len(y)),
            "cv_logloss": overall.get("logloss"),
            "cv_logloss_man_count_only": calibration(base_p[ok], y[ok], w[ok]).get("logloss"),
            **{k: v for k, v in overall.items() if k != "logloss"},
        }
        for key, label in (("by_map", lambda s: _map_key(s.state.map_name) or "?"),
                           ("by_clock", lambda s: _clock_bucket(s.state)),
                           ("by_buys", lambda s: buy_key(s.state) or "?")):  # fmt: skip
            if key == "by_buys" and planted:
                continue
            tags = np.array([label(s) for s in rows])
            part = {}
            for tag in sorted(set(tags)):
                m = ok & (tags == tag)
                if m.sum() >= 200:
                    c = calibration(held_p[m], y[m], w[m])
                    part[tag] = {"samples": int(m.sum()), "logloss": c["logloss"],
                                 "brier": c["brier"], "ece": c["ece"]}  # fmt: skip
            metrics[key] = part
        spec["metrics"][phase] = metrics
    return spec
