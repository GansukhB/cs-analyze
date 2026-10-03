"""Per-map tactical reading: how a team plays each map, and what to do about it.

:mod:`app.services.roles` answers "who is this player". This answers "how does
this team play Mirage" -- which side they hold, which site they hit, how fast
they hit it, whether they convert a plant, and whether their record is built on
pistols or on rifles. It is the layer a veto and a map-day plan come off.

Everything is scoped to a **map and a team**, and optionally to a date range,
because a team's map pool is the most volatile thing about them.

Two things this module is careful about:

* **Sides swap at round 13** and again every three rounds in overtime, so a
  tally of "CT rounds won" is not a team's CT record unless it is taken from
  ``Round.ct_team``. It always is here.
* **``Round.bomb_site`` was wrong for every row stored before schema version 7**
  (H11), so :func:`bombsite_health` exists to say whether the data has been
  fixed, and the report prints it rather than quietly producing a B-only map.

Ported from cstat's ``hltv/services/mapstrategy.py``.
"""

from __future__ import annotations

import logging
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.models import BombEvent, Match, MatchMap, PlayerRound, Round, Team
from app.services.dbctx import count_if, db, memo

logger = logging.getLogger(__name__)

# Below this a map profile is an anecdote: reported, flagged, never used for veto advice.
MIN_MAPS_FOR_READ = 2
MIN_ROUNDS_FOR_RATE = 24

# Plant timing is judged against the map, never against a fixed clock (the median
# plant is 78 s across the sample, so "60 s is slow" fires on everybody). What is
# informative is planting sooner or later *than the other teams on that map*.
FAST_PLANT_MARGIN = 12.0
SLOW_PLANT_MARGIN = 12.0
# Nothing legitimate plants this early except a rush; the fastest plant is 20.8 s.
RUSH_PLANT_SEC = 35.0
# Plants needed from *other* teams before a map's tempo is worth comparing against.
MIN_PLANTS_FOR_BASELINE = 8

ACTIVE_DUTY = (
    "de_ancient",
    "de_anubis",
    "de_dust2",
    "de_inferno",
    "de_mirage",
    "de_nuke",
    "de_overpass",
    "de_train",
)


def pistol_rounds(numbers: Iterable[int]) -> set:
    """Which round numbers are pistol rounds, for MR12 plus MR3 overtime (25, 28, 31...)."""
    out = set()
    for n in numbers:
        if n in (1, 13):
            out.add(n)
        elif n >= 25 and (n - 25) % 3 == 0:
            out.add(n)
    return out


def _plays(team_id: int):
    """EXISTS: the team held a side on some round of the map."""
    return (
        select(Round.id)
        .where(
            Round.match_map_id == MatchMap.id,
            or_(Round.ct_team_id == team_id, Round.t_team_id == team_id),
        )
        .exists()
    )


def _ordered(query):
    # Django's MatchMap ordering is ("match", "map_number"), and ordering by a
    # foreign key means the related model's ordering: newest match first.
    return query.join(Match, Match.id == MatchMap.match_id).order_by(
        Match.played_at.desc(), Match.hltv_id.desc(), MatchMap.map_number
    )


def maps_in_window(
    team: Team,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    opponent: Team | None = None,
) -> list[MatchMap]:
    """Every parsed map this team played, optionally inside a date window."""
    key = ("maps_in_window", team.id, since, until, opponent.id if opponent else None)
    return list(memo(key, lambda: _maps_in_window(team, since, until, opponent)))


def _maps_in_window(team, since, until, opponent) -> list[MatchMap]:
    query = _ordered(
        select(MatchMap)
        .where(MatchMap.parsed_at.is_not(None), _plays(team.id))
        .options(
            joinedload(MatchMap.match),
            joinedload(MatchMap.game_map),
            joinedload(MatchMap.team1),
            joinedload(MatchMap.team2),
            joinedload(MatchMap.winner),
        )
    )
    if since is not None:
        query = query.where(Match.played_at >= since)
    if until is not None:
        query = query.where(Match.played_at <= until)
    if opponent is not None:
        query = query.where(_plays(opponent.id))
    return list(db().scalars(query).unique())


def bombsite_health() -> dict:
    """Whether stored bombsites agree with the bomb feed (H11)."""
    session = db()
    total = session.scalar(
        select(func.count()).select_from(Round).where(Round.bomb_plant_tick.is_not(None))
    )
    if not total:
        return {
            "planted": 0,
            "checked": 0,
            "mismatched": 0,
            "healthy": True,
            "note": "No planted rounds stored.",
        }

    truth: dict = {}
    for round_id, tick, site in session.execute(
        select(BombEvent.round_id, BombEvent.tick, BombEvent.bombsite).where(
            BombEvent.event == "plant", BombEvent.bombsite != ""
        )
    ):
        truth.setdefault(round_id, {})[tick] = site

    checked = mismatched = 0
    for round_id, bomb_site, plant_tick in session.execute(
        select(Round.id, Round.bomb_site, Round.bomb_plant_tick).where(
            Round.bomb_plant_tick.is_not(None)
        )
    ):
        site = (truth.get(round_id) or {}).get(plant_tick)
        if site is None:
            continue
        checked += 1
        if site != bomb_site:
            mismatched += 1

    healthy = mismatched == 0
    return {
        "planted": total,
        "checked": checked,
        "mismatched": mismatched,
        "healthy": healthy,
        "note": (
            "Bombsites agree with the bomb feed."
            if healthy
            else f"{mismatched} of {checked} stored bombsites disagree with the bomb feed (H11). "
            "Every site number below is unreliable until they are repaired."
        ),
    }


# ------------------------------------------------------------- map profile ---
def map_profiles(team: Team, *, since=None, until=None, opponent: Team | None = None) -> list[dict]:
    """One tactical profile per map this team has played in the window."""
    key = ("map_profiles", team.id, since, until, opponent.id if opponent else None)
    return memo(key, lambda: _map_profiles(team, since, until, opponent))


def _map_profiles(team, since, until, opponent) -> list[dict]:
    match_maps = maps_in_window(team, since=since, until=until, opponent=opponent)
    if not match_maps:
        return []

    by_map: dict[str, list[MatchMap]] = defaultdict(list)
    for m in match_maps:
        by_map[m.game_map.name if m.game_map else "?"].append(m)

    baselines = plant_baselines(exclude_team=team)
    profiles = [_profile(team, name, maps, baselines) for name, maps in by_map.items()]
    profiles.sort(key=lambda p: (-p["maps"], -p["win_pct"]))
    return profiles


def plant_baselines(
    match_maps: Iterable[MatchMap] | None = None, *, exclude_team: Team | None = None
) -> dict[str, dict]:
    """Median seconds to plant on each map, across every *other* team parsed.

    ``exclude_team`` matters: a team that is the only one parsed on some map would
    otherwise be compared to a baseline made of its own rounds -- a tautology that
    reads like a finding. Excluded, the baseline has other teams in it or nothing.
    """
    if match_maps is None:
        key = ("plant_baselines", exclude_team.id if exclude_team else None)
        return memo(key, lambda: _plant_baselines(None, exclude_team))
    return _plant_baselines(match_maps, exclude_team)


def _plant_baselines(match_maps, exclude_team) -> dict[str, dict]:
    session = db()
    if match_maps is None:
        match_maps = session.scalars(
            select(MatchMap)
            .options(joinedload(MatchMap.game_map))
            .where(MatchMap.parsed_at.is_not(None))
        )
    maps = {}
    tickrates = {}
    for m in match_maps:
        maps[m.id] = m.game_map.name if m.game_map else "?"
        tickrates[m.id] = m.tickrate

    query = select(Round.match_map_id, Round.bomb_plant_tick, Round.freeze_end_tick).where(
        Round.match_map_id.in_(list(maps)), Round.bomb_plant_tick.is_not(None)
    )
    if exclude_team is not None:
        query = query.where(or_(Round.t_team_id.is_(None), Round.t_team_id != exclude_team.id))

    seconds: dict[str, list] = defaultdict(list)
    for map_id, plant_tick, freeze_tick in session.execute(query):
        rate = tickrates.get(map_id) or 64
        secs = (plant_tick - freeze_tick) / rate
        if 0 <= secs <= 200:
            seconds[maps[map_id]].append(secs)

    # A handful of plants is not a map's tempo: dropped rather than reported soft.
    return {
        name: {"median": round(statistics.median(v), 1), "plants": len(v)}
        for name, v in seconds.items()
        if len(v) >= MIN_PLANTS_FOR_BASELINE
    }


def _profile(team: Team, map_name: str, match_maps: list[MatchMap], baselines=None) -> dict:
    session = db()
    map_ids = [m.id for m in match_maps]
    tickrates = {m.id: m.tickrate for m in match_maps}
    rounds = [
        r._asdict()
        for r in session.execute(
            select(
                Round.id,
                Round.match_map_id,
                Round.number,
                Round.winner_team_id,
                Round.ct_team_id,
                Round.t_team_id,
                Round.end_reason,
                Round.bomb_site,
                Round.bomb_plant_tick,
                Round.freeze_end_tick,
            ).where(Round.match_map_id.in_(map_ids))
        )
    ]

    ct = [r for r in rounds if r["ct_team_id"] == team.id]
    t = [r for r in rounds if r["t_team_id"] == team.id]
    ours = ct + t

    # -- pistols: a separate game, and a record built on them is fragile
    pistols = pistol_rounds(r["number"] for r in ours)
    pistol_ours = [r for r in ours if r["number"] in pistols]
    pistol_won = [r for r in pistol_ours if r["winner_team_id"] == team.id]

    # -- T side: where they plant, how fast, and whether it holds
    planted = [r for r in t if r["bomb_plant_tick"] is not None]
    sites = Counter(r["bomb_site"] for r in planted if r["bomb_site"])
    site_conversion = {}
    for site in ("A", "B"):
        at = [r for r in planted if r["bomb_site"] == site]
        if at:
            won_there = sum(1 for r in at if r["winner_team_id"] == team.id)
            site_conversion[site] = {
                "plants": len(at),
                "won": won_there,
                "win_pct": _pct(won_there, len(at)),
            }
    plant_seconds = []
    for r in planted:
        rate = tickrates.get(r["match_map_id"]) or 64
        secs = (r["bomb_plant_tick"] - r["freeze_end_tick"]) / rate
        if 0 <= secs <= 200:
            plant_seconds.append(secs)

    # -- CT side: do they retake, or do they lose the site
    opp_planted = [r for r in ct if r["bomb_plant_tick"] is not None]
    retakes_won = sum(1 for r in opp_planted if r["winner_team_id"] == team.id)

    # -- opening duels on this map
    opening_k, opening_d = session.execute(
        select(count_if(PlayerRound.opening_kill), count_if(PlayerRound.opening_death))
        .join(Round, Round.id == PlayerRound.round_id)
        .where(Round.match_map_id.in_(map_ids), PlayerRound.team_id == team.id)
    ).one()
    opening_k, opening_d = int(opening_k or 0), int(opening_d or 0)

    results = []
    for m in match_maps:
        mine, theirs = _score_for(m, team)
        results.append(
            {
                "match": m.match.hltv_id,
                "played_at": m.match.played_at.isoformat() if m.match.played_at else None,
                "opponent": _opponent_name(m, team),
                "score": f"{mine}-{theirs}",
                "won": m.winner_id == team.id,
            }
        )
    results.sort(key=lambda r: r["played_at"] or "", reverse=True)

    rounds_for = sum(1 for r in ours if r["winner_team_id"] == team.id)
    rounds_against = len(ours) - rounds_for
    maps_won = sum(1 for m in match_maps if m.winner_id == team.id)
    ct_won = sum(1 for r in ct if r["winner_team_id"] == team.id)
    t_won = sum(1 for r in t if r["winner_team_id"] == team.id)
    planted_won = sum(1 for r in planted if r["winner_team_id"] == team.id)

    profile = {
        "map": map_name,
        "team": team.name,
        "maps": len(match_maps),
        "won": maps_won,
        "lost": len(match_maps) - maps_won,
        "win_pct": _pct(maps_won, len(match_maps)),
        "rounds": len(ours),
        "rounds_for": rounds_for,
        "rounds_against": rounds_against,
        "round_diff": rounds_for - rounds_against,
        "ct": {"rounds": len(ct), "won": ct_won, "win_pct": _pct(ct_won, len(ct))},
        "t": {"rounds": len(t), "won": t_won, "win_pct": _pct(t_won, len(t))},
        "pistols": {
            "played": len(pistol_ours),
            "won": len(pistol_won),
            "win_pct": _pct(len(pistol_won), len(pistol_ours)),
        },
        "plants": {
            "rounds": len(t),
            "planted": len(planted),
            "plant_pct": _pct(len(planted), len(t)),
            "sites": dict(sites),
            "site_pct": {s: _pct(n, sum(sites.values())) for s, n in sites.items()},
            "conversion": site_conversion,
            "won_after_plant": planted_won,
            "post_plant_win_pct": _pct(planted_won, len(planted)),
            "median_plant_sec": round(statistics.median(plant_seconds), 1)
            if plant_seconds
            else None,
            "rush_plants": sum(1 for s in plant_seconds if s <= RUSH_PLANT_SEC),
        },
        "retakes": {
            "faced": len(opp_planted),
            "won": retakes_won,
            "win_pct": _pct(retakes_won, len(opp_planted)),
        },
        "opening": {
            "won": opening_k,
            "lost": opening_d,
            "win_pct": _pct(opening_k, opening_k + opening_d),
        },
        "end_reasons": dict(Counter(r["end_reason"] for r in ours if r["end_reason"])),
        "results": results,
        "thin": len(match_maps) < MIN_MAPS_FOR_READ or len(ours) < MIN_ROUNDS_FOR_RATE,
    }
    base = (baselines or {}).get(map_name)
    profile["plants"]["map_median_plant_sec"] = base["median"] if base else None
    profile["plants"]["map_plants_sampled"] = base["plants"] if base else 0
    profile["notes"] = tactical_notes(profile)
    return profile


def _score_for(match_map: MatchMap, team: Team):
    if match_map.team1_id == team.id:
        return match_map.team1_score or 0, match_map.team2_score or 0
    return match_map.team2_score or 0, match_map.team1_score or 0


def _opponent_name(match_map: MatchMap, team: Team) -> str:
    other = match_map.team2 if match_map.team1_id == team.id else match_map.team1
    return other.name if other else "?"


# ------------------------------------------------------------------- notes ---
def tactical_notes(p: dict) -> list[dict]:
    """The findings a coach would write on the whiteboard, each with its numbers.

    Nothing fires on a sample too small to mean anything -- a 100% A-site
    preference over three plants is not a tendency, it is three rounds.
    """
    notes = []
    plants, sites = p["plants"], p["plants"]["sites"]
    total_plants = sum(sites.values())

    if total_plants >= 8:
        top, top_n = max(sites.items(), key=lambda kv: kv[1])
        share = top_n / total_plants
        if share >= 0.65:
            notes.append(
                _note(
                    "site-preference",
                    f"Hits {top} on {share:.0%} of plants ({top_n}/{total_plants}). "
                    f"Weight the {top} hold and stack utility for it.",
                    {"site": top, "plants": top_n, "of": total_plants},
                )
            )

    # A site they hit often but cannot hold is a retake opportunity, not a threat.
    for site, conv in (plants.get("conversion") or {}).items():
        if conv["plants"] >= 6 and conv["win_pct"] <= 55:
            notes.append(
                _note(
                    "weak-conversion",
                    f"Plants {site} {conv['plants']} times but only converts "
                    f"{conv['win_pct']}%. Let them have the plant and retake it.",
                    conv,
                )
            )

    median = plants.get("median_plant_sec")
    map_median = plants.get("map_median_plant_sec")
    if median is not None and plants["planted"] >= 6:
        rushes = plants.get("rush_plants", 0)
        if rushes >= 3:
            notes.append(
                _note(
                    "rushes",
                    f"{rushes} of {plants['planted']} plants inside {RUSH_PLANT_SEC:.0f}s — "
                    "they do run it. Keep one player deep and do not over-rotate early.",
                    {"rush_plants": rushes, "plants": plants["planted"]},
                )
            )
        if map_median is not None:
            delta = median - map_median
            evidence = {
                "median_plant_sec": median,
                "map_median_plant_sec": map_median,
                "plants": plants["planted"],
            }
            if delta <= -FAST_PLANT_MARGIN:
                notes.append(
                    _note(
                        "fast-for-the-map",
                        f"Plants at {median}s where the map averages {map_median}s "
                        f"({delta:+.0f}s). Faster than {p['map']} usually goes — commit "
                        "utility early rather than saving it for a late hit.",
                        evidence,
                    )
                )
            elif delta >= SLOW_PLANT_MARGIN:
                notes.append(
                    _note(
                        "slow-for-the-map",
                        f"Plants at {median}s where the map averages {map_median}s "
                        f"({delta:+.0f}s). They default longer than most — hold info, "
                        "keep utility for the last 40s and do not force early.",
                        evidence,
                    )
                )

    # Side imbalance is the single most actionable veto fact.
    ct, t = p["ct"], p["t"]
    if ct["rounds"] >= 20 and t["rounds"] >= 20:
        gap = ct["win_pct"] - t["win_pct"]
        if gap >= 20:
            notes.append(
                _note(
                    "ct-sided",
                    f"CT {ct['win_pct']}% vs T {t['win_pct']}% ({gap:+.0f} pts). "
                    "Their T side is the half to attack — take CT if the pick is theirs.",
                    {"ct": ct, "t": t},
                )
            )
        elif gap <= -20:
            notes.append(
                _note(
                    "t-sided",
                    f"T {t['win_pct']}% vs CT {ct['win_pct']}% ({-gap:+.0f} pts the other way). "
                    "Their CT side is the soft half.",
                    {"ct": ct, "t": t},
                )
            )

    pistol = p["pistols"]
    if pistol["played"] >= 4:
        if pistol["win_pct"] >= 70:
            notes.append(
                _note(
                    "pistol-strong",
                    f"Wins {pistol['won']}/{pistol['played']} pistols. Prepare a real "
                    "pistol setup — conceding these is conceding the map.",
                    pistol,
                )
            )
        elif pistol["win_pct"] <= 30:
            notes.append(
                _note(
                    "pistol-weak",
                    f"Wins only {pistol['won']}/{pistol['played']} pistols. Press the "
                    "pistol and the two rounds after it.",
                    pistol,
                )
            )

    retakes = p["retakes"]
    if retakes["faced"] >= 8 and retakes["win_pct"] <= 20:
        notes.append(
            _note(
                "no-retake",
                f"Retakes only {retakes['won']}/{retakes['faced']} ({retakes['win_pct']}%). "
                "Getting the bomb down against them is close to winning the round.",
                retakes,
            )
        )

    opening = p["opening"]
    if opening["won"] + opening["lost"] >= 20:
        if opening["win_pct"] >= 58:
            notes.append(
                _note(
                    "wins-openings",
                    f"Takes {opening['win_pct']}% of opening duels. Do not trade blind "
                    "into their first contact.",
                    opening,
                )
            )
        elif opening["win_pct"] <= 42:
            notes.append(
                _note(
                    "loses-openings",
                    f"Loses opening duels ({opening['win_pct']}%). Force first contact "
                    "early and play off the man advantage.",
                    opening,
                )
            )
    return notes


def _note(kind: str, text: str, evidence) -> dict:
    return {"kind": kind, "text": text, "evidence": evidence}


# ---------------------------------------------------------------- map pool ---
def map_pool(team: Team, *, since=None, until=None, profiles: list[dict] | None = None) -> dict:
    """Veto guidance: what they are good at, what they avoid, what is untested.

    "Untested" is a real category: a map with no parsed games is a blind spot,
    not a weakness, and telling a coach to ban it is worse than saying nothing.
    """
    if profiles is None:
        profiles = map_profiles(team, since=since, until=until)
    seen = {p["map"] for p in profiles}
    rated = [p for p in profiles if not p["thin"]]
    rated.sort(key=lambda p: (-p["win_pct"], -p["round_diff"]))
    unseen = [m for m in ACTIVE_DUTY if m not in seen]
    return {
        "team": team.name,
        "profiles": profiles,
        "strong": [_pool_row(p) for p in rated if p["win_pct"] >= 60][:3],
        "weak": [_pool_row(p) for p in reversed(rated) if p["win_pct"] <= 40][:3],
        "thin": [_pool_row(p) for p in profiles if p["thin"]],
        "unseen": unseen,
        "advice": _pool_advice(rated, [p for p in profiles if p["thin"]], unseen),
    }


def _pool_row(p: dict) -> dict:
    return {
        "map": p["map"],
        "maps": p["maps"],
        "won": p["won"],
        "lost": p["lost"],
        "win_pct": p["win_pct"],
        "round_diff": p["round_diff"],
        "ct_win_pct": p["ct"]["win_pct"],
        "t_win_pct": p["t"]["win_pct"],
        "thin": p["thin"],
    }


# A map has to be better than a coin flip before banning it is worth a veto slot.
BAN_WIN_PCT = 55.0
LEAVE_IN_WIN_PCT = 45.0


def _pool_advice(rated, thin, unseen) -> list[str]:
    out = []
    if rated:
        best = rated[0]
        if best["win_pct"] >= BAN_WIN_PCT:
            out.append(
                f"Ban {best['map']} — {best['won']}-{best['lost']} "
                f"({best['win_pct']}%, {best['round_diff']:+d} rounds), "
                "their strongest parsed map."
            )
        else:
            out.append(
                f"No standout to ban: their best rated map is {best['map']} at "
                f"{best['win_pct']}% ({best['won']}-{best['lost']}). On this sample "
                "the veto is better spent protecting your own pool than attacking theirs."
            )
        worst = rated[-1]
        if worst["map"] != best["map"] and worst["win_pct"] <= LEAVE_IN_WIN_PCT:
            out.append(
                f"Leave {worst['map']} in — {worst['won']}-{worst['lost']} "
                f"({worst['win_pct']}%, {worst['round_diff']:+d} rounds)."
            )
    if unseen:
        out.append(
            "No parsed games on "
            + ", ".join(unseen)
            + " — that is a blind spot, not a weakness of theirs. "
            "Parse a match on one before vetoing around it."
        )
    if thin:
        out.append(
            "Single-map samples ("
            + ", ".join(p["map"] for p in thin)
            + ") are not a read; they are one result."
        )
    if not rated:
        out.append(
            "Nothing in this window has enough maps to rank. Widen the "
            "date range or parse more matches."
        )
    return out


def _pct(numerator, denominator, nd: int = 1) -> float:
    return round(numerator / denominator * 100, nd) if denominator else 0.0
