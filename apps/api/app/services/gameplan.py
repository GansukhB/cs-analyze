"""The match-preparation view: how do we beat this specific opponent.

:mod:`scouting` says what happened between the two, :mod:`roles` what job each
man does, :mod:`mapstrategy` how a map is played. This module answers the only
question a coach has on the day -- *where is the win* -- by putting all three
next to the head-to-head record and turning the gaps into instructions.

**Every number on the page is computed, not narrated.** Each team's metrics are
z-scored against the pool of every team parsed, and a metric only becomes a
"strength" when it is measurably above that pool. Sample size is carried on
every panel.

The duel matrix is keyed by ``(our player, their player)`` tuples, so the report
is not JSON as-is; :mod:`app.routers.gameplan` flattens those keys at the
boundary.

Ported from cstat's ``hltv/services/gameplan.py``.
"""

from __future__ import annotations

import logging
import math
import statistics
from collections import defaultdict
from collections.abc import Iterable, Mapping

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload

from app.models import (
    KillEvent,
    MapRoster,
    MatchMap,
    Player,
    PlayerMap,
    PlayerMapDuel,
    PlayerMapPosition,
    PlayerMapUtility,
    PlayerRound,
    PositionKind,
    Round,
    Team,
)
from app.services import (
    dbctx,
    lineup,
    map_pool,
    mapstrategy,
    playerplan,
    pool_cache,
    roles,
    scope,
    scouting,
    stats,
    window,
)
from app.services.dbctx import count_if, db, memo, total

logger = logging.getLogger(__name__)

# A team needs this many rounds before it joins the comparison pool: the size of
# a two-map series. At 80 only three teams qualified, two of them the pair being
# compared, so every z-score was measured against the subjects themselves.
MIN_POOL_ROUNDS = 40
# Standard deviations from the pool mean before a metric is called out.
STRENGTH_Z = 0.8
WEAKNESS_Z = -0.8
# Duels below this are drawn hatched and never generate advice.
MIN_DUELS = 4


# --------------------------------------------------------------- metrics -----
# name -> (label, higher_is_better, unit, why it matters in one line)
METRICS: dict[str, tuple] = {
    "ct_win_pct": ("CT round win", True, "%", "Holding sites and retaking."),
    "t_win_pct": ("T round win", True, "%", "Getting space and getting the bomb down."),
    "pistol_win_pct": ("Pistol rounds", True, "%", "Two pistols are worth up to six rounds."),
    "opening_win_pct": ("Opening duels", True, "%", "Who wins first contact."),
    "plant_rate": ("Plant rate on T", True, "%", "How often a T round reaches a plant."),
    "post_plant_win_pct": ("Post-plant hold", True, "%", "Converting a plant into a round."),
    "retake_win_pct": ("Retakes", True, "%", "Taking the round back after they plant."),
    "traded_death_pct": ("Deaths traded", True, "%", "Whether anyone is behind the man who dies."),
    "multi_kill_rate": ("Multi-kill rounds", True, "/round", "Rounds one player takes over."),
    "adr": ("ADR", True, "", "Raw damage output per round."),
    "kast_pct": ("KAST", True, "%", "How often a player contributes at all."),
    "util_per_round": ("Utility thrown", True, "/round", "Smokes and molotovs per round."),
}


def team_metrics(team: Team, match_maps: Iterable[MatchMap]) -> dict:
    """The metric vector for one team over a set of maps.

    Side rates come from ``Round.ct_team`` / ``Round.t_team``, never from
    ``winner_side`` -- sides swap at 13, so a tally of CT wins is not a CT record.
    """
    match_maps = list(match_maps)
    map_ids = [m.id for m in match_maps]
    if not map_ids:
        return {}
    session = db()

    rounds = [
        r._asdict()
        for r in session.execute(
            select(
                Round.id,
                Round.number,
                Round.winner_team_id,
                Round.ct_team_id,
                Round.t_team_id,
                Round.bomb_plant_tick,
            ).where(Round.match_map_id.in_(map_ids))
        )
    ]
    ct = [r for r in rounds if r["ct_team_id"] == team.id]
    t = [r for r in rounds if r["t_team_id"] == team.id]
    ours = ct + t
    if not ours:
        return {}

    pistols = mapstrategy.pistol_rounds(r["number"] for r in ours)
    pistol_rounds = [r for r in ours if r["number"] in pistols]
    planted = [r for r in t if r["bomb_plant_tick"] is not None]
    faced = [r for r in ct if r["bomb_plant_tick"] is not None]

    pr_rounds, kast, traded, deaths, opening_k, opening_d, multi = (
        int(v or 0)
        for v in session.execute(
            select(
                func.count(PlayerRound.id),
                count_if(PlayerRound.kast),
                count_if(PlayerRound.traded),
                total(PlayerRound.deaths),
                count_if(PlayerRound.opening_kill),
                count_if(PlayerRound.opening_death),
                count_if(PlayerRound.kills >= 3),
            ).where(
                PlayerRound.round_id.in_(select(Round.id).where(Round.match_map_id.in_(map_ids))),
                PlayerRound.team_id == team.id,
            )
        ).one()
    )
    pm_damage, pm_rounds = (
        int(v or 0)
        for v in session.execute(
            select(total(PlayerMap.damage), total(PlayerMap.rounds_played)).where(
                PlayerMap.match_map_id.in_(map_ids), PlayerMap.team_id == team.id
            )
        ).one()
    )
    smokes, infernos, flashes = (
        int(v or 0)
        for v in session.execute(
            select(
                total(PlayerMapUtility.smokes),
                total(PlayerMapUtility.infernos),
                total(PlayerMapUtility.flash_assists),
            ).where(PlayerMapUtility.match_map_id.in_(map_ids), PlayerMapUtility.team_id == team.id)
        ).one()
    )

    def won(rows):
        return sum(1 for r in rows if r["winner_team_id"] == team.id)

    return {
        "rounds": len(ours),
        "maps": len(match_maps),
        "ct_rounds": len(ct),
        "t_rounds": len(t),
        "ct_win_pct": _pct(won(ct), len(ct)),
        "t_win_pct": _pct(won(t), len(t)),
        "pistol_win_pct": _pct(won(pistol_rounds), len(pistol_rounds)),
        "pistols_played": len(pistol_rounds),
        "opening_win_pct": _pct(opening_k, opening_k + opening_d),
        "plant_rate": _pct(len(planted), len(t)),
        "post_plant_win_pct": _pct(won(planted), len(planted)),
        "plants": len(planted),
        "retake_win_pct": _pct(won(faced), len(faced)),
        "retakes_faced": len(faced),
        "traded_death_pct": _pct(traded, deaths),
        "multi_kill_rate": _ratio(multi, pr_rounds, 3),
        "adr": _ratio(pm_damage, pm_rounds),
        "kast_pct": _pct(kast, pr_rounds),
        "util_per_round": _ratio(smokes + infernos, len(ours), 2),
        "flash_assists": flashes,
        # The denominators TM-9's test needs.
        "openings": opening_k + opening_d,
        "deaths": deaths,
        "player_rounds": pr_rounds,
    }


def _teams_with_parsed_maps() -> list[Team]:
    played = (
        select(Round.ct_team_id)
        .join(MatchMap, MatchMap.id == Round.match_map_id)
        .where(MatchMap.parsed_at.is_not(None))
    )
    return list(db().scalars(select(Team).where(Team.id.in_(played)).order_by(Team.name)))


# Bump when a metric or the pool's arithmetic changes: the whole pool is kept in
# Redis under this and the parse stamp (`pool_cache`).
METRIC_POOL_SCHEMA = 1


def metric_pool(exclude: Team | None = None) -> dict[str, dict]:
    """Mean and spread of every metric across all teams with enough rounds.

    The yardstick "strength" is measured against; without it the page compares
    the two teams to each other, which on a 6-1 fixture says only "they are better".
    The whole pool is computed once per parse and shared through Redis.
    """

    def compute():
        values: dict[str, list] = defaultdict(list)
        for team in _teams_with_parsed_maps():
            if exclude is not None and team.id == exclude.id:
                continue
            with window.none():  # the Pool is every Team over everything (TM-3)
                m = team_metrics(team, mapstrategy.maps_in_window(team))
            if not m or m.get("rounds", 0) < MIN_POOL_ROUNDS:
                continue
            for key in METRICS:
                v = m.get(key)
                if isinstance(v, int | float):
                    values[key].append(float(v))

        out = {}
        for key, vals in values.items():
            if len(vals) < 3:
                continue
            mean = statistics.fmean(vals)
            sd = statistics.pstdev(vals)
            # The floor scales with the metric, or it silences the small ones
            # (multi_kill_rate sits around 0.04).
            floor = max(abs(mean) * 0.10, 1e-6)
            out[key] = {"mean": round(mean, 4), "sd": round(max(sd, floor), 5), "n": len(vals)}
        return out

    if exclude is not None:
        return memo(("metric_pool", exclude.id), compute)
    key = f"pool:metrics:v{METRIC_POOL_SCHEMA}:{pool_cache.parse_stamp()}"
    return memo(("metric_pool", None), lambda: pool_cache.remember(key, compute))


def parsed_maps() -> list[MatchMap]:
    """Every parsed Match Map: what the Pool's role signals are measured on."""
    return list(
        db()
        .scalars(
            select(MatchMap)
            .options(joinedload(MatchMap.match), joinedload(MatchMap.game_map))
            .where(MatchMap.parsed_at.is_not(None))
        )
        .unique()
    )


def warm_pool() -> None:
    """Compute the Pool for the current parse unless some process already has.

    The worker calls it after each Match a Scout parses, after re-parsing and when
    it starts, so a Game Plan opened later finds the Pool in Redis. Never raises.
    """
    from app.db import SessionLocal

    try:
        with SessionLocal() as session, dbctx.using(session):
            # The Pool every Workspace without uploads reads (docs/adr/0011).
            scope.bind(session, None)
            roles.pool_signals(parsed_maps())
            metric_pool()
    except Exception:
        logger.exception("could not warm the Pool")


def profile_team(
    team: Team,
    *,
    since=None,
    until=None,
    pool: dict | None = None,
    exclude_opponent: Team | None = None,
) -> dict:
    """One team's metrics, plus which of them are genuinely strong or weak.

    ``exclude_opponent`` drops the maps played against the fixture opponent: a
    team 1-6 against this opponent would otherwise read as bad at all twelve.
    Their own matches say what their level is; :func:`h2h_delta` says what changes
    when this opponent is across the server.
    """
    maps = mapstrategy.maps_in_window(team, since=since, until=until)
    if exclude_opponent is not None:
        against = {
            m.id
            for m in mapstrategy.maps_in_window(
                team, since=since, until=until, opponent=exclude_opponent
            )
        }
        maps = [m for m in maps if m.id not in against]
    metrics = team_metrics(team, maps)
    if pool is None:
        pool = metric_pool()

    strengths, weaknesses, neutral = [], [], []
    for key, (label, higher_better, unit, why) in METRICS.items():
        value = metrics.get(key)
        stat = pool.get(key)
        if value is None or stat is None:
            continue
        z = (float(value) - stat["mean"]) / stat["sd"]
        if not higher_better:
            z = -z
        row = {
            "key": key,
            "label": label,
            "value": value,
            "unit": unit,
            "why": why,
            "pool_mean": stat["mean"],
            "z": round(z, 2),
            "pool_n": stat["n"],
            "sample": _metric_sample(key, metrics),
        }
        if z >= STRENGTH_Z:
            strengths.append(row)
        elif z <= WEAKNESS_Z:
            weaknesses.append(row)
        else:
            neutral.append(row)

    strengths.sort(key=lambda r: -r["z"])
    weaknesses.sort(key=lambda r: r["z"])
    ranked = sorted(strengths + neutral + weaknesses, key=lambda r: -r["z"])
    empty_note = ""
    if not maps:
        empty_note = (
            f"Every parsed {team.name} map is against this opponent, so there is no "
            "independent form to measure. Parse one of their other matches and this "
            "panel fills in."
        )
    elif not ranked:
        empty_note = (
            f"{len(maps)} parsed map(s), but not enough rounds for any metric "
            "to be scored against the pool."
        )
    return {
        "team": team.name,
        "team_id": team.id,
        "metrics": metrics,
        "maps": len(maps),
        "empty_note": empty_note,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "neutral": neutral,
        # A team with no metric clearing the bar still shows what it is
        # *relatively* best at -- reported as such, never relabelled a strength.
        "ranked": ranked,
        "best_relative": ranked[:3],
        "worst_relative": ranked[-3:][::-1],
    }


def h2h_delta(team: Team, opponent: Team) -> dict:
    """The same metrics measured only against this opponent, and the change."""
    versus_maps = mapstrategy.maps_in_window(team, opponent=opponent)
    versus_ids = {m.id for m in versus_maps}
    own = team_metrics(
        team, [m for m in mapstrategy.maps_in_window(team) if m.id not in versus_ids]
    )
    versus = team_metrics(team, versus_maps)
    if not own or not versus:
        return {"rows": [], "note": "Not enough parsed maps on one side of the split."}

    rows = []
    for key, (label, higher_better, unit, why) in METRICS.items():
        a, b = own.get(key), versus.get(key)
        if a is None or b is None:
            continue
        delta = round(float(b) - float(a), 2)
        judged = _delta_test(key, own, versus)
        rows.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "why": why,
                "own": a,
                "versus": b,
                "delta": delta,
                "worse": (delta < 0) if higher_better else (delta > 0),
                **judged,
            }
        )
    rows.sort(key=lambda r: r["delta"])
    return {
        "rows": rows,
        "own_rounds": own.get("rounds", 0),
        "versus_rounds": versus.get("rounds", 0),
        # TM-9: a collapse is a drop past its unit's bar that chance doesn't explain;
        # a hold is no drop on a sample big enough to have shown one.
        "collapses": [r for r in rows if r["worse"] and r["clear"]][:5],
        "holds": [r for r in rows if not r["worse"] and r["enough"]][:5],
    }


# kpi -> (its denominator in team_metrics, the value's scale: 100 for a percent).
# The rest (ADR, utility per round) are continuous.
DELTA_DENOM = {
    "ct_win_pct": ("ct_rounds", 100.0),
    "t_win_pct": ("t_rounds", 100.0),
    "pistol_win_pct": ("pistols_played", 100.0),
    "opening_win_pct": ("openings", 100.0),
    "plant_rate": ("t_rounds", 100.0),
    "post_plant_win_pct": ("plants", 100.0),
    "retake_win_pct": ("retakes_faced", 100.0),
    "traded_death_pct": ("deaths", 100.0),
    "kast_pct": ("player_rounds", 100.0),
    "multi_kill_rate": ("player_rounds", 1.0),
}
DELTA_MIN_EVENTS = 8  # against them, before a rate's change can be read
DELTA_MIN_POINTS = 5.0  # a rate must move this many points
DELTA_MIN_RELATIVE = 0.15  # a per-round number must move this share of its own value
DELTA_MIN_ROUNDS = 48  # two Match Maps against them, for a per-round number
DELTA_P = 0.10


def _delta_test(key: str, own: dict, versus: dict) -> dict:
    """Whether a metric's change against this opponent is past chance (TM-9)."""
    a, b = float(own[key]), float(versus[key])
    spec = DELTA_DENOM.get(key)
    if spec is None:
        enough = (versus.get("rounds") or 0) >= DELTA_MIN_ROUNDS
        moved = abs(b - a) >= DELTA_MIN_RELATIVE * max(abs(a), 1e-9)
        return {"enough": enough, "clear": enough and moved, "p": None}
    denom, scale = spec
    n_own, n_vs = float(own.get(denom) or 0), float(versus.get(denom) or 0)
    enough = n_vs >= DELTA_MIN_EVENTS
    if not enough or n_own <= 0:
        return {"enough": enough, "clear": False, "p": None}
    # Rounds of one Match Map aren't independent: discount both samples for it.
    e_own = stats.effective_n(n_own, n_own / max(1, own.get("maps") or 1))
    e_vs = stats.effective_n(n_vs, n_vs / max(1, versus.get("maps") or 1))
    p1, p2 = a / scale, b / scale
    pooled = (p1 * e_own + p2 * e_vs) / (e_own + e_vs)
    se = math.sqrt(max(pooled * (1 - pooled), 1e-9) * (1 / e_own + 1 / e_vs))
    p = math.erfc(abs(p2 - p1) / se / math.sqrt(2))
    return {
        "enough": True,
        "clear": p < DELTA_P and abs(p2 - p1) * 100 >= DELTA_MIN_POINTS * (scale / 100),
        "p": round(p, 4),
    }


def _metric_sample(key: str, metrics: dict) -> str:
    if key == "pistol_win_pct":
        return f"{metrics.get('pistols_played', 0)} pistol rounds"
    if key in ("plant_rate", "post_plant_win_pct"):
        return f"{metrics.get('plants', 0)} plants over {metrics.get('t_rounds', 0)} T rounds"
    if key == "retake_win_pct":
        return f"{metrics.get('retakes_faced', 0)} plants faced"
    if key == "ct_win_pct":
        return f"{metrics.get('ct_rounds', 0)} CT rounds"
    if key == "t_win_pct":
        return f"{metrics.get('t_rounds', 0)} T rounds"
    return f"{metrics.get('rounds', 0)} rounds"


# ---------------------------------------------------------------- duels ------
def duel_matrix(
    my_team: Team, opponent: Team, h2h_maps: Iterable[MatchMap], current_only: bool = True
) -> dict:
    """Who beats whom, ours down the side and theirs across the top.

    Restricted to players still fielded by default: a matrix of men who have left
    the roster is history.
    """
    h2h_maps = list(h2h_maps)
    map_ids = [m.id for m in h2h_maps]
    if not map_ids:
        return {"rows": [], "cols": [], "cells": {}, "note": "No head-to-head maps parsed."}

    # Players are told apart by id (Steam id), never by name: two can share one.
    mine_current = lineup.fielded(my_team)
    theirs_current = lineup.fielded(opponent)

    D = PlayerMapDuel
    by_id: dict[tuple, dict] = defaultdict(lambda: {"for": 0, "against": 0})
    for k_id, v_id, k_team, n in db().execute(
        select(D.killer_id, D.victim_id, D.killer_team_id, total(D.kills))
        .where(
            D.match_map_id.in_(map_ids),
            or_(
                and_(D.killer_team_id == my_team.id, D.victim_team_id == opponent.id),
                and_(D.killer_team_id == opponent.id, D.victim_team_id == my_team.id),
            ),
        )
        .group_by(D.killer_id, D.victim_id, D.killer_team_id)
    ):
        if k_team == my_team.id:
            by_id[(k_id, v_id)]["for"] += int(n or 0)
        else:
            by_id[(v_id, k_id)]["against"] += int(n or 0)

    names = _display_names({pid for pair in by_id for pid in pair})
    pairs = {(names[r], names[c]): d for (r, c), d in by_id.items()}
    row_ids = sorted({k[0] for k in by_id}, key=names.get)
    col_ids = sorted({k[1] for k in by_id}, key=names.get)
    rows_all = [names[r] for r in row_ids]
    cols_all = [names[c] for c in col_ids]
    rows = [names[r] for r in row_ids if r in mine_current] if current_only else rows_all
    cols = [names[c] for c in col_ids if c in theirs_current] if current_only else cols_all
    rows = rows or rows_all
    cols = cols or cols_all

    cells = {}
    for r in rows:
        for c in cols:
            d = pairs.get((r, c))
            if not d:
                continue
            cells[(r, c)] = {
                "for": d["for"],
                "against": d["against"],
                "net": d["for"] - d["against"],
                "thin": d["for"] + d["against"] < MIN_DUELS,
            }

    dropped_mine = [p for p in rows_all if p not in rows]
    dropped_theirs = [c for c in cols_all if c not in cols]
    return {
        "rows": rows,
        "cols": cols,
        "cells": cells,
        "dropped": {"mine": dropped_mine, "theirs": dropped_theirs},
        "note": _duel_note(dropped_mine, dropped_theirs),
        "totals": _duel_totals(rows, cols, cells),
    }


def _duel_note(dropped_mine, dropped_theirs) -> str:
    gone = dropped_mine + dropped_theirs
    if not gone:
        return ""
    return (
        "Hidden because they no longer play for either side: "
        + ", ".join(sorted(gone))
        + ". Their duels are history, not preparation."
    )


def _duel_totals(rows, cols, cells) -> list[dict]:
    out = []
    for r in rows:
        kf = sum(cells[(r, c)]["for"] for c in cols if (r, c) in cells)
        ka = sum(cells[(r, c)]["against"] for c in cols if (r, c) in cells)
        out.append({"name": r, "for": kf, "against": ka, "net": kf - ka, "duels": kf + ka})
    out.sort(key=lambda x: -x["net"])
    return out


def _current_lineup(team: Team) -> set:
    """The five fielded in that team's most recent parsed match."""
    return playerplan.current_lineup(team)


def _display_names(player_ids: set[int]) -> dict[int, str]:
    """Each Player's name, made unique: two Players can go by the same name."""
    rows = sorted(db().execute(select(Player.id, Player.name).where(Player.id.in_(player_ids))))
    out: dict[int, str] = {}
    taken: dict[str, int] = defaultdict(int)
    for pid, name in rows:
        taken[name] += 1
        out[pid] = name if taken[name] == 1 else f"{name} ({taken[name]})"
    return out


# ------------------------------------------------------------- map board -----
def map_board(my_team: Team, opponent: Team, *, since=None, until=None) -> dict:
    """Every map, both teams' record on it, and what to do in the veto."""

    def compute():
        mine = {p["map"]: p for p in mapstrategy.map_profiles(my_team, since=since, until=until)}
        theirs = {p["map"]: p for p in mapstrategy.map_profiles(opponent, since=since, until=until)}
        h2h = {
            p["map"]: p
            for p in mapstrategy.map_profiles(my_team, since=since, until=until, opponent=opponent)
        }
        names = sorted(set(map_pool.active_duty()) | set(mine) | set(theirs))
        board = []
        for name in names:
            m, t, h = mine.get(name), theirs.get(name), h2h.get(name)
            board.append(
                {
                    "map": name,
                    "mine": m,
                    "theirs": t,
                    "h2h": h,
                    "mine_pct": m["win_pct"] if m else None,
                    "theirs_pct": t["win_pct"] if t else None,
                    "verdict": _map_verdict(name, m, t, h),
                }
            )
        board.sort(key=lambda r: (-(r["verdict"]["rank"]), r["map"]))
        return {"board": board, "advice": _veto_advice(board)}

    return memo(("map_board", my_team.id, opponent.id, since, until), compute)


def _map_verdict(name: str, m, t, h) -> dict:
    """Pick / ban / avoid, with the reason spelled out.

    An unplayed map is never called a weakness of theirs: it is a hole in our
    research, a reason to go and parse a demo.
    """
    if m is None and t is None:
        return {
            "call": "unknown",
            "rank": 0,
            "why": "Энд аль ч багийн задлан шинжилсэн тоглолт алга.",
            "confidence": "none",
        }
    if t is None:
        return {
            "call": "blind",
            "rank": 1,
            "why": f"Бид энд {m['maps']} map тоглосон, тэднийх нэг ч задлагдаагүй. "
            "Энэ нь сул тал биш, судлагдаагүй л газар: итгэхээс өмнө demo задал.",
            "confidence": "none",
        }
    if m is None:
        return {
            "call": "avoid",
            "rank": 1,
            "why": f"Тэдний {t['maps']} map энд задлагдсан, бидэнд нэг ч алга. "
            "Харалгүй тоглох нь бэлтгэлийн давуу байдлыг тэдэнд өгнө.",
            "confidence": "low",
        }

    gap = (m["win_pct"] or 0) - (t["win_pct"] or 0)
    thin = m["thin"] or t["thin"]
    conf = "low" if thin else ("medium" if min(m["maps"], t["maps"]) < 3 else "high")
    if h and h["maps"] >= 2 and (h["win_pct"] or 0) <= 25:
        return {
            "call": "ban",
            "rank": 5,
            "why": f"Хоорондын {h['maps']} map-д тэд биднийг энд {h['lost']}-{h['won']} "
            "хожсон. Хориглох.",
            "confidence": conf,
        }
    if gap >= 20:
        return {
            "call": "pick",
            "rank": 4,
            "why": f"Бид энд {m['win_pct']}%, тэд {t['win_pct']}% ({gap:+.0f} нэгж).",
            "confidence": conf,
        }
    if gap <= -20:
        return {
            "call": "ban",
            "rank": 3,
            "why": f"Тэд энд {t['win_pct']}%, бид {m['win_pct']}% (бидний эсрэг {gap:+.0f} нэгж).",
            "confidence": conf,
        }
    return {
        "call": "contest",
        "rank": 2,
        "why": f"Ойролцоо: бид {m['win_pct']}%, тэд {t['win_pct']}%.",
        "confidence": conf,
    }


def _veto_advice(board) -> list[str]:
    out = []

    def calls(kind):
        return [b for b in board if b["verdict"]["call"] == kind]

    picks, bans, blind, avoid, unknown = (
        calls(k) for k in ("pick", "ban", "blind", "avoid", "unknown")
    )
    if bans:
        out.append(
            "Ban first: " + ", ".join(f"{b['map']} ({b['verdict']['why']})" for b in bans[:2])
        )
    if picks:
        out.append("Pick: " + ", ".join(f"{b['map']} ({b['verdict']['why']})" for b in picks[:2]))
    else:
        out.append(
            "Nothing in the parsed sample is a clear pick for us. That is the finding: "
            "this veto has to be won by banning, not by picking."
        )
    if blind:
        out.append(
            "They have no parsed games on "
            + ", ".join(b["map"] for b in blind)
            + " — we would be guessing. Parse one of their matches there before "
            "building a plan around it."
        )
    if avoid:
        out.append(
            "Avoid "
            + ", ".join(b["map"] for b in avoid)
            + " — they have demos there and we have none."
        )
    if unknown:
        out.append("No data either way on " + ", ".join(b["map"] for b in unknown) + ".")
    return out


# ------------------------------------------------------------ the report -----
class Report(Mapping):
    """The match-preparation report, computed one section at a time.

    Reading a key computes it; reading it again is free. A tab reads a handful of
    keys and the keys are not remotely equal in price (``map_matrix`` alone costs
    as much as the rest of the page), so each is paid by the tab that shows it.
    Intermediates (the metric pool, league baseline, role cohorts, each team's
    window) are built at most once per report.
    """

    KEYS = (
        "my_team",
        "opponent",
        "my_delta",
        "opponent_delta",
        "head_to_head",
        "h2h_maps",
        "continuity",
        "linchpins",
        "man_advantage",
        "board",
        "map_plans",
        "duels",
        "roles",
        "players",
        "map_matrix",
        "pool",
        "metrics_meta",
        "bombsite_health",
        "sample",
        "lede",
    )

    def __init__(self, my_team: Team, opponent: Team, *, since=None, until=None):
        self.my_team = my_team
        self.opponent = opponent
        self.since = since
        self.until = until
        self._cache: dict[str, object] = {}
        self._parts: dict[str, object] = {}

    def __getitem__(self, key):
        if key not in self._cache:
            if key not in self.KEYS:
                raise KeyError(key)
            self._cache[key] = getattr(self, f"_key_{key}")()
        return self._cache[key]

    def __iter__(self):
        return iter(self.KEYS)

    def __len__(self):
        return len(self.KEYS)

    # -- shared intermediates ------------------------------------------------
    def _part(self, name, build):
        if name not in self._parts:
            self._parts[name] = build()
        return self._parts[name]

    def _pool(self):
        return self._part("pool", metric_pool)

    def _h2h_maps(self):
        return self._part(
            "h2h_maps", lambda: scouting.head_to_head_maps(self.my_team, self.opponent)
        )

    def _all_parsed(self):
        return self._part("all_parsed", parsed_maps)

    def _signals(self):
        """Role signals for every parsed team, built once and shared by baseline and cohorts."""
        return self._part("signals", lambda: roles.pool_signals(self._all_parsed()))

    def _baseline(self):
        return self._part(
            "baseline", lambda: roles.league_baseline(self._all_parsed(), signals=self._signals())
        )

    def _cohorts(self):
        return self._part(
            "cohorts",
            lambda: roles.role_cohorts(
                self._all_parsed(), self._baseline(), signals=self._signals()
            ),
        )

    def _window(self, team):
        return self._part(f"window:{team.id}", lambda: mapstrategy.maps_in_window(team))

    def _profile_maps(self, team, against):
        """What `profile_team` measures a team on: its window minus the opponent's."""

        def build():
            against_maps = {m.id for m in mapstrategy.maps_in_window(team, opponent=against)}
            return [m for m in self._window(team) if m.id not in against_maps]

        return self._part(f"profilemaps:{team.id}", build)

    def _own_maps(self, team):
        """That team's maps excluding the fixture -- what own form is measured on."""

        def build():
            played = {m.id for m in self._h2h_maps()}
            return [m for m in self._window(team) if m.id not in played]

        return self._part(f"own:{team.id}", build)

    def _players(self, team, against):
        def build():
            out = playerplan.team_players(
                team, against, baseline=self._baseline(), cohorts=self._cohorts()
            )
            for p in out:
                p["instructions"] = playerplan.scout_instructions(
                    p, my_side=(team.id == self.my_team.id)
                )
            return out

        return self._part(f"players:{team.id}", build)

    def _profile(self, team, against):
        return self._part(
            f"profile:{team.id}",
            lambda: profile_team(
                team,
                since=self.since,
                until=self.until,
                pool=self._pool(),
                exclude_opponent=against,
            ),
        )

    def _roles_for(self, team):
        def build():
            picture = roles.rate_team(
                team, self._window(team), baseline=self._baseline(), cohorts=self._cohorts()
            )
            # A new signing in the Lineup is rated where they played (CONTEXT.md).
            for player in lineup.newcomers(team):
                found = lineup.elsewhere(player)
                if not found or not found[1]:
                    continue
                there = roles.rate_team(
                    found[0], found[1], baseline=self._baseline(), cohorts=self._cohorts()
                )
                entry = next((p for p in there["players"] if p["name"] == player.name), None)
                if entry:
                    picture["players"].append(
                        {**entry, "in_current_lineup": True, "elsewhere": found[0].name}
                    )
            return picture

        return self._part(f"roles:{team.id}", build)

    # -- the keys ------------------------------------------------------------
    def _key_my_team(self):
        return self._profile(self.my_team, self.opponent)

    def _key_opponent(self):
        return self._profile(self.opponent, self.my_team)

    def _key_my_delta(self):
        return h2h_delta(self.my_team, self.opponent)

    def _key_opponent_delta(self):
        return h2h_delta(self.opponent, self.my_team)

    def _key_head_to_head(self):
        return scouting.head_to_head_report(self.my_team, self.opponent, self._h2h_maps())

    def _key_h2h_maps(self):
        return len(self._h2h_maps())

    def _key_continuity(self):
        return roster_continuity(self.my_team, self.opponent, self._h2h_maps())

    def _key_linchpins(self):
        # Counted over every Match Map, but only the Lineup is named: a man who
        # will not play is nobody to kill first or to protect.
        return {
            key: [
                pin
                for pin in linchpins(team, self._own_maps(team))
                if pin["player_id"] in lineup.fielded(team)
            ]
            for key, team in (("mine", self.my_team), ("opponent", self.opponent))
        }

    def _key_man_advantage(self):
        return {
            "mine": man_advantage(self.my_team, self._own_maps(self.my_team)),
            "opponent": man_advantage(self.opponent, self._own_maps(self.opponent)),
        }

    def _key_board(self):
        return map_board(self.my_team, self.opponent, since=self.since, until=self.until)

    def _key_map_plans(self):
        return all_map_plans(self.my_team, self.opponent, since=self.since, until=self.until)

    def _key_duels(self):
        return duel_matrix(self.my_team, self.opponent, self._h2h_maps())

    def _key_roles(self):
        mine = self._roles_for(self.my_team)
        theirs = self._roles_for(self.opponent)
        return {"mine": mine, "opponent": theirs, "comparison": _role_comparison(mine, theirs)}

    def _key_players(self):
        return {
            "mine": self._players(self.my_team, self.opponent),
            "opponent": self._players(self.opponent, self.my_team),
        }

    def _key_map_matrix(self):
        return playerplan.map_matrix(
            self.my_team,
            self.opponent,
            players_mine=self._players(self.my_team, self.opponent),
            players_theirs=self._players(self.opponent, self.my_team),
        )

    def _key_pool(self):
        return self._pool()

    def _key_metrics_meta(self):
        return {k: {"label": v[0], "unit": v[2], "why": v[3]} for k, v in METRICS.items()}

    def _key_bombsite_health(self):
        return mapstrategy.bombsite_health()

    def _key_lede(self):
        """The three map counts in the page header, without touching the pool."""
        return {
            "my_maps": len(self._profile_maps(self.my_team, self.opponent)),
            "opponent_maps": len(self._profile_maps(self.opponent, self.my_team)),
            "h2h_maps": len(self._h2h_maps()),
        }

    def _key_sample(self):
        return {
            "my_maps": self["my_team"]["maps"],
            "opponent_maps": self["opponent"]["maps"],
            "h2h_maps": len(self._h2h_maps()),
            "pool_teams": max((s["n"] for s in self._pool().values()), default=0),
        }


def build(my_team: Team, opponent: Team, *, since=None, until=None) -> Report:
    """The whole match-preparation page, computed on demand. See :class:`Report`."""
    return Report(my_team, opponent, since=since, until=until)


def _role_comparison(mine: dict, theirs: dict) -> list[dict]:
    """Our man against their man in the same job, per side."""
    out = []
    for side in ("t", "ct"):
        theirs_by_role: dict[str, list] = defaultdict(list)
        for p in theirs["players"]:
            if not p.get("in_current_lineup", True):
                continue
            verdict = p["roles"].get(side)
            if verdict and verdict["role"]:
                theirs_by_role[verdict["role"]].append(p)
        for p in mine["players"]:
            if not p.get("in_current_lineup", True):
                continue
            verdict = p["roles"].get(side)
            if not verdict or not verdict["role"]:
                continue
            fit = (p.get("fit") or {}).get(side) or {}
            rivals = theirs_by_role.get(verdict["role"]) or []
            rival = max(
                rivals,
                key=lambda r: ((r.get("fit") or {}).get(side) or {}).get("score") or -9,
                default=None,
            )
            rival_fit = ((rival.get("fit") or {}).get(side) or {}) if rival else {}
            mine_score, rival_score = fit.get("score"), rival_fit.get("score")
            out.append(
                {
                    "side": side,
                    "role": verdict["role"],
                    "role_label": verdict["label"],
                    "mine": p["name"],
                    "mine_fit": mine_score,
                    "theirs": rival["name"] if rival else None,
                    "theirs_fit": rival_score,
                    "delta": (
                        round(mine_score - rival_score, 2)
                        if mine_score is not None and rival_score is not None
                        else None
                    ),
                    "note": f"No {verdict['label'].lower()} on their side to compare against"
                    if not rival
                    else "",
                }
            )
    out.sort(key=lambda r: r["delta"] if r["delta"] is not None else 9)
    return out


def _pct(n, d, nd: int = 1) -> float:
    return round(n / d * 100, nd) if d else 0.0


def _ratio(n, d, nd: int = 1) -> float:
    return round(n / d, nd) if d else 0.0


# --------------------------------------------------------------- verdict -----
def verdict(report: Mapping, my_team: Team, opponent: Team) -> dict:
    """Гол дүгнэлт -- **бүтэцтэй**, текстгүй.

    ``kind`` ба тоонуудыг буцаана, монгол хэллэгийг :func:`app.services.mn.headline`
    болон бусад угсарна.
    """
    h2h = report["head_to_head"]["totals"]
    delta = report["my_delta"]
    board = report["board"]["board"]
    duels = report["duels"]
    continuity = report.get("continuity") or {}

    played = h2h.get("maps_played") or 0
    won, lost = h2h.get("maps_won") or 0, h2h.get("maps_lost") or 0

    facts, points, actions = {}, [], []
    facts["record"] = {
        "played": played,
        "won": won,
        "lost": lost,
        "my_team": my_team.name,
        "opponent": opponent.name,
    }
    facts["worst_side"] = None
    facts["top_collapse"] = None
    facts["stale"] = bool(continuity.get("stale"))
    facts["continuity"] = continuity

    # Only the delta-derived points need head-to-head maps; everything below is
    # each team's own form and is available with none.
    if played:
        by_key = {r["key"]: r for r in delta.get("rows", [])}
        t_drop = by_key.get("t_win_pct", {}).get("delta")
        ct_drop = by_key.get("ct_win_pct", {}).get("delta")
        # A Side is named only when it did drop against them; two Sides that held
        # or rose have no "worst".
        drops = {side: d for side, d in (("t", t_drop), ("ct", ct_drop)) if d is not None and d < 0}
        facts["worst_side"] = min(drops, key=drops.get) if drops else None
        collapses = delta.get("collapses") or []
        facts["top_collapse"] = collapses[0] if collapses else None
        for row in collapses[:3]:
            points.append({"kind": "collapse", **row})
        for row in (delta.get("holds") or [])[:2]:
            if row["key"] in METRICS:
                points.append({"kind": "holds", **row})

    pins_theirs = (report.get("linchpins") or {}).get("opponent") or []
    if pins_theirs and pins_theirs[0].get("significant") and pins_theirs[0]["swing"] >= 20:
        pin = pins_theirs[0]
        points.append({"kind": "linchpin_theirs", **pin})
        actions.append({"kind": "kill_first", **pin})
    pins_mine = (report.get("linchpins") or {}).get("mine") or []
    if pins_mine and pins_mine[0].get("significant") and pins_mine[0]["swing"] >= 20:
        actions.append({"kind": "protect", **pins_mine[0]})

    ma = report.get("man_advantage") or {}
    a, b = (ma.get("mine") or {}).get("up"), (ma.get("opponent") or {}).get("up")
    if a and b and a["reached"] >= 25 and b["reached"] >= 25 and a["win_pct"] >= b["win_pct"] - 2:
        points.append({"kind": "man_advantage_level", "mine": a, "theirs": b})
        actions.append({"kind": "play_numbers", "mine": a, "theirs": b})

    if facts["stale"]:
        actions.insert(0, {"kind": "stale_record", **continuity})

    bans = [x for x in board if x["verdict"]["call"] == "ban"]
    picks = [x for x in board if x["verdict"]["call"] == "pick"]
    blind = [x for x in board if x["verdict"]["call"] == "blind"]
    if bans:
        actions.append(
            {
                "kind": "ban",
                "maps": [{"map": x["map"], "why": x["verdict"]["why"]} for x in bans[:2]],
            }
        )
    if picks:
        actions.append({"kind": "pick", "map": picks[0]["map"], "why": picks[0]["verdict"]["why"]})
    else:
        actions.append({"kind": "no_pick"})
    if blind:
        actions.append({"kind": "parse_more", "maps": [x["map"] for x in blind]})

    losers = sorted(
        (t for t in duels.get("totals", []) if t["net"] <= -10 and t["duels"] >= 20),
        key=lambda t: t["net"],
    )
    for t in losers[:2]:
        actions.append({"kind": "duel_hole", **t})

    gaps = [r for r in report["roles"]["comparison"] if r.get("delta") is not None]
    if gaps:
        worst = min(gaps, key=lambda r: r["delta"])
        if worst["delta"] <= -0.4:
            actions.append({"kind": "role_gap", **worst})

    actions.append({"kind": "caveat", **report["sample"]})
    return {
        "facts": facts,
        "points": points,
        "actions": actions,
        "headline_kind": "normal" if played else "no_h2h",
    }


# ------------------------------------------------- roster continuity ---------
def roster_continuity(my_team: Team, opponent: Team, h2h_maps: Iterable[MatchMap]) -> dict:
    """How much of each side's current five actually set the head-to-head record."""
    h2h_maps = list(h2h_maps)
    if not h2h_maps:
        return {
            "available": False,
            "note": "No parsed head-to-head maps, so there is no record to qualify.",
        }

    out = {"available": True, "sides": {}}
    for key, team in (("mine", my_team), ("theirs", opponent)):
        current = lineup.fielded(team)
        played = set(
            db().scalars(
                select(MapRoster.player_id).where(
                    MapRoster.match_map_id.in_([m.id for m in h2h_maps]),
                    MapRoster.team_id == team.id,
                )
            )
        )
        names = _display_names(current | played)
        overlap = current & played
        out["sides"][key] = {
            "team": team.name,
            "current": sorted(names[p] for p in current),
            "played": sorted(names[p] for p in played),
            "overlap": sorted(names[p] for p in overlap),
            "unseen": sorted(names[p] for p in current - played),
            "n": len(overlap),
            "of": len(current) or 5,
        }
    out["stale"] = min(out["sides"]["mine"]["n"], out["sides"]["theirs"]["n"]) <= 3
    return out


# ------------------------------------------------ man-advantage --------------
def man_advantage(team: Team, match_maps: Iterable[MatchMap]) -> dict:
    """What a team does once it is a player up, and once it is a player down.

    Reconstructed from the kill feed: walk the alive counts down and record the
    first moment either side reaches a numbers advantage.
    """
    map_ids = [m.id for m in match_maps]
    if not map_ids:
        return {}
    session = db()
    rounds = {
        r.id: r
        for r in session.execute(
            select(Round.id, Round.winner_team_id, Round.ct_team_id, Round.t_team_id).where(
                Round.match_map_id.in_(map_ids)
            )
        )
    }
    if not rounds:
        return {}

    by_round: dict[int, list] = defaultdict(list)
    for round_id, tick, victim_side in session.execute(
        select(KillEvent.round_id, KillEvent.tick, KillEvent.victim_side)
        .where(KillEvent.round_id.in_(list(rounds)), KillEvent.victim_side != "")
        .order_by(KillEvent.tick)
    ):
        by_round[round_id].append((tick, victim_side))

    up = {"reached": 0, "won": 0}
    down = {"reached": 0, "won": 0}
    for round_id, kills in by_round.items():
        rnd = rounds.get(round_id)
        if rnd.ct_team_id == team.id:
            ours, theirs = "ct", "t"
        elif rnd.t_team_id == team.id:
            ours, theirs = "t", "ct"
        else:
            continue
        alive = {"ct": 5, "t": 5}
        first = None
        for _tick, side in sorted(kills):
            if side not in alive:
                continue
            alive[side] -= 1
            if alive[ours] != alive[theirs]:
                first = "up" if alive[ours] > alive[theirs] else "down"
                break
        if first is None:
            continue
        bucket = up if first == "up" else down
        bucket["reached"] += 1
        bucket["won"] += 1 if rnd.winner_team_id == team.id else 0

    return {
        "up": {**up, "win_pct": _pct(up["won"], up["reached"])},
        "down": {**down, "win_pct": _pct(down["won"], down["reached"])},
        "rounds": len(by_round),
    }


# ------------------------------------------------------------- linchpins -----
# Just after the median opening duel (29.5 s): an early death is one in the
# opening exchange rather than the mid-round.
EARLY_DEATH_SEC = 30.0
MIN_EARLY_DEATHS = 8


def linchpins(team: Team, match_maps: Iterable[MatchMap]) -> list[dict]:
    """Which player the team cannot afford to lose early.

    The team's round win rate when he died inside :data:`EARLY_DEATH_SEC`,
    against every other round. A star's rating stays high in the rounds he dies
    in; it is the team's result that collapses.
    """
    match_maps = list(match_maps)
    map_ids = [m.id for m in match_maps]
    if not map_ids:
        return []
    session = db()
    tickrates = {m.id: m.tickrate for m in match_maps}
    rounds = {
        r.id: r
        for r in session.execute(
            select(
                Round.id,
                Round.match_map_id,
                Round.freeze_end_tick,
                Round.winner_team_id,
                Round.ct_team_id,
                Round.t_team_id,
                Round.ct_buy,
                Round.t_buy,
            ).where(Round.match_map_id.in_(map_ids))
        )
    }
    ours = [rid for rid, r in rounds.items() if team.id in (r.ct_team_id, r.t_team_id)]
    if not ours:
        return []

    first_death: dict[tuple, int] = {}
    names: dict[int, str] = {}
    for round_id, tick, victim_id, victim_name in session.execute(
        select(KillEvent.round_id, KillEvent.tick, KillEvent.victim_id, Player.name)
        .join(Player, Player.id == KillEvent.victim_id)
        .where(KillEvent.round_id.in_(ours))
    ):
        key = (round_id, victim_id)
        if key not in first_death or tick < first_death[key]:
            first_death[key] = tick
        names[victim_id] = victim_name

    played: dict[int, set] = defaultdict(set)
    roster_of: dict[int, set] = defaultdict(set)
    for pid, map_id in session.execute(
        select(MapRoster.player_id, MapRoster.match_map_id).where(
            MapRoster.match_map_id.in_(map_ids), MapRoster.team_id == team.id
        )
    ):
        played[pid].add(map_id)
        roster_of[map_id].add(pid)

    deaths_in: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for (r_id, victim), tick in first_death.items():
        deaths_in[r_id].append((tick, victim))
    # Each round's first death of ours inside the window: (stratum, victim, won, map).
    openers = []
    for rid in ours:
        rnd = rounds[rid]
        rate = tickrates.get(rnd.match_map_id) or 64
        firsts = [
            (tick, victim)
            for tick, victim in deaths_in.get(rid, ())
            if victim in roster_of.get(rnd.match_map_id, ())
        ]
        if not firsts:
            continue
        tick, victim = min(firsts)
        if not 0 <= (tick - rnd.freeze_end_tick) / rate <= EARLY_DEATH_SEC:
            continue
        side = "ct" if rnd.ct_team_id == team.id else "t"
        buy = rnd.ct_buy if side == "ct" else rnd.t_buy
        openers.append(((side, buy or ""), victim, rnd.winner_team_id == team.id, rnd.match_map_id))

    out = []
    for pid in played:
        early_w = early_n = rest_w = rest_n = 0
        for rid in ours:
            rnd = rounds[rid]
            if rnd.match_map_id not in played[pid]:
                continue
            won = rnd.winner_team_id == team.id
            tick = first_death.get((rid, pid))
            rate = tickrates.get(rnd.match_map_id) or 64
            if tick is not None and 0 <= (tick - rnd.freeze_end_tick) / rate <= EARLY_DEATH_SEC:
                early_n += 1
                early_w += 1 if won else 0
            else:
                rest_n += 1
                rest_w += 1 if won else 0
        if early_n < MIN_EARLY_DEATHS:
            continue
        early_pct, rest_pct = _pct(early_w, early_n), _pct(rest_w, rest_n)
        # Against his teammates, not against rounds nobody died in: of the rounds the
        # team lost its first man inside the window, how much worse it does when that
        # man is him, Side by Side and buy by buy (docs/plans PL-8).
        gap, p, firsts = stats.stratified_gap(
            [(stratum, victim == pid, won) for stratum, victim, won, maps_id in openers
             if maps_id in played[pid]]
        )  # fmt: skip
        out.append(
            {
                "name": names.get(pid, str(pid)),
                "player_id": pid,
                "early_deaths": early_n,
                "early_won": early_w,
                "early_pct": early_pct,
                "other_rounds": rest_n,
                "other_won": rest_w,
                "other_pct": rest_pct,
                "swing": round(rest_pct - early_pct, 1),
                "first_deaths": firsts,
                "vs_teammates": round(100 * gap, 1),
                "p": round(p, 4),
            }
        )
    # Many players, one team: say a linchpin only past the false discovery rate.
    keep = stats.bh([r["p"] for r in out], q=stats.LFSR)
    for row, significant in zip(out, keep, strict=True):
        row["significant"] = bool(significant and row["first_deaths"] >= MIN_EARLY_DEATHS)
    out.sort(key=lambda r: (not r["significant"], -r["vs_teammates"], -r["swing"]))
    return out


# ------------------------------------------------------------- map plans -----
# Хаанаас алж байгаа нь ямар өнцөг хүлээхийг, хаана үхэж байгаа нь аль өнцгийг
# алдаж байгааг хэлнэ. Хоёул зөвхөн нэг газрын зургийн дотор утгатай.
PLAN_PLACES = 4


def map_plan(
    my_team: Team, opponent: Team, map_name: str, *, since=None, until=None
) -> dict | None:
    """Нэг газрын зургийн CT ба T төлөвлөгөө -- бичсэн биш, гаргаж авсан.

    Манай CT төлөвлөгөө *тэдний* T хагасаас, манай T төлөвлөгөө тэдний CT
    хагасаас гарна. Тэдний тоо дэмжихгүй зүйлийг бичихгүй.
    """
    ours = {p["map"]: p for p in mapstrategy.map_profiles(my_team, since=since, until=until)}.get(
        map_name
    )
    theirs = {
        p["map"]: p for p in mapstrategy.map_profiles(opponent, since=since, until=until)
    }.get(map_name)
    if ours is None and theirs is None:
        return None

    ct_plan, t_plan, cautions = [], [], []

    if theirs:
        plants, sites = theirs["plants"], theirs["plants"]["sites"]
        whole = sum(sites.values())
        if whole >= 8:
            top, n = max(sites.items(), key=lambda kv: kv[1])
            ct_plan.append(
                {
                    "kind": "their_site",
                    "site": top,
                    "plants": n,
                    "total": whole,
                    "share": round(n / whole, 3),
                    "conversion": (plants.get("conversion") or {}).get(top),
                }
            )
        elif whole:
            cautions.append({"kind": "few_plants", "plants": whole})

        median, map_median = plants.get("median_plant_sec"), plants.get("map_median_plant_sec")
        if median and map_median and plants["planted"] >= 6:
            gap = median - map_median
            if abs(gap) >= 12:
                ct_plan.append(
                    {
                        "kind": "fast_tempo" if gap < 0 else "slow_tempo",
                        "median": median,
                        "map_median": map_median,
                        "gap": round(gap, 1),
                        "plants": plants["planted"],
                        "map": map_name,
                    }
                )
        if plants.get("rush_plants", 0) >= 3:
            ct_plan.append(
                {"kind": "rushes", "rushes": plants["rush_plants"], "plants": plants["planted"]}
            )
        opening = theirs["opening"]
        if opening["won"] + opening["lost"] >= 20 and opening["win_pct"] >= 56:
            ct_plan.append({"kind": "they_win_openings", **opening})

        rt = theirs["retakes"]
        if rt["faced"] >= 8:
            if rt["win_pct"] <= 25:
                t_plan.append({"kind": "weak_retake", **rt})
            elif rt["win_pct"] >= 45:
                t_plan.append({"kind": "strong_retake", **rt})
        ct_side = theirs["ct"]
        if ct_side["rounds"] >= 20:
            t_plan.append(
                {
                    "kind": "their_ct_soft" if ct_side["win_pct"] < 50 else "their_ct_strong",
                    **ct_side,
                }
            )
        pistol = theirs["pistols"]
        if pistol["played"] >= 4 and pistol["win_pct"] <= 35:
            t_plan.append({"kind": "weak_pistols", **pistol})

    if ours:
        if ours["thin"]:
            cautions.append({"kind": "thin_own", "maps": ours["maps"]})
        if ours["ct"]["rounds"] >= 20 and ours["ct"]["win_pct"] < 40:
            cautions.append({"kind": "weak_own_ct", **ours["ct"]})
        if ours["retakes"]["faced"] >= 8 and ours["retakes"]["win_pct"] <= 15:
            cautions.append({"kind": "weak_own_retake", **ours["retakes"]})
    else:
        cautions.append({"kind": "no_own_data"})
    if not theirs:
        cautions.append({"kind": "no_their_data"})

    return {
        "map": map_name,
        "ct": ct_plan,
        "t": t_plan,
        "cautions": cautions,
        "ours": ours,
        "theirs": theirs,
        "hot_places": _hot_places(opponent, map_name),
    }


def _hot_places(team: Team, map_name: str) -> dict:
    """Энэ баг тухайн газрын зураг дээр хаанаас алж, хаана үхдэг вэ, талаар нь."""
    maps = [
        m.id for m in mapstrategy.maps_in_window(team) if m.game_map and m.game_map.name == map_name
    ]
    if not maps:
        return {}
    out: dict[str, dict[str, list]] = {}
    n = total(PlayerMapPosition.count)
    for side in ("ct", "t"):
        for kind, key in (
            (PositionKind.KILL_FROM, "kills_from"),
            (PositionKind.DEATH_AT, "dies_at"),
        ):
            rows = db().execute(
                select(PlayerMapPosition.place, n)
                .where(
                    PlayerMapPosition.match_map_id.in_(maps),
                    PlayerMapPosition.team_id == team.id,
                    PlayerMapPosition.side == side,
                    PlayerMapPosition.kind == kind,
                    PlayerMapPosition.place != "",
                )
                .group_by(PlayerMapPosition.place)
                .order_by(n.desc(), PlayerMapPosition.place)
                .limit(PLAN_PLACES)
            )
            out.setdefault(side, {})[key] = [{"place": place, "count": int(c)} for place, c in rows]
    return out


def all_map_plans(my_team: Team, opponent: Team, *, since=None, until=None) -> list[dict]:
    """Аль нэг тал нь тоглосон газрын зураг бүрийн төлөвлөгөө."""
    plans = []
    for row in map_board(my_team, opponent, since=since, until=until)["board"]:
        if row["verdict"]["call"] == "unknown":
            continue
        plan = map_plan(my_team, opponent, row["map"], since=since, until=until)
        if plan is None:
            continue
        plan["verdict"] = row["verdict"]
        plans.append(plan)
    return plans
