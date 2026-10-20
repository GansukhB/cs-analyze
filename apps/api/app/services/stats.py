"""Small-sample statistics shared by every page that calls something a habit,
a Strength or a Weakness (docs/plans/05-team-analytics.md TM-1).

A Team has a few Match Maps on any one Map, so a raw rate is mostly chance:
8 plants split 6-2 is "a B habit" 14% of the time for a Team that goes 50/50.
Each rate here is pulled toward the Pool's (empirical Bayes, a Beta prior fitted
on the other Teams), and a line is said only when the pulled number is still
clearly on one side of the Pool: its local false sign rate (the chance the true
rate sits on the other side of the Pool's mean) is under :data:`LFSR`.

Rounds of one Match Map are not independent draws (ρ ≈ 0.074 between them,
Parshakov 2026); :func:`effective_n` discounts a count for that. Sources and
the reasoning: docs/plans/12-research-sources.md §3.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from scipy.stats import beta as beta_dist

# A line is said when the chance it points the wrong way is below this.
LFSR = 0.10
# What one Round tells about the next in the same Match Map.
ROUND_CORRELATION = 0.074
# Bounds on a fitted prior's weight, in pseudo-events: never so weak that one
# Team's 3-0 reads as certain, never so strong that no Team can differ.
MIN_STRENGTH = 2.0
MAX_STRENGTH = 400.0
# Teams do differ: a Pool of a few Teams with a few Rounds each can show no
# spread beyond chance, which would make its prior unmovable. The true spread
# between Teams' rates is taken to be at least this (5 percentage points).
MIN_SPREAD = 0.05
INTERVAL = 0.80


@dataclass(frozen=True)
class BetaPrior:
    """What the Pool says a rate is before a Team's own events: Beta(alpha, beta)."""

    alpha: float
    beta: float
    teams: int  # how many Teams it was fitted on

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def strength(self) -> float:
        return self.alpha + self.beta


def beta_prior(
    rates: Iterable[tuple[float, float]], min_spread: float = MIN_SPREAD
) -> BetaPrior | None:
    """The Pool's prior for a rate, from each Team's ``(successes, trials)``.

    Method of moments, net of chance: the Teams' spread of rates less the spread
    their sample sizes alone would make is the true spread, and a Beta with that
    mean and variance is the prior. None with fewer than two Teams to fit on.
    ``min_spread`` is the least true spread assumed between Teams (see :data:`MIN_SPREAD`).
    """
    pairs = [(float(x), float(n)) for x, n in rates if n > 0]
    if len(pairs) < 2:
        return None
    total = sum(n for _, n in pairs)
    mean = sum(x for x, _ in pairs) / total
    mean = min(max(mean, 1e-3), 1 - 1e-3)
    weights = [n / total for _, n in pairs]
    observed = sum(w * (x / n - mean) ** 2 for w, (x, n) in zip(weights, pairs, strict=True))
    chance = sum(w * mean * (1 - mean) / n for w, (_, n) in zip(weights, pairs, strict=True))
    true_var = max(observed - chance, min_spread**2)
    strength = min(max(mean * (1 - mean) / true_var - 1, MIN_STRENGTH), MAX_STRENGTH)
    return BetaPrior(mean * strength, (1 - mean) * strength, len(pairs))


@dataclass(frozen=True)
class Shrunk:
    """A Team's rate once the Pool's prior has had its say."""

    raw: float  # x / n
    mean: float  # the posterior mean
    low: float  # the INTERVAL credible interval
    high: float
    lfsr: float  # chance the true rate is on the other side of the Pool's mean
    pool: float  # the Pool's mean
    n: float

    @property
    def above(self) -> bool:
        return self.mean > self.pool

    def clear(self, threshold: float = LFSR) -> bool:
        """Whether it stands out from the Pool, one way or the other."""
        return self.lfsr < threshold


def shrink(x: float, n: float, prior: BetaPrior) -> Shrunk:
    """``x`` successes in ``n`` (effective) trials, pulled toward ``prior``."""
    a, b = prior.alpha + x, prior.beta + max(n - x, 0.0)
    mean = a / (a + b)
    below_pool = float(beta_dist.cdf(prior.mean, a, b))
    lfsr = below_pool if mean > prior.mean else 1.0 - below_pool
    tail = (1 - INTERVAL) / 2
    return Shrunk(
        raw=x / n if n else 0.0,
        mean=mean,
        low=float(beta_dist.ppf(tail, a, b)),
        high=float(beta_dist.ppf(1 - tail, a, b)),
        lfsr=lfsr,
        pool=prior.mean,
        n=n,
    )


def effective_n(n: float, per_cluster: float, rho: float = ROUND_CORRELATION) -> float:
    """``n`` Rounds in clusters of ``per_cluster`` (a Match Map's), as independent ones."""
    if n <= 0:
        return 0.0
    return n / (1 + max(per_cluster - 1, 0.0) * rho)


def recency(age_days: float, half_life_days: float) -> float:
    """How much an event this old counts, 1 today and 1/2 at the half-life."""
    return 0.5 ** (max(age_days, 0.0) / half_life_days)


def shrink_mean(value: float, n: float, pool_mean: float, k: float) -> float:
    """A continuous number over ``n`` events pulled toward the Pool: reliability
    is n/(n+k), where k is read off the Pool's split-half agreement."""
    weight = n / (n + k) if n + k > 0 else 0.0
    return pool_mean + weight * (value - pool_mean)


def bh(pvalues: Sequence[float], q: float = LFSR) -> list[bool]:
    """Benjamini–Hochberg: which of many tests to keep at false discovery rate ``q``."""
    order = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    keep = [False] * len(pvalues)
    cutoff = -1
    for rank, i in enumerate(order, start=1):
        if pvalues[i] <= q * rank / len(pvalues):
            cutoff = rank
    for rank, i in enumerate(order, start=1):
        keep[i] = rank <= cutoff
    return keep


def bootstrap(
    groups: Sequence, statistic: Callable[[list], float], draws: int = 1000, seed: int = 0
) -> tuple[float, float]:
    """The INTERVAL range of ``statistic`` when whole groups (Match Maps) are
    resampled, so Rounds of one night don't count as independent evidence."""
    if not groups:
        return (math.nan, math.nan)
    rng = random.Random(seed)
    values = sorted(statistic(rng.choices(groups, k=len(groups))) for _ in range(draws))
    tail = (1 - INTERVAL) / 2
    return values[int(tail * (draws - 1))], values[int((1 - tail) * (draws - 1))]


def stratified_gap(
    rows: Sequence[tuple[object, bool, bool]], draws: int = 1000, seed: int = 0
) -> tuple[float, float, int]:
    """How much worse the outcome is when ``flag`` holds, within strata, and how
    often chance alone would make a gap that large: ``(gap, p, n flagged)``.

    ``rows`` are ``(stratum, flag, success)``. The gap is the flagged rows' success
    rate below the others' in the same stratum, weighted by the flagged rows; the
    one-sided p comes from shuffling ``flag`` within each stratum (a permutation
    test, so no distribution is assumed). Strata with no flagged or no other row
    say nothing and are left out.
    """
    import numpy as np

    by: dict[object, list[tuple[bool, bool]]] = {}
    for stratum, flag, ok in rows:
        by.setdefault(stratum, []).append((bool(flag), bool(ok)))
    groups = []
    for pairs in by.values():
        flags = np.array([f for f, _ in pairs], dtype=bool)
        if flags.all() or not flags.any():
            continue
        groups.append((flags, np.array([o for _, o in pairs], dtype=float)))
    n_flagged = int(sum(f.sum() for f, _ in groups))
    if not n_flagged:
        return 0.0, 1.0, 0

    def gap(flag_sets) -> np.ndarray:
        total = 0.0
        for (flags, ok), perm in zip(groups, flag_sets, strict=True):
            k = flags.sum()
            mine = (perm * ok).sum(axis=-1) / k
            rest = ((~perm) * ok).sum(axis=-1) / (len(ok) - k)
            total = total + k * (rest - mine)
        return total / n_flagged

    observed = float(gap([f for f, _ in groups]))
    rng = np.random.default_rng(seed)
    shuffled = [rng.permuted(np.tile(f, (draws, 1)), axis=1) for f, _ in groups]
    null = gap(shuffled)
    p = (1 + int((null >= observed - 1e-12).sum())) / (1 + draws)
    return observed, p, n_flagged


def chance_higher(k1: float, n1: float, k2: float, n2: float) -> float:
    """The chance the first rate is above the second, each a Beta(1 + k, 1 + n - k):
    a normal reading of their difference (fine past a handful of each)."""
    a1, b1, a2, b2 = 1 + k1, 1 + n1 - k1, 1 + k2, 1 + n2 - k2
    m1, m2 = a1 / (a1 + b1), a2 / (a2 + b2)
    v1 = a1 * b1 / ((a1 + b1) ** 2 * (a1 + b1 + 1))
    v2 = a2 * b2 / ((a2 + b2) ** 2 * (a2 + b2 + 1))
    return 0.5 * (1 + math.erf((m1 - m2) / math.sqrt(2 * (v1 + v2))))
