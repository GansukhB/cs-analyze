"""A my team's numbers over a set of its Match Maps, read from stored rows.

The v2 overview, the management summary and the Team goals all count the same
things the same way: Maps and Rounds won, pistols, opening duels, trades (a
death avenged inside the trade window, CONTEXT.md: Trade), Rounds won after the
plant, retakes, force buys. Each comes back as ``won`` of ``of`` so a caller can
say how much it rests on; a share with nothing under it is None, never 0.

Which Match Maps a caller passes decides what counts: the session's scope
already hides other Workspaces' Matches and, unless the page asked, Scrims
(docs/adr/0010). Bind a session with ``dbctx.using``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from app.models import BuyType, Match, MatchKind, MatchMap, PlayerRound, Round
from app.services.dbctx import db


@dataclass
class Count:
    won: int = 0
    of: int = 0

    def add(self, won: bool) -> None:
        self.of += 1
        self.won += 1 if won else 0

    @property
    def pct(self) -> float | None:
        return round(100.0 * self.won / self.of, 1) if self.of else None

    def as_dict(self) -> dict:
        return {"won": self.won, "of": self.of, "pct": self.pct}


# What every number is called, in the order the overview shows them.
KEYS = ("maps", "rounds", "rounds_t", "rounds_ct", "pistol", "opening", "trade", "post_plant",
        "retake", "force")  # fmt: skip


def team_maps(
    team_id: int,
    since: datetime | None = None,
    until: datetime | None = None,
    *,
    kind: str | None = None,
) -> list[MatchMap]:
    """The Team's parsed Match Maps in a window, oldest first. ``kind`` keeps one
    kind of Match (official or scrim); the scope decides whether Scrims are seen."""
    q = (
        select(MatchMap)
        .join(Match, Match.id == MatchMap.match_id)
        .where(
            MatchMap.parsed_at.is_not(None),
            or_(MatchMap.team1_id == team_id, MatchMap.team2_id == team_id),
        )
        .options(joinedload(MatchMap.match), joinedload(MatchMap.game_map))
        .order_by(Match.played_at, MatchMap.map_number)
    )
    if since is not None:
        q = q.where(Match.played_at >= since)
    if until is not None:
        q = q.where(Match.played_at < until)
    if kind is not None:
        q = q.where(Match.kind == kind)
    return list(db().scalars(q).unique())


def map_name(m: MatchMap) -> str:
    return m.game_map.name if m.game_map else "?"


def is_scrim(m: MatchMap) -> bool:
    return m.match.kind == MatchKind.SCRIM


def numbers(team_id: int, maps: Iterable[MatchMap], side: str | None = None) -> dict[str, Count]:
    """Every number of :data:`KEYS` over these Match Maps; with ``side``, every
    number but the Maps over the Rounds the Team played on that Side only."""
    maps = list(maps)
    out = {key: Count() for key in KEYS}
    for m in maps:
        if m.winner_id:
            out["maps"].add(m.winner_id == team_id)
    ids = [m.id for m in maps]
    if not ids:
        return out
    session = db()
    rounds = list(session.scalars(select(Round).where(Round.match_map_id.in_(ids))))
    for r in rounds:
        here = "ct" if r.ct_team_id == team_id else "t" if r.t_team_id == team_id else None
        if here is None or not r.winner_team_id or (side and here != side):
            continue
        won = r.winner_team_id == team_id
        out["rounds"].add(won)
        out[f"rounds_{here}"].add(won)
        buy = r.ct_buy if here == "ct" else r.t_buy
        if buy == BuyType.PISTOL:
            out["pistol"].add(won)
        elif buy == BuyType.FORCE:
            out["force"].add(won)
        if r.bomb_plant_tick is not None:
            out["post_plant" if here == "t" else "retake"].add(won)
    by_round = {
        r.id: r
        for r in rounds
        if not side or (r.ct_team_id if side == "ct" else r.t_team_id) == team_id
    }
    for pr in session.scalars(
        select(PlayerRound).where(
            PlayerRound.round_id.in_(list(by_round)), PlayerRound.team_id == team_id
        )
    ):
        if pr.opening_kill:
            out["opening"].add(True)
        elif pr.opening_death:
            out["opening"].add(False)
        if pr.deaths:
            out["trade"].add(pr.traded)
    return out


def round_shares(team_id: int, maps: Iterable[MatchMap]) -> dict[int, float]:
    """Each Match Map's share of Rounds this Team won, 0–1, from its scoreline."""
    out = {}
    for m in maps:
        if m.team1_score is None or m.team2_score is None:
            continue
        mine, theirs = m.team1_score, m.team2_score
        if m.team2_id == team_id:
            mine, theirs = theirs, mine
        if mine + theirs:
            out[m.id] = mine / (mine + theirs)
    return out


def by_map(team_id: int, maps: Iterable[MatchMap]) -> dict[str, list[MatchMap]]:
    grouped: dict[str, list[MatchMap]] = defaultdict(list)
    for m in maps:
        grouped[map_name(m)].append(m)
    return grouped


def score_of(team_id: int, m: MatchMap) -> tuple[int | None, int | None]:
    """This Team's Rounds first, the opponent's second."""
    if m.team2_id == team_id:
        return m.team2_score, m.team1_score
    return m.team1_score, m.team2_score


def opponent_of(team_id: int, m: MatchMap):
    return m.team2 if m.team1_id == team_id else m.team1
