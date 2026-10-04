"""Head-to-head reading: what has actually happened when two teams met.

The parts of cstat's ``hltv/services/scouting.py`` the game plan and the
Assistant read: the head-to-head maps, their summary, the per-player profiles
over them, a team's shape, the three findings (underperformers, threats,
vulnerabilities) and the player-vs-player matchups. Every finding ships the
counts behind it; a note without its sample size is a guess.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload

from app.models import (
    GrenadeThrow,
    KillEvent,
    MapRoster,
    Match,
    MatchMap,
    Player,
    PlayerMap,
    PlayerMapDuel,
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


def _ever_played_for(team_id: int):
    """Players who ever appeared on this Team's roster (cstat's ``map_appearances__team``)."""
    return select(MapRoster.player_id).where(MapRoster.team_id == team_id)


# -- team-level shape --------------------------------------------------------
def team_shape(team: Team, match_maps: Iterable[MatchMap]) -> dict:
    """Side balance, bombsite habits and utility use for one team."""
    match_maps = list(match_maps)
    map_ids = [m.id for m in match_maps]
    session = db()
    in_maps = Round.match_map_id.in_(map_ids)

    def side(column) -> tuple[int, int]:
        n, won = session.execute(
            select(func.count(Round.id), count_if(Round.winner_team_id == team.id)).where(
                in_maps, column == team.id
            )
        ).one()
        return int(n), int(won)

    ct_rounds, ct_wins = side(Round.ct_team_id)
    t_rounds, t_wins = side(Round.t_team_id)

    plant_split: dict[str, int] = {}
    plant_conversion: dict[str, float] = {}
    for site, n, won in session.execute(
        select(Round.bomb_site, func.count(Round.id), count_if(Round.winner_team_id == team.id))
        .where(in_maps, Round.t_team_id == team.id, Round.bomb_site != "")
        .group_by(Round.bomb_site)
    ):
        plant_split[site] = int(n)
        plant_conversion[site] = _pct(int(won), int(n))

    util = session.scalar(
        select(func.count(GrenadeThrow.id))
        .join(Round, Round.id == GrenadeThrow.round_id)
        .where(in_maps, GrenadeThrow.thrower_id.in_(_ever_played_for(team.id)))
    )
    total_rounds = ct_rounds + t_rounds

    return {
        "rounds": total_rounds,
        "maps": len(map_ids),
        "ct_rounds": ct_rounds,
        "ct_wins": ct_wins,
        "ct_win_pct": _pct(ct_wins, ct_rounds),
        "t_rounds": t_rounds,
        "t_wins": t_wins,
        "t_win_pct": _pct(t_wins, t_rounds),
        "plant_split": plant_split,
        "plant_conversion_pct": plant_conversion,
        "grenades_per_round": _ratio(util or 0, total_rounds, nd=2),
        "map_results": [
            {
                "map": m.game_map.name if m.game_map else "?",
                "score": m.scoreline,
                "won": m.winner_id == team.id,
                "match": m.match.hltv_id,
            }
            for m in match_maps
        ],
    }


# -- the three findings ------------------------------------------------------
def find_underperformers(profiles: list[dict], shape: dict) -> list[dict]:
    """My team's weak links, each with the comparison that flags them."""
    if not profiles:
        return []
    avg_adr = _mean(p["adr"] for p in profiles)
    avg_kast = _mean(p["kast_pct"] for p in profiles)
    findings = []

    for p in sorted(profiles, key=lambda x: x["impact"]):
        reasons = []
        if p["adr"] < avg_adr * 0.85:
            reasons.append(
                {
                    "code": "low_adr",
                    "text": f"ADR {p['adr']} against a team average of {avg_adr} "
                    f"({round(p['adr'] - avg_adr, 1)})",
                }
            )
        if p["kast_pct"] < avg_kast - 5:
            reasons.append(
                {
                    "code": "low_kast",
                    "text": f"contributes in only {p['kast_pct']}% of rounds, "
                    f"team average {avg_kast}%",
                }
            )
        if p["kd_diff"] <= -5:
            reasons.append(
                {
                    "code": "negative_kd",
                    "text": f"{p['kd_diff']} kill difference over {p['rounds']} rounds",
                }
            )
        if p["opening_deaths"] > p["opening_kills"] and p["opening_attempts"] >= 4:
            reasons.append(
                {
                    "code": "loses_openings",
                    "text": f"loses the opening duel {p['opening_deaths']}-{p['opening_kills']} "
                    f"({p['opening_win_pct']}% won)",
                }
            )
        if p["deaths"] and p["traded_death_pct"] < 25 and p["deaths"] >= 10:
            reasons.append(
                {
                    "code": "untraded",
                    "text": f"only {p['traded_death_pct']}% of his deaths are traded — "
                    "he is dying away from support",
                }
            )
        if reasons:
            findings.append(
                {
                    "player": p["name"],
                    "player_id": p["player_id"],
                    "impact": p["impact"],
                    "summary": _underperformer_summary(p, reasons),
                    "reasons": reasons,
                    "stats": _headline(p),
                }
            )
    return findings


def _underperformer_summary(p: dict, reasons: list[dict]) -> str:
    codes = {r["code"] for r in reasons}
    if "loses_openings" in codes and "untraded" in codes:
        return f"{p['name']} is taking duels the team cannot support."
    if "loses_openings" in codes:
        return f"{p['name']} is losing the first duel too often."
    if "low_kast" in codes:
        return f"{p['name']} is passing through rounds without affecting them."
    if "low_adr" in codes:
        return f"{p['name']} is not doing his share of the damage."
    return f"{p['name']} is below the team's own par."


def find_threats(profiles: list[dict]) -> list[dict]:
    """Opponent players who decide rounds, and the shape of how they do it."""
    threats = []
    for p in sorted(profiles, key=lambda x: -x["impact"])[:3]:
        traits = []
        if p["opening_kills"] >= 4 and p["opening_win_pct"] >= 55:
            traits.append(
                {
                    "code": "entry",
                    "text": f"wins {p['opening_win_pct']}% of his opening duels "
                    f"({p['opening_kills']}-{p['opening_deaths']})",
                }
            )
        if p["adr"] >= 80:
            traits.append({"code": "damage", "text": f"{p['adr']} ADR across {p['rounds']} rounds"})
        if p["multi_kill_rounds"] >= 3:
            traits.append(
                {
                    "code": "multikill",
                    "text": f"{p['multi_kill_rounds']} rounds with 3 or more kills",
                }
            )
        if p["hs_pct"] and p["hs_pct"] >= 55:
            traits.append({"code": "aim", "text": f"{p['hs_pct']}% of his kills are headshots"})
        best_side = _best_side(p)
        if best_side:
            traits.append(best_side)
        if p["top_weapons"]:
            w = p["top_weapons"][0]
            traits.append(
                {"code": "weapon", "text": f"{w['count']} of his kills came with the {w['value']}"}
            )
        if p["kill_places"]:
            spots = ", ".join(f"{k['value']} ({k['count']})" for k in p["kill_places"])
            traits.append({"code": "positions", "text": f"kills mostly from {spots}"})

        threats.append(
            {
                "player": p["name"],
                "player_id": p["player_id"],
                "impact": p["impact"],
                "summary": _threat_summary(p, traits),
                "traits": traits,
                "stats": _headline(p),
            }
        )
    return threats


def _threat_summary(p: dict, traits: list[dict]) -> str:
    codes = {t["code"] for t in traits}
    if "entry" in codes:
        return f"{p['name']} opens rounds — deny him the first contact."
    if "damage" in codes and "multikill" in codes:
        return f"{p['name']} is the one who wins their rounds outright."
    if "damage" in codes:
        return f"{p['name']} carries their damage."
    return f"{p['name']} is their most consistent player."


def _best_side(p: dict) -> dict | None:
    sides = p.get("sides") or {}
    if len(sides) < 2:
        return None
    ct, t = sides.get("ct"), sides.get("t")
    if not ct or not t or not ct["rounds"] or not t["rounds"]:
        return None
    if abs(ct["adr"] - t["adr"]) < 15:
        return None
    strong, label = (ct, "CT") if ct["adr"] > t["adr"] else (t, "T")
    weak = t if strong is ct else ct
    return {
        "code": "side",
        "text": f"far stronger on {label} side ({strong['adr']} ADR vs {weak['adr']} on the other)",
    }


def find_vulnerabilities(
    profiles: list[dict], shape: dict, team: Team, match_maps: Iterable[MatchMap]
) -> list[dict]:
    """Exploitable tendencies, each with the numbers it came from."""
    findings = []
    map_ids = [m.id for m in match_maps]

    # 1. The weak link -- who to hunt.
    if profiles:
        weakest = min(profiles, key=lambda p: p["impact"])
        if len(profiles) > 1 and weakest["impact"] < _mean(p["impact"] for p in profiles) * 0.8:
            findings.append(
                {
                    "code": "weak_link",
                    "title": f"Hunt {weakest['name']}",
                    "detail": f"Their lowest-impact player: {weakest['adr']} ADR, "
                    f"{weakest['kast_pct']}% KAST, {weakest['kd_diff']:+d} kill difference. "
                    + (
                        f"He dies first {weakest['opening_deaths']} times."
                        if weakest["opening_deaths"]
                        else ""
                    ),
                    "evidence": _headline(weakest),
                    "player": weakest["name"],
                }
            )

    # 2. Side imbalance -- which half to attack.
    if shape["ct_rounds"] and shape["t_rounds"]:
        gap = (shape["ct_win_pct"] or 0) - (shape["t_win_pct"] or 0)
        if abs(gap) >= 15:
            weak_side = "T" if gap > 0 else "CT"
            findings.append(
                {
                    "code": "side_imbalance",
                    "title": f"They are weaker on {weak_side} side",
                    "detail": f"CT {shape['ct_wins']}/{shape['ct_rounds']} "
                    f"({shape['ct_win_pct']}%) versus T {shape['t_wins']}/{shape['t_rounds']} "
                    f"({shape['t_win_pct']}%).",
                    "evidence": {
                        "ct_win_pct": shape["ct_win_pct"],
                        "t_win_pct": shape["t_win_pct"],
                        "rounds": shape["rounds"],
                    },
                }
            )

    # 3. Predictable bombsite.
    plants = shape["plant_split"]
    if plants and sum(plants.values()) >= 5:
        total_plants = sum(plants.values())
        site, n = max(plants.items(), key=lambda kv: kv[1])
        share = _pct(n, total_plants)
        if share >= 70:
            findings.append(
                {
                    "code": "site_preference",
                    "title": f"They go {site} — {share}% of the time",
                    "detail": f"{n} of {total_plants} plants at {site}. Conversion after "
                    f"planting there: {shape['plant_conversion_pct'].get(site)}%.",
                    "evidence": {"plants": plants, "conversion": shape["plant_conversion_pct"]},
                }
            )

    # 4. Where they die -- the areas where they lose control.
    n = func.count(KillEvent.id)
    death_spots = db().execute(
        select(KillEvent.victim_place, n)
        .join(Round, Round.id == KillEvent.round_id)
        .where(
            Round.match_map_id.in_(map_ids),
            KillEvent.victim_id.in_(_ever_played_for(team.id)),
            KillEvent.victim_place != "",
        )
        .group_by(KillEvent.victim_place)
        .order_by(n.desc())
        .limit(4)
    )
    spots = [{"place": place, "deaths": int(count)} for place, count in death_spots]
    if spots and spots[0]["deaths"] >= 5:
        findings.append(
            {
                "code": "death_clusters",
                "title": f"They keep dying at {spots[0]['place']}",
                "detail": "Deaths cluster at "
                + ", ".join(f"{s['place']} ({s['deaths']})" for s in spots)
                + " — contest those areas.",
                "evidence": {"places": spots},
            }
        )

    # 5. One-man dependency: if their opening game runs through a single player.
    total_openings = sum(p["opening_kills"] for p in profiles)
    if total_openings >= 8:
        leader = max(profiles, key=lambda p: p["opening_kills"])
        share = _pct(leader["opening_kills"], total_openings)
        if share >= 40:
            findings.append(
                {
                    "code": "opening_dependency",
                    "title": f"{leader['name']} takes {share}% of their opening kills",
                    "detail": f"{leader['opening_kills']} of {total_openings}. "
                    "Trade him early and their round structure stalls.",
                    "evidence": {
                        "player": leader["name"],
                        "opening_kills": leader["opening_kills"],
                        "team_total": total_openings,
                    },
                    "player": leader["name"],
                }
            )

    # 6. Over-aggression: players who die first far more than they open.
    reckless = [
        p
        for p in profiles
        if p["opening_deaths"] >= 4 and p["opening_deaths"] >= p["opening_kills"] * 2
    ]
    if reckless:
        findings.append(
            {
                "code": "over_aggression",
                "title": "They give away first blood",
                "detail": "; ".join(
                    f"{p['name']} {p['opening_deaths']} opening deaths "
                    f"to {p['opening_kills']} kills"
                    for p in reckless
                ),
                "evidence": {"players": [p["name"] for p in reckless]},
            }
        )

    # 7. Utility discipline.
    gpr = shape["grenades_per_round"]
    if gpr is not None and shape["rounds"] >= 20 and gpr < 4:
        findings.append(
            {
                "code": "low_utility",
                "title": "They under-use utility",
                "detail": f"{gpr} tracked smokes and molotovs per round. Sites are likely "
                "to be taken without full execute support.",
                "evidence": {"grenades_per_round": gpr, "rounds": shape["rounds"]},
            }
        )

    return findings


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


# -- player-vs-player ----------------------------------------------------------
def matchup_report(
    my_team: Team, opponent: Team, h2h_maps: Iterable[MatchMap], side: str | None = None
) -> dict:
    """Who on our side handles who on theirs, and from where.

    Built from :class:`PlayerMapDuel`, which stores each cross-team kill with the
    positions both players were standing in. A matchup is a row paired with its
    mirror: ours-killing-theirs against theirs-killing-ours, so a positive net is
    a duel we actually win rather than one we merely take part in.

    ``side`` restricts this to the duels that happened while ``my_team`` played
    that side. ``PlayerMapDuel.side`` is the *killer's* side, so "my_team on ct"
    covers both our kills (``side="ct"``) and our deaths (``side="t"``).
    """
    empty = {"pairs": [], "by_my_player": [], "by_their_player": [], "totals": {}}
    map_ids = [m.id for m in h2h_maps]
    if not map_ids:
        return empty

    query = (
        select(PlayerMapDuel)
        .where(PlayerMapDuel.match_map_id.in_(map_ids))
        .options(joinedload(PlayerMapDuel.killer), joinedload(PlayerMapDuel.victim))
    )
    if side:
        opposite = "t" if side == "ct" else "ct"
        query = query.where(
            or_(
                and_(PlayerMapDuel.side == side, PlayerMapDuel.killer_team_id == my_team.id),
                and_(PlayerMapDuel.side == opposite, PlayerMapDuel.killer_team_id == opponent.id),
            )
        )
    rows = list(db().scalars(query))
    if not rows:
        return empty

    # (mine, theirs) -> what happened both ways
    pairs: dict[tuple, dict] = {}
    for row in rows:
        ours_killed = row.killer_team_id == my_team.id
        mine_id = row.killer_id if ours_killed else row.victim_id
        theirs_id = row.victim_id if ours_killed else row.killer_id
        mine_name = row.killer.name if ours_killed else row.victim.name
        theirs_name = row.victim.name if ours_killed else row.killer.name

        entry = pairs.setdefault(
            (mine_id, theirs_id),
            {
                "mine": mine_name,
                "mine_id": mine_id,
                "theirs": theirs_name,
                "theirs_id": theirs_id,
                "kills_for": 0,
                "kills_against": 0,
                "opening_for": 0,
                "opening_against": 0,
                "won_from": Counter(),
                "lost_at": Counter(),
                "sides": Counter(),
            },
        )
        if ours_killed:
            entry["kills_for"] += row.kills
            entry["opening_for"] += row.opening_kills
            if row.killer_place:
                entry["won_from"][row.killer_place] += row.kills
            entry["sides"][row.side or "?"] += row.kills
        else:
            entry["kills_against"] += row.kills
            entry["opening_against"] += row.opening_kills
            if row.victim_place:
                entry["lost_at"][row.victim_place] += row.kills

    out_pairs = []
    for entry in pairs.values():
        duels = entry["kills_for"] + entry["kills_against"]
        out_pairs.append(
            {
                "mine": entry["mine"],
                "mine_id": entry["mine_id"],
                "theirs": entry["theirs"],
                "theirs_id": entry["theirs_id"],
                "kills_for": entry["kills_for"],
                "kills_against": entry["kills_against"],
                "net": entry["kills_for"] - entry["kills_against"],
                "duels": duels,
                "win_pct": _pct(entry["kills_for"], duels),
                "opening_for": entry["opening_for"],
                "opening_against": entry["opening_against"],
                "won_from": [{"place": p, "count": n} for p, n in entry["won_from"].most_common(3)],
                "lost_at": [{"place": p, "count": n} for p, n in entry["lost_at"].most_common(3)],
                "verdict": _duel_verdict(entry["kills_for"], entry["kills_against"], duels),
            }
        )
    out_pairs.sort(key=lambda p: (-p["net"], -p["duels"]))

    return {
        "pairs": out_pairs,
        "by_my_player": _matchup_by_player(out_pairs, "mine", "theirs"),
        "by_their_player": _matchup_by_player(out_pairs, "theirs", "mine", flip=True),
        "totals": {
            "kills_for": sum(p["kills_for"] for p in out_pairs),
            "kills_against": sum(p["kills_against"] for p in out_pairs),
            "duels": sum(p["duels"] for p in out_pairs),
        },
    }


def _duel_verdict(won: int, lost: int, duels: int) -> str:
    """Only call a matchup either way when there is enough of it to mean anything."""
    if duels < 3:
        return "thin"
    if won - lost >= 2:
        return "good"
    if lost - won >= 2:
        return "bad"
    return "even"


def _matchup_by_player(pairs: list[dict], key: str, other: str, flip: bool = False) -> list[dict]:
    """Group the pairs under one side's players, best matchup first."""
    grouped: dict[str, dict] = {}
    for pair in pairs:
        entry = grouped.setdefault(
            pair[key],
            {
                "player": pair[key],
                "player_id": pair[f"{key}_id"],
                "kills_for": 0,
                "kills_against": 0,
                "opponents": [],
            },
        )
        won = pair["kills_against"] if flip else pair["kills_for"]
        lost = pair["kills_for"] if flip else pair["kills_against"]
        entry["kills_for"] += won
        entry["kills_against"] += lost
        entry["opponents"].append(
            {
                "name": pair[other],
                "kills_for": won,
                "kills_against": lost,
                "net": won - lost,
                "duels": pair["duels"],
                "win_pct": _pct(won, pair["duels"]),
                "verdict": _duel_verdict(won, lost, pair["duels"]),
                "won_from": pair["lost_at"] if flip else pair["won_from"],
                "lost_at": pair["won_from"] if flip else pair["lost_at"],
            }
        )

    out = []
    for entry in grouped.values():
        entry["opponents"].sort(key=lambda o: (-o["net"], -o["duels"]))
        entry["net"] = entry["kills_for"] - entry["kills_against"]
        best = [o for o in entry["opponents"] if o["verdict"] == "good"]
        worst = [o for o in entry["opponents"] if o["verdict"] == "bad"]
        entry["advice"] = _matchup_advice(entry["player"], best, worst)
        out.append(entry)
    out.sort(key=lambda e: -e["net"])
    return out


def _matchup_advice(player: str, best: list[dict], worst: list[dict]) -> str:
    if best and worst:
        return (
            f"{player} handles {best[0]['name']} "
            f"({best[0]['kills_for']}-{best[0]['kills_against']}) but loses to "
            f"{worst[0]['name']} ({worst[0]['kills_for']}-{worst[0]['kills_against']})."
        )
    if best:
        spot = best[0]["won_from"][0]["place"] if best[0]["won_from"] else None
        return (
            f"{player} wins his duels with {best[0]['name']} "
            f"({best[0]['kills_for']}-{best[0]['kills_against']})"
            + (f", mostly from {spot}." if spot else ".")
        )
    if worst:
        spot = worst[0]["lost_at"][0]["place"] if worst[0]["lost_at"] else None
        return (
            f"{player} keeps losing to {worst[0]['name']} "
            f"({worst[0]['kills_for']}-{worst[0]['kills_against']})"
            + (f", usually at {spot}." if spot else ".")
        )
    return f"{player} has no settled matchup either way yet."


def _headline(p: dict) -> dict:
    return {
        k: p[k]
        for k in (
            "rounds",
            "kills",
            "deaths",
            "kd_diff",
            "adr",
            "kast_pct",
            "hs_pct",
            "opening_kills",
            "opening_deaths",
        )
    }


def _ratio(numerator, denominator, nd: int = 1):
    return round(numerator / denominator, nd) if denominator else 0.0


def _pct(numerator, denominator, nd: int = 1):
    return round(numerator / denominator * 100, nd) if denominator else 0.0


def _mean(values) -> float:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else 0.0
