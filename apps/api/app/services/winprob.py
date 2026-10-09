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
BASE_RIDGE = 0.01
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


def _cells() -> list[tuple[int, int]]:
    return [(c, t) for c in range(0, 6) for t in range(0, 6)]


def features(state: State, maps: list[str]) -> dict[str, float]:
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
    name = _map_key(state.map_name)
    if name in maps:
        out[f"map:{name}"] = 1.0
    return out


def _map_key(name: str) -> str:
    return (name or "").strip().lower().removeprefix("de_")


def _names(planted: bool, maps: list[str]) -> list[str]:
    base = ["bias", "diff", "ct", "t", "equip", "clock", "clock_ct", "clock_t"]
    if planted:
        base += ["kit", "kit_clock"]
    return base + [f"cell:{c}v{t}" for c, t in _cells()] + [f"map:{m}" for m in maps]


def _ridge(name: str) -> float:
    if name.startswith("cell:"):
        return CELL_RIDGE
    if name.startswith("map:"):
        return MAP_RIDGE
    return BASE_RIDGE


def terminal(state: State) -> float | None:
    """The CT's chance when the game has already decided, else None."""
    if state.ct_alive <= 0:
        return 0.0
    if not state.planted:
        if state.t_alive <= 0 or state.seconds_left <= 0:
            return 1.0
    # A defuse takes 10 s, 5 with a kit: less than that left and nobody can.
    elif state.seconds_left < (DEFUSE_KIT_SECONDS if state.ct_kits > 0 else DEFUSE_SECONDS):
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
        z = sum(coef.get(k, 0.0) * v for k, v in features(state, spec.get("maps", [])).items())
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


def samples_from_db(db) -> list[Sample]:
    """Every parsed Round's states: at freeze end, after each kill and the plant,
    and every :data:`SAMPLE_EVERY_SECONDS` between. Each Round weighs the same."""
    from sqlalchemy import select

    from app.models import GameMap, KillEvent, MatchMap, PlayerRound, Round

    maps = dict(
        db.execute(
            select(MatchMap.id, GameMap.name).join(GameMap, GameMap.id == MatchMap.game_map_id)
        ).all()
    )
    rates = dict(db.execute(select(MatchMap.id, MatchMap.tickrate)).all())
    kills: dict[int, list] = defaultdict(list)
    for row in db.execute(
        select(KillEvent.round_id, KillEvent.tick, KillEvent.victim_id, KillEvent.victim_side)
    ):
        kills[row.round_id].append(row)
    players: dict[int, list] = defaultdict(list)
    for row in db.execute(
        select(
            PlayerRound.round_id,
            PlayerRound.player_id,
            PlayerRound.side,
            PlayerRound.equip_value,
            PlayerRound.defuser,
        )
    ):
        players[row.round_id].append(row)
    out: list[Sample] = []
    for rnd in db.scalars(select(Round).where(Round.winner_side.in_(("ct", "t")))):
        rate = rates.get(rnd.match_map_id) or 64
        roster = players.get(rnd.id) or []
        if len(roster) < 2:
            continue
        timeline = round_states(
            rnd, roster, kills.get(rnd.id) or [], rate, maps.get(rnd.match_map_id, "")
        )
        if not timeline:
            continue
        weight = 1.0 / len(timeline)
        out += [
            Sample(state, rnd.winner_side == "ct", weight, rnd.match_map_id)
            for _tick, state in timeline
        ]
    return out


def round_states(rnd, roster, kills, rate: int, map_name: str) -> list[tuple[int, State]]:
    """``(tick, state)`` through one Round, live part only, as :func:`samples_from_db` fits."""
    equip = {r.player_id: float(r.equip_value or 0) for r in roster}
    side = {r.player_id: r.side for r in roster}
    kit = {r.player_id for r in roster if r.defuser}
    alive = {pid for pid in side}
    start, end = rnd.freeze_end_tick, rnd.end_tick
    plant = rnd.bomb_plant_tick
    deaths = sorted((k.tick, k.victim_id) for k in kills if start <= k.tick <= end)
    moments = {start, *(t for t, _ in deaths), *([plant] if plant else [])}
    step = max(1, int(SAMPLE_EVERY_SECONDS * rate))
    moments |= set(range(start, end, step))
    out = []
    di = 0
    for tick in sorted(moments):
        while di < len(deaths) and deaths[di][0] <= tick:
            alive.discard(deaths[di][1])
            di += 1
        out.append((tick, state_at(tick, alive, side, equip, kit, start, plant, rate, map_name)))
    return out


def state_at(tick, alive, side, equip, kit, start, plant, rate, map_name) -> State:
    planted = plant is not None and tick >= plant
    if planted:
        left = BOMB_SECONDS - (tick - plant) / rate
    else:
        left = ROUND_SECONDS - (tick - start) / rate
    ct = [p for p in alive if side.get(p) == "ct"]
    t = [p for p in alive if side.get(p) == "t"]
    return State(
        ct_alive=len(ct),
        t_alive=len(t),
        ct_equip=sum(equip.get(p, 0.0) for p in ct),
        t_equip=sum(equip.get(p, 0.0) for p in t),
        planted=planted,
        seconds_left=left,
        ct_kits=sum(1 for p in ct if p in kit),
        map_name=map_name,
    )


def _design(samples: list[Sample], planted: bool, maps: list[str]):
    names = _names(planted, maps)
    index = {n: i for i, n in enumerate(names)}
    rows = [s for s in samples if s.state.planted == planted and terminal(s.state) is None]
    x = np.zeros((len(rows), len(names)))
    for r, s in enumerate(rows):
        for k, v in features(s.state, maps).items():
            if k in index:
                x[r, index[k]] = v
    y = np.array([1.0 if s.ct_won else 0.0 for s in rows])
    w = np.array([s.weight for s in rows])
    g = np.array([s.group for s in rows])
    return names, x, y, w, g


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


def fit(samples: list[Sample], folds: int = 5) -> dict:
    """Both models on ``samples``, with a cross-validated log loss per phase."""
    counts: dict[str, int] = defaultdict(int)
    for s in samples:
        counts[_map_key(s.state.map_name)] += 1
    maps = sorted(m for m, n in counts.items() if m and n >= 2000)
    spec: dict = {"maps": maps, "metrics": {}}
    for phase, planted in (("pre", False), ("post", True)):
        names, x, y, w, g = _design(samples, planted, maps)
        ridge = np.array([_ridge(n) for n in names])
        beta = _irls(x, y, w, ridge)
        spec[phase] = {n: round(float(b), 5) for n, b in zip(names, beta, strict=True)}
        groups = np.unique(g)
        rng = np.random.default_rng(7)
        rng.shuffle(groups)
        losses, base = [], []
        for k in range(folds):
            held = np.isin(g, groups[k::folds])
            if held.sum() == 0 or (~held).sum() == 0:
                continue
            b = _irls(x[~held], y[~held], w[~held], ridge)
            losses.append(_logloss(x[held], y[held], w[held], b))
            # The man count alone, for comparison.
            simple = np.zeros(len(names))
            cols = [names.index(c) for c in ("bias", "diff")]
            simple[cols] = _irls(x[~held][:, cols], y[~held], w[~held], ridge[cols])
            base.append(_logloss(x[held], y[held], w[held], simple))
        spec["metrics"][phase] = {
            "samples": int(len(y)),
            "cv_logloss": round(float(np.mean(losses)), 4) if losses else None,
            "cv_logloss_man_count_only": round(float(np.mean(base)), 4) if base else None,
        }
    return spec
