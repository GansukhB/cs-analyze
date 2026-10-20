"""The timeout card (docs/plans/06 GP-4): what the opponent changes when a Map
goes against them, Map by Map and Side by Side, and what we answer.

Their Rounds on the Map are split into "under pressure" (right after they lost
:data:`STREAK` in a row, or right after their own timeout) and the rest. Each
habit the Playbook already reads (where the bomb goes, a fast plant, a three-man
stack at the Setup, an early pick, a force buy) is compared between the two,
and the biggest moves (at least :data:`MIN_MOVE` points, on
:data:`MIN_PRESSURE` Rounds or more) make the card, each with its counter.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models import Round, Team
from app.services import mapstrategy, mn, playbook, stats
from app.services.dbctx import db

STREAK = 2
MIN_PRESSURE = 4
MIN_MOVE = 15.0  # points
CARD = 3
EARLY_PICK = 20.0

# Which Side each signal is read on (the words are mn.TIMEOUT_SIGNALS).
SIGNALS = {"site_a": "t", "rush": "t", "force": "both", "stack": "ct", "early_pick": "ct"}
# A move is said when the chance it is real (stats.chance_higher) is past this.
SURE = 0.85


def _pressure(team_id: int, rounds: list) -> set[int]:
    """Round ids played right after the Team lost :data:`STREAK` in a row, or
    right after its own timeout."""
    out: set[int] = set()
    by_map: dict[int, list] = {}
    for r in rounds:
        by_map.setdefault(r.match_map_id, []).append(r)
    timeouts = _timeouts(team_id, [r.id for r in rounds])
    for maps in by_map.values():
        maps.sort(key=lambda r: r.number)
        lost = 0
        for r in maps:
            if r.number in playbook.PISTOL_ROUNDS:
                lost = 0  # a half starts afresh
            if lost >= STREAK or r.id in timeouts:
                out.add(r.id)
            lost = 0 if r.winner == team_id else lost + 1
    return out


def _timeouts(team_id: int, ids: list[int]) -> set[int]:
    found = set()
    for rid, ct, t, ct_to, t_to in db().execute(
        select(
            Round.id, Round.ct_team_id, Round.t_team_id, Round.ct_timeout, Round.t_timeout
        ).where(Round.id.in_(ids))
    ):
        if (ct == team_id and ct_to) or (t == team_id and t_to):
            found.add(rid)
    return found


def _signals(team_id: int, rounds: list, detail, sites, side: str) -> dict[str, list[int]]:
    """Per Round of the Side: each signal's 0/1, keyed by Round id."""
    setups = playbook._setups(team_id, rounds, side, detail, sites)
    out: dict[str, dict[int, int]] = {k: {} for k in SIGNALS}
    for r in rounds:
        if r.side_of(team_id) != side:
            continue
        if side == "t":
            if r.plant and r.site in ("A", "B"):
                out["site_a"][r.id] = int(r.site == "A")
            out["rush"][r.id] = int(bool(r.plant) and r.secs(r.plant) <= mapstrategy.RUSH_PLANT_SEC)
        else:
            s = setups.get(r.id)
            if s and sum(s["count"].values()) >= 4:
                out["stack"][r.id] = int(max(s["count"].get("A", 0), s["count"].get("B", 0)) >= 3)
            k = detail.first_kill.get(r.id)
            out["early_pick"][r.id] = int(
                bool(k) and k.attacker_side == "ct" and r.secs(k.tick) <= EARLY_PICK
            )
        buy = r.buy(team_id)
        if buy in ("eco", "force"):
            out["force"][r.id] = int(buy == "force")
    return out


def card(opponent: Team, my_team: Team, map_name: str) -> dict:
    """The opponent's moves under pressure on this Map, Side by Side."""
    rounds = playbook._team_rounds(opponent, my_team, map_name)
    if not rounds:
        return {"map": map_name, "sides": [], "rounds": 0, "pressure": 0}
    detail = playbook._detail(rounds)
    sites = playbook.site_centroids(map_name)
    pressure = _pressure(opponent.id, rounds)
    sides = []
    for side in ("t", "ct"):
        signals = _signals(opponent.id, rounds, detail, sites, side)
        moves = []
        for key, per_round in signals.items():
            if SIGNALS[key] not in (side, "both"):
                continue
            label, up, down = mn.TIMEOUT_SIGNALS[key]
            hot = [v for rid, v in per_round.items() if rid in pressure]
            calm = [v for rid, v in per_round.items() if rid not in pressure]
            if len(hot) < MIN_PRESSURE or len(calm) < MIN_PRESSURE:
                continue
            before, after = 100 * sum(calm) / len(calm), 100 * sum(hot) / len(hot)
            sure = stats.chance_higher(sum(hot), len(hot), sum(calm), len(calm))
            if abs(after - before) < MIN_MOVE or (1 - SURE) < sure < SURE:
                continue
            refs = [
                r.ref
                for r in rounds
                if r.id in pressure and per_round.get(r.id) == int(after > before)
            ]
            moves.append(
                {
                    "key": key,
                    "label": label,
                    "usual": round(before),
                    "pressed": round(after),
                    "rounds": len(hot),
                    "counter": up if after > before else down,
                    "refs": refs[:4],
                }
            )
        moves.sort(key=lambda m: -abs(m["pressed"] - m["usual"]))
        sides.append({"side": side, "moves": moves[:CARD]})
    return {
        "map": map_name,
        "sides": sides,
        "rounds": len(rounds),
        "pressure": len(pressure),
    }
