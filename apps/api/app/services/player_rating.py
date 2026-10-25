"""Player rating (CONTEXT.md; docs/adr/0013): HLTV's Rating 2.0, as published approximately.

    Rating = 0.0073·KAST + 0.3591·KPR − 0.5329·DPR + 0.2372·Impact + 0.0032·ADR + 0.1587
    Impact = 2.13·KPR + 0.42·APR − 0.41

KAST in percent, the rest per Round. 1.00 is an average game. It is read from the
stored per-Map lines (``player_maps``), summed over Rounds before the formula, so
a Player's rating over several Match Maps weighs each by its Rounds. It is not
HLTV's own number; Swing stays what every judgement is made from.

Like the other services this takes no session: bind one with ``dbctx.using``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select

from app.models import PlayerMap
from app.services.dbctx import db


@dataclass
class Line:
    """One Player's totals over some Match Maps."""

    rounds: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    damage: int = 0
    kast_rounds: float = 0.0
    headshots: int = 0
    opening_kills: int = 0
    opening_deaths: int = 0
    maps: int = 0

    def add(self, pm: PlayerMap) -> None:
        self.rounds += pm.rounds_played
        self.kills += pm.kills
        self.deaths += pm.deaths
        self.assists += pm.assists
        self.damage += pm.damage
        self.kast_rounds += (pm.kast_pct or 0.0) * pm.rounds_played / 100.0
        self.headshots += pm.headshots
        self.opening_kills += pm.opening_kills
        self.opening_deaths += pm.opening_deaths
        self.maps += 1

    def merge(self, other: Line) -> None:
        for name in self.__dataclass_fields__:
            setattr(self, name, getattr(self, name) + getattr(other, name))

    @property
    def adr(self) -> float | None:
        return self.damage / self.rounds if self.rounds else None

    @property
    def kast(self) -> float | None:
        return 100.0 * self.kast_rounds / self.rounds if self.rounds else None

    @property
    def hs(self) -> float | None:
        return 100.0 * self.headshots / self.kills if self.kills else None

    @property
    def opening(self) -> float | None:
        duels = self.opening_kills + self.opening_deaths
        return 100.0 * self.opening_kills / duels if duels else None

    @property
    def rating(self) -> float | None:
        if not self.rounds:
            return None
        return rating(
            self.rounds, self.kills, self.deaths, self.assists, self.damage, self.kast or 0.0
        )


def rating(
    rounds: int, kills: int, deaths: int, assists: int, damage: int, kast_pct: float
) -> float:
    kpr, dpr, apr, adr = kills / rounds, deaths / rounds, assists / rounds, damage / rounds
    impact = 2.13 * kpr + 0.42 * apr - 0.41
    value = (
        0.0073 * kast_pct + 0.3591 * kpr - 0.5329 * dpr + 0.2372 * impact + 0.0032 * adr + 0.1587
    )
    # A game of deaths and nothing else reads below zero in the formula; HLTV's floor is 0.
    return max(0.0, value)


def _played(pm: PlayerMap) -> bool:
    # A coach or caster in the server has Rounds but never a kill, death or damage.
    return pm.rounds_played > 0 and (pm.kills or pm.deaths or pm.damage) > 0


def per_map(match_map_ids: Iterable[int]) -> dict[tuple[int, int], tuple[Line, int | None]]:
    """``{(match_map_id, player_id): (line, team_id)}`` for these Match Maps."""
    ids = list(set(match_map_ids))
    if not ids:
        return {}
    out = {}
    for pm in db().scalars(select(PlayerMap).where(PlayerMap.match_map_id.in_(ids))):
        if _played(pm):
            line = Line()
            line.add(pm)
            out[(pm.match_map_id, pm.player_id)] = (line, pm.team_id)
    return out


def per_player(match_map_ids: Iterable[int], team_id: int | None = None) -> dict[int, Line]:
    """Each Player's totals over these Match Maps, only for one Team when named."""
    totals: dict[int, Line] = {}
    for (_mm, pid), (line, team) in per_map(match_map_ids).items():
        if team_id is not None and team != team_id:
            continue
        totals.setdefault(pid, Line()).merge(line)
    return totals


def team_average(lines: Iterable[Line]) -> float | None:
    """A Team's five over a Match Map, as one number: their ratings weighed by Rounds."""
    pairs = [(line.rating, line.rounds) for line in lines if line.rating is not None]
    total = sum(r for _v, r in pairs)
    return sum(v * r for v, r in pairs) / total if total else None
