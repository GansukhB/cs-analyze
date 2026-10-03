"""Head-to-head reading: what has actually happened when two teams met.

Only the parts of cstat's ``hltv/services/scouting.py`` the game plan reads:
the head-to-head maps, their summary, and the per-player profiles over them.
Every finding ships the counts behind it; a note without its sample size is a guess.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.models import (
    KillEvent,
    MapRoster,
    Match,
    MatchMap,
    Player,
    PlayerMap,
    PlayerRound,
    Round,
    Team,
)
from app.services.dbctx import count_if, db, memo, total

MIN_ROUNDS_FOR_CONFIDENCE = 60
MIN_MAPS_FOR_CONFIDENCE = 3


def _on_roster(team_id: int):
    return (
        select(MapRoster.id)
        .where(MapRoster.match_map_id == MatchMap.id, MapRoster.team_id == team_id)
        .exists()
    )


def head_to_head_maps(team_a: Team, team_b: Team) -> list[MatchMap]:
    """Parsed maps where these two teams faced each other."""

    def compute():
        return list(
            db()
            .scalars(
                select(MatchMap)
                .join(Match, Match.id == MatchMap.match_id)
                .where(
                    MatchMap.parsed_at.is_not(None), _on_roster(team_a.id), _on_roster(team_b.id)
                )
                .options(
                    joinedload(MatchMap.match),
                    joinedload(MatchMap.game_map),
                    joinedload(MatchMap.team1),
                    joinedload(MatchMap.team2),
                    joinedload(MatchMap.winner),
                )
                .order_by(Match.played_at.desc(), MatchMap.map_number)
            )
            .unique()
        )

    return list(memo(("h2h_maps", *sorted((team_a.id, team_b.id))), compute))


def maps_for_team(team: Team) -> list[MatchMap]:
    """Parsed maps this team appears on, newest first."""

    def compute():
        return list(
            db()
            .scalars(
                select(MatchMap)
                .join(Match, Match.id == MatchMap.match_id)
                .where(MatchMap.parsed_at.is_not(None), _on_roster(team.id))
                .options(
                    joinedload(MatchMap.match),
                    joinedload(MatchMap.game_map),
                    joinedload(MatchMap.team1),
                    joinedload(MatchMap.team2),
                    joinedload(MatchMap.winner),
                )
                .order_by(Match.played_at.desc(), MatchMap.map_number.desc())
            )
            .unique()
        )

    return list(memo(("maps_for_team", team.id), compute))


def player_profiles(team: Team, match_maps: Iterable[MatchMap]) -> list[dict]:
    """One row per player, aggregated across the given maps."""
    map_ids = [m.id for m in match_maps]
    if not map_ids:
        return []
    session = db()
    player_ids = set(
        session.scalars(
            select(MapRoster.player_id).where(
                MapRoster.match_map_id.in_(map_ids), MapRoster.team_id == team.id
            )
        )
    )
    if not player_ids:
        return []
    pids = list(player_ids)

    stats = session.execute(
        select(
            PlayerMap.player_id,
            Player.name,
            func.count(PlayerMap.id),
            total(PlayerMap.rounds_played),
            total(PlayerMap.kills),
            total(PlayerMap.deaths),
            total(PlayerMap.assists),
            total(PlayerMap.headshots),
            total(PlayerMap.damage),
            total(PlayerMap.opening_kills),
            total(PlayerMap.opening_deaths),
        )
        .join(Player, Player.id == PlayerMap.player_id)
        .where(PlayerMap.match_map_id.in_(map_ids), PlayerMap.player_id.in_(pids))
        .group_by(PlayerMap.player_id, Player.name)
    ).all()

    in_maps = PlayerRound.round_id.in_(select(Round.id).where(Round.match_map_id.in_(map_ids)))
    per_player = {
        pid: (int(kast), int(traded), int(multi))
        for pid, kast, traded, multi in session.execute(
            select(
                PlayerRound.player_id,
                count_if(PlayerRound.kast),
                count_if(PlayerRound.traded),
                count_if(PlayerRound.kills >= 3),
            )
            .where(in_maps, PlayerRound.player_id.in_(pids))
            .group_by(PlayerRound.player_id)
        )
    }
    side_split: dict[int, dict[str, dict]] = defaultdict(dict)
    for pid, side, n, kills, deaths, damage in session.execute(
        select(
            PlayerRound.player_id,
            PlayerRound.side,
            func.count(PlayerRound.id),
            total(PlayerRound.kills),
            total(PlayerRound.deaths),
            total(PlayerRound.damage),
        )
        .where(in_maps, PlayerRound.player_id.in_(pids), PlayerRound.side != "")
        .group_by(PlayerRound.player_id, PlayerRound.side)
    ):
        side_split[pid][side] = {
            "rounds": n,
            "kills": int(kills),
            "deaths": int(deaths),
            "adr": _ratio(int(damage), n),
        }

    in_kills = KillEvent.round_id.in_(select(Round.id).where(Round.match_map_id.in_(map_ids)))
    weapons = _top_by(
        KillEvent.attacker_id, KillEvent.weapon, in_kills, KillEvent.attacker_id.in_(pids)
    )
    kill_places = _top_by(
        KillEvent.attacker_id,
        KillEvent.attacker_place,
        in_kills,
        KillEvent.attacker_id.in_(pids),
        KillEvent.attacker_place != "",
    )
    death_places = _top_by(
        KillEvent.victim_id,
        KillEvent.victim_place,
        in_kills,
        KillEvent.victim_id.in_(pids),
        KillEvent.victim_place != "",
    )

    profiles = []
    for row in stats:
        pid, name, maps = row[0], row[1], row[2]
        rounds, kills, deaths, assists, headshots, damage, ok, od = (int(v or 0) for v in row[3:])
        kast, traded, multi = per_player.get(pid, (0, 0, 0))
        attempts = ok + od
        profiles.append(
            {
                "player_id": pid,
                "name": name,
                "maps": maps,
                "rounds": rounds,
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "kd_diff": kills - deaths,
                "kd_ratio": round(kills / deaths, 2) if deaths else float(kills),
                "adr": _ratio(damage, rounds),
                "kast_pct": _pct(kast, rounds),
                "hs_pct": _pct(headshots, kills),
                "opening_kills": ok,
                "opening_deaths": od,
                "opening_attempts": attempts,
                "opening_win_pct": _pct(ok, attempts),
                "traded_death_pct": _pct(traded, deaths),
                "multi_kill_rounds": multi,
                "sides": side_split.get(pid, {}),
                "top_weapons": weapons.get(pid, []),
                "kill_places": kill_places.get(pid, []),
                "death_places": death_places.get(pid, []),
            }
        )
    profiles.sort(key=lambda p: (-p["adr"], -p["kills"]))
    for p in profiles:
        p["impact"] = _impact(p)
    return profiles


def _top_by(group, value, *where, limit: int = 3) -> dict[int, list]:
    """Top ``limit`` values of ``value`` per ``group``, with counts."""
    out: dict[int, list] = defaultdict(list)
    n = func.count(KillEvent.id)
    for key, val, count in db().execute(
        select(group, value, n).where(*where).group_by(group, value).order_by(group, n.desc())
    ):
        if key is not None and len(out[key]) < limit:
            out[key].append({"value": val, "count": count})
    return out


def _impact(profile: dict) -> float:
    """A within-report yardstick: damage, consistency and duel value."""
    adr = profile["adr"] or 0
    kast = profile["kast_pct"] or 0
    kd = profile["kd_ratio"] or 0
    opening = profile["opening_kills"] - profile["opening_deaths"]
    rounds = max(profile["rounds"], 1)
    return round(adr / 100 * 1.4 + kast / 100 * 1.0 + kd * 0.6 + opening / rounds * 2.0, 3)


def _map_summary(match_map: MatchMap, my_team: Team) -> dict:
    """One map's result from my team's point of view."""
    mine_is_team1 = match_map.team1_id == my_team.id
    my_score = match_map.team1_score if mine_is_team1 else match_map.team2_score
    their_score = match_map.team2_score if mine_is_team1 else match_map.team1_score
    return {
        "match": match_map.match.hltv_id,
        "match_id": match_map.match_id,
        "map_number": match_map.map_number,
        "played_at": match_map.match.played_at.isoformat() if match_map.match.played_at else None,
        "map": match_map.game_map.name if match_map.game_map else "?",
        "my_score": my_score,
        "their_score": their_score,
        "won": match_map.winner_id == my_team.id,
        "rounds": match_map.n_rounds,
    }


def head_to_head_report(my_team: Team, opponent: Team, h2h_maps: list[MatchMap]) -> dict:
    """What has actually happened when these two met."""
    if not h2h_maps:
        return {
            "maps": [],
            "matches": [],
            "by_map": [],
            "totals": {},
            "my_players": [],
            "their_players": [],
        }

    summaries = [_map_summary(m, my_team) for m in h2h_maps]

    by_match: dict[int, dict] = {}
    for summary in summaries:
        entry = by_match.setdefault(
            summary["match"],
            {
                "match": summary["match"],
                "match_id": summary["match_id"],
                "played_at": summary["played_at"],
                "maps": [],
                "my_maps_won": 0,
                "their_maps_won": 0,
            },
        )
        entry["maps"].append(summary)
        if summary["won"]:
            entry["my_maps_won"] += 1
        elif summary["their_score"] is not None:
            entry["their_maps_won"] += 1

    by_map: dict[str, dict] = {}
    for summary in summaries:
        entry = by_map.setdefault(
            summary["map"],
            {
                "map": summary["map"],
                "played": 0,
                "won": 0,
                "lost": 0,
                "rounds_for": 0,
                "rounds_against": 0,
            },
        )
        entry["played"] += 1
        entry["won" if summary["won"] else "lost"] += 1
        entry["rounds_for"] += summary["my_score"] or 0
        entry["rounds_against"] += summary["their_score"] or 0
    for entry in by_map.values():
        entry["round_diff"] = entry["rounds_for"] - entry["rounds_against"]
        entry["win_pct"] = _pct(entry["won"], entry["played"])

    won = sum(1 for s in summaries if s["won"])
    return {
        "maps": summaries,
        "matches": sorted(by_match.values(), key=lambda m: m["played_at"] or "", reverse=True),
        "by_map": sorted(by_map.values(), key=lambda e: (-e["played"], e["map"])),
        "totals": {
            "maps_played": len(summaries),
            "maps_won": won,
            "maps_lost": len(summaries) - won,
            "map_win_pct": _pct(won, len(summaries)),
            "rounds_for": sum(s["my_score"] or 0 for s in summaries),
            "rounds_against": sum(s["their_score"] or 0 for s in summaries),
        },
        "my_players": player_profiles(my_team, h2h_maps),
        "their_players": player_profiles(opponent, h2h_maps),
    }


def _ratio(numerator, denominator, nd: int = 1):
    return round(numerator / denominator, nd) if denominator else 0.0


def _pct(numerator, denominator, nd: int = 1):
    return round(numerator / denominator * 100, nd) if denominator else 0.0
