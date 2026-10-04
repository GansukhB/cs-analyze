"""A Fixture's Lineups: whose numbers a Game Plan shows and ranks (CONTEXT.md).

The User picks them on the page, and the page's URL carries them, so a Game Plan
stays stateless. A request binds them with :func:`using`, like the analysis
session (:mod:`app.services.dbctx`), and the analysis modules ask :func:`names`
for a Team's five instead of guessing it themselves. A side left unpicked keeps
the guess the modules always made: the five from the Team's most recent parsed
Match.

A Lineup never narrows a Team's habits. It only decides which Players are shown
and ranked. A picked Player who never played for the Team (a new signing) has
no numbers there, so :func:`elsewhere` finds the Team and Match Maps the Player's
numbers come from instead.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

from sqlalchemy import func, or_, select

from app.models import MapRoster, Match, MatchMap, Player, PlayerAlias, Team
from app.services import mapstrategy
from app.services.dbctx import db, memo

SEARCH_LIMIT = 20
_EPOCH = datetime(1970, 1, 2)

_chosen: ContextVar[Mapping[int, tuple[Player, ...]] | None] = ContextVar("lineups", default=None)


@contextmanager
def using(chosen: Mapping[int, Sequence[Player]]) -> Iterator[None]:
    """Bind ``{team_id: players}`` for this request. A Team not in it is unpicked."""
    token = _chosen.set({team: tuple(players) for team, players in chosen.items() if players})
    try:
        yield
    finally:
        _chosen.reset(token)


def chosen(team: Team) -> tuple[Player, ...] | None:
    """The Players picked for this Team, or None when its Lineup is unpicked."""
    return (_chosen.get() or {}).get(team.id)


def names(team: Team, inferred: Callable[[], set[str]]) -> set[str]:
    """The names in this Team's Lineup: the picked Players, else ``inferred()``."""
    picked = chosen(team)
    return {p.name for p in picked} if picked is not None else inferred()


def fielded(team: Team) -> set[int]:
    """The ids in this Team's Lineup: the picked Players, else :func:`latest_five`."""
    picked = chosen(team)
    return {p.id for p in (picked if picked is not None else latest_five(team))}


def latest_five(team: Team) -> list[Player]:
    """The Players who played for this Team in its most recent parsed Match."""

    def compute():
        maps = [m for m in mapstrategy.maps_in_window(team) if m.match and m.match.played_at]
        if not maps:
            return []
        latest = max(m.match.played_at for m in maps)
        ids = [m.id for m in maps if m.match.played_at == latest]
        return list(
            db().scalars(
                select(Player)
                .join(MapRoster, MapRoster.player_id == Player.id)
                .where(MapRoster.match_map_id.in_(ids), MapRoster.team_id == team.id)
                .distinct()
                .order_by(Player.name)
            )
        )

    return memo(("latest_five", team.id), compute)


def _played_for(team: Team) -> set[int]:
    """Every Player who played a parsed Match Map for this Team."""

    def compute():
        return set(
            db().scalars(
                select(MapRoster.player_id)
                .join(MatchMap, MatchMap.id == MapRoster.match_map_id)
                .where(MapRoster.team_id == team.id, MatchMap.parsed_at.is_not(None))
            )
        )

    return memo(("played_for", team.id), compute)


def newcomers(team: Team) -> list[Player]:
    """Picked Players with no parsed Match Map for this Team, such as a new signing."""
    played = _played_for(team)
    return [p for p in chosen(team) or () if p.id not in played]


def elsewhere(player: Player) -> tuple[Team, list[MatchMap]] | None:
    """The Team a Player last played for, and their parsed Match Maps with it.

    It is where a new signing's numbers come from: the most recent Team only,
    because two former Teams' numbers do not add up to one Player's form.
    """

    def compute():
        row = (
            db()
            .execute(
                select(MapRoster.team_id)
                .join(MatchMap, MatchMap.id == MapRoster.match_map_id)
                .join(Match, Match.id == MatchMap.match_id)
                .where(
                    MapRoster.player_id == player.id,
                    MapRoster.team_id.is_not(None),
                    MatchMap.parsed_at.is_not(None),
                )
                .order_by(Match.played_at.desc(), MatchMap.map_number.desc())
                .limit(1)
            )
            .first()
        )
        if row is None:
            return None
        team = db().get(Team, row[0])
        his = set(
            db().scalars(
                select(MapRoster.match_map_id).where(
                    MapRoster.player_id == player.id, MapRoster.team_id == team.id
                )
            )
        )
        return team, [m for m in mapstrategy.maps_in_window(team) if m.id in his]

    return memo(("elsewhere", player.id), compute)


# ------------------------------------------------------------- the picker ---
def candidates(team: Team) -> list[dict]:
    """Who has played for this Team, most recent first, the inferred five marked."""
    default = {p.id for p in latest_five(team)}
    rows = (
        db()
        .execute(
            select(
                Player,
                func.count(func.distinct(MapRoster.match_map_id)),
                func.max(Match.played_at),
            )
            .join(MapRoster, MapRoster.player_id == Player.id)
            .join(MatchMap, MatchMap.id == MapRoster.match_map_id)
            .join(Match, Match.id == MatchMap.match_id)
            .where(MapRoster.team_id == team.id, MatchMap.parsed_at.is_not(None))
            .group_by(Player.id)
        )
        .all()
    )
    out = [
        {
            "steamid": str(player.steamid),
            "name": player.name,
            "team": team.name,
            "maps": maps,
            "last_played": last,
            "default": player.id in default,
        }
        for player, maps, last in rows
    ]
    out.sort(key=lambda p: (not p["default"], -(p["last_played"] or _EPOCH).timestamp()))
    return out


def search(query: str) -> list[dict]:
    """Players whose name, or any name they played under, contains ``query``."""
    like = f"%{query.strip()}%"
    players = (
        db()
        .scalars(
            select(Player)
            .outerjoin(PlayerAlias, PlayerAlias.player_id == Player.id)
            .where(or_(Player.name.ilike(like), PlayerAlias.name.ilike(like)))
            .distinct()
            .order_by(Player.last_seen.desc())
            .limit(SEARCH_LIMIT)
        )
        .all()
    )
    out = []
    for player in players:
        last = elsewhere(player)
        out.append(
            {
                "steamid": str(player.steamid),
                "name": player.name,
                "team": last[0].name if last else "",
                "maps": len(last[1]) if last else 0,
                "last_played": None,
                "default": False,
            }
        )
    return out


def resolve(steamids: Sequence[int]) -> list[Player]:
    """The Players behind these Steam ids, in the given order; KeyError names a stranger."""
    found = {p.steamid: p for p in db().scalars(select(Player).where(Player.steamid.in_(steamids)))}
    missing = [s for s in steamids if s not in found]
    if missing:
        raise KeyError(missing[0])
    return [found[s] for s in steamids]


def cache_part(mine: Sequence[Player], theirs: Sequence[Player]) -> str:
    """What the Lineups add to a cached panel's key: nothing when both are unpicked."""
    if not mine and not theirs:
        return ""
    signature = "|".join(",".join(sorted(str(p.steamid) for p in side)) for side in (mine, theirs))
    return ":L" + hashlib.sha1(signature.encode()).hexdigest()[:12]
