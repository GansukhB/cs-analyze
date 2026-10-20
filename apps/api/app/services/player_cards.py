"""What the Reviews say about a Fixture's Players (docs/plans/04 PL-7): each one's
Swing per Round with its range over his Match Maps, and the Findings he gets
clearly more (or less) often than every reviewed Player does.

A Finding rate is per Round, pulled toward a Beta prior fitted on every Player
with enough reviewed Rounds (``stats``), and said only at local false sign rate
under ``stats.LFSR`` with :data:`MIN_FINDINGS` of them; Swing per Round is said
only when its bootstrap range over his Match Maps sits clear of zero (a Round's
Swing sums to zero, so zero is the Pool).
"""

from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import select

from app.models import Player, Team
from app.services import mn, review, review_pool, stats
from app.services.dbctx import db, memo

MIN_FINDINGS = 3  # of one code, before it can be his habit
# Utility effects that cost the Team, read with the Mistakes.
COSTLY_UTILITY = {"team_flash", "empty_utility"}
# Only an AWPer can miss with one: those codes are judged against Players who had them.
AWP_CODES = {"awp_miss", "unscoped_awp"}
MIN_POOL_ROUNDS = 48  # a Player joins a code's prior with two Match Maps' worth
MIN_SWING_MAPS = 3


def _pool_rates() -> dict:
    """code -> [(count, rounds)] over every reviewed Player, and rounds by sid."""

    def build():
        data = review_pool.data()
        rounds: Counter = Counter()
        counts: dict[str, Counter] = defaultdict(Counter)
        for t in data.tallies:
            for sid, rows in t.players.items():
                rounds[sid] += len(rows)
            for code, events in t.codes.items():
                for e in events:
                    if e[2]:
                        counts[code][e[2]] += 1
        out = {}
        for code, by_sid in counts.items():
            out[code] = [
                (by_sid.get(sid, 0), stats.effective_n(n, review_pool_rounds_per_map()))
                for sid, n in rounds.items()
                if n >= MIN_POOL_ROUNDS and (code not in AWP_CODES or by_sid.get(sid))
            ]
        return out, rounds

    return memo(("player_cards_pool", review_pool.stamp()), build)


def review_pool_rounds_per_map() -> float:
    return 24.0  # a regulation Match Map's Rounds, both Sides


def lines(team: Team, player_ids: list[int]) -> dict[int, dict]:
    """player id -> {"swing", "weaknesses", "tendencies"} from the stored Reviews."""
    if not player_ids:
        return {}
    session = db()
    sids = {
        str(steamid): pid
        for pid, steamid in session.execute(
            select(Player.id, Player.steamid).where(Player.id.in_(player_ids))
        )
    }
    data = review_pool.data()
    priors_by_code, _rounds = _pool_rates()
    per_map: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    codes: dict[str, Counter] = defaultdict(Counter)
    for t in data.by_team.get(team.id, []):
        for sid, rows in t.players.items():
            if sid in sids:
                per_map[sid][t.mm] += [s for _n, s in rows]
        for code, events in t.codes.items():
            for e in events:
                if e[2] in sids:
                    codes[e[2]][code] += 1

    out: dict[int, dict] = {}
    for sid, pid in sids.items():
        maps = per_map.get(sid) or {}
        rounds = sum(len(v) for v in maps.values())
        entry = {
            "rounds": rounds,
            "maps": len(maps),
            "swing": None,
            "weaknesses": [],
            # Key plays and useful utility he makes more than most: how he plays,
            # which says as much about his role as about his level.
            "tendencies": [],
        }
        if len(maps) >= MIN_SWING_MAPS:
            groups = list(maps.values())

            def mean(sample):
                flat = [s for g in sample for s in g]
                return sum(flat) / len(flat) if flat else 0.0

            low, high = stats.bootstrap(groups, mean, draws=400)
            entry["swing"] = {
                "per_round": round(mean(groups), 4),
                "low": round(low, 4),
                "high": round(high, 4),
                "clear": low > 0 or high < 0,
            }
        n_eff = stats.effective_n(rounds, review_pool_rounds_per_map())
        for code, count in codes.get(sid, {}).items():
            prior = stats.beta_prior(priors_by_code.get(code) or [])
            if prior is None or count < MIN_FINDINGS or n_eff <= 0:
                continue
            post = stats.shrink(count, n_eff, prior)
            if not post.clear() or not post.above:
                continue
            kind = review.CODE_KIND.get(code, "")
            line = {
                "code": code,
                "kind": kind,
                "label": mn.REVIEW_CODE.get(code, code),
                "count": count,
                "per24": round(24 * count / rounds, 2) if rounds else None,
                "pool_per24": round(24 * prior.mean * n_eff / rounds, 2) if rounds else None,
                "lfsr": round(post.lfsr, 3),
            }
            costly = kind in ("mistake", "missed_chance") or code in COSTLY_UTILITY
            entry["weaknesses" if costly else "tendencies"].append(line)
        for key in ("weaknesses", "tendencies"):
            entry[key].sort(key=lambda r: r["lfsr"])
        out[pid] = entry
    return out
