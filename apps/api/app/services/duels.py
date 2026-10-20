"""Eco-adjusted duels (docs/plans/04 PL-6), after HLTV Rating 3.0's eco adjustment.

Every kill between enemies is a duel the killer won. Each Player's class is
what he bought for the Round (a Player who bought no gun holds a pistol; the
victim's held gun is not stored, so both sides are judged the same way). Over
the Pool, each pair of classes has a chance of being won, by the killer's Side,
pulled toward the pair's chance over both Sides by :data:`SIDE_PRIOR` duels. A
Player's duels are then worth what they beat: killing a pistol with a rifle
earns little, losing to one costs a lot.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.models import KillEvent, PlayerRound, Round
from app.services.dbctx import db, memo

CLASSES = ("sniper", "rifle", "rifle2", "smg", "pistol")
# What a Player had bought, by the Loadout's name; no gun bought is a pistol.
BOUGHT_CLASS = {
    **dict.fromkeys(("AWP", "G3SG1", "SCAR-20"), "sniper"),
    **dict.fromkeys(("AK-47", "M4A4", "M4A1-S", "AUG", "SG 553"), "rifle"),
    **dict.fromkeys(("Galil AR", "FAMAS", "SSG 08"), "rifle2"),
    **dict.fromkeys(
        (
            "MP9",
            "MAC-10",
            "MP7",
            "MP5-SD",
            "UMP-45",
            "P90",
            "PP-Bizon",
            "MAG-7",
            "Nova",
            "XM1014",
            "Sawed-Off",
            "M249",
            "Negev",
        ),
        "smg",
    ),  # fmt: skip
}
SIDE_PRIOR = 30.0  # duels
PAIR_PRIOR = 10.0  # duels, toward an even duel


def _feed(match_map_ids: list[int] | None = None):
    """``(killer, victim, killer side, killer class, victim class, round id)`` per
    kill between enemies, in the Match Maps given (or all)."""
    killer_round = aliased(PlayerRound)
    victim_round = aliased(PlayerRound)
    query = (
        select(
            KillEvent.attacker_id,
            KillEvent.victim_id,
            KillEvent.attacker_side,
            killer_round.primary_weapon,
            victim_round.primary_weapon,
            KillEvent.round_id,
        )
        .join(Round, Round.id == KillEvent.round_id)
        .join(
            victim_round,
            (victim_round.round_id == KillEvent.round_id)
            & (victim_round.player_id == KillEvent.victim_id),
        )
        .join(
            killer_round,
            (killer_round.round_id == KillEvent.round_id)
            & (killer_round.player_id == KillEvent.attacker_id),
        )
        .where(
            KillEvent.attacker_id.is_not(None),
            KillEvent.attacker_side.in_(("ct", "t")),
            KillEvent.victim_side.in_(("ct", "t")),
            KillEvent.attacker_side != KillEvent.victim_side,
        )
    )
    if match_map_ids is not None:
        query = query.where(Round.match_map_id.in_(match_map_ids))
    for killer, victim, side, mine, theirs, round_id in db().execute(query):
        yield (killer, victim, side, BOUGHT_CLASS.get(mine or "", "pistol"),
               BOUGHT_CLASS.get(theirs or "", "pistol"), round_id)  # fmt: skip


def table() -> dict:
    """``{(side, a, b): chance}``: the chance a Player of the ``side`` with class
    ``a`` wins a duel against class ``b``, over the Pool."""

    def build() -> dict:
        won: dict[tuple, int] = defaultdict(int)
        for _k, _v, side, a, b, _r in _feed():
            won[(side, a, b)] += 1
        out = {}
        for a in CLASSES:
            for b in CLASSES:
                both = sum(won[(s, a, b)] for s in ("ct", "t"))
                lost = sum(won[(s, b, a)] for s in ("ct", "t"))
                pair = (both + PAIR_PRIOR / 2) / (both + lost + PAIR_PRIOR)
                for side, other in (("ct", "t"), ("t", "ct")):
                    w, lo = won[(side, a, b)], won[(other, b, a)]
                    out[(side, a, b)] = (w + SIDE_PRIOR * pair) / (w + lo + SIDE_PRIOR)
        return out

    return memo("duels:table", build)


def player(player_id: int, match_map_ids: list[int]) -> dict | None:
    """One Player's duels over these Match Maps: taken, won, what the classes
    expected, and the difference per Round he played."""
    if not match_map_ids:
        return None
    chance = table()
    won = lost = 0
    expected = 0.0
    for killer, victim, side, a, b, _round in _feed(match_map_ids):
        if killer == player_id:
            won += 1
            expected += chance[(side, a, b)]
        elif victim == player_id:
            lost += 1
            expected += 1.0 - chance[(side, a, b)]
    duels = won + lost
    played = db().scalar(
        select(func.count(PlayerRound.id))
        .join(Round, Round.id == PlayerRound.round_id)
        .where(PlayerRound.player_id == player_id, Round.match_map_id.in_(match_map_ids))
    )
    if not duels or not played:
        return None
    return {
        "duels": duels,
        "won": won,
        "won_pct": round(100 * won / duels, 1),
        "expected_pct": round(100 * expected / duels, 1),
        # Duels won above what the guns on both sides expected, per Round.
        "over_per_round": round((won - expected) / played, 4),
    }
