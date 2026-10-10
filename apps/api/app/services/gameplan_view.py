"""What each game-plan panel shows, as JSON the page can render as-is.

cstat's ``views._gameplan_panel`` picked the report keys a panel reads and its
templates applied the Mongolian filters (``mn_map``, ``mn_role``, ``mn_plan``,
...). Both happen here: :func:`panel` reads only what its tab shows -- reading a
:class:`gameplan.Report` key is what computes it, so a key read in the wrong
branch is a panel paying for data it never shows -- and every label leaves the
server already worded, so the wording stays in :mod:`app.services.mn` alone.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import func, select

from app.models import MatchMap, Round, Team
from app.services import charts, decision, gameplan, levers, mn, playbook_view, review_pool
from app.services.dbctx import db

DEFAULT_TAB = "decision"

# The left-hand navigation, and with it the set of panels that exist. The nav
# computes nothing: only the two grid tabs carry a count, because theirs *is*
# the cheap query and it says whether there is anything in there before a click.
TABS = [
    {"key": "decision", "label": "Шийдвэр", "grp": 1},
    {"key": "verdict", "label": "Дүгнэлт", "grp": 1},
    {"key": "metrics", "label": "Үзүүлэлт", "grp": 2},
    {"key": "h2h", "label": "Хоорондын тоглолт", "grp": 2},
    {"key": "maps", "label": "Газрын зураг", "grp": 2},
    {"key": "players", "label": "Тоглогчид", "grp": 2},
    {"key": "duels", "label": "Дуэль", "grp": 2},
    {"key": "roles", "label": "Үүрэг", "grp": 2},
    {"key": "edge", "label": "Тулгуур ба тоо", "grp": 2},
    {"key": "heatmaps", "label": "Heatmap", "grp": 2},
    {"key": "movement", "label": "Movement", "grp": 2},
    {"key": "todo", "label": "Юу хийх", "grp": 3},
]
TAB_KEYS = {t["key"] for t in TABS}

# (side, label) in the order the panels list a player's two halves.
SIDE_PAIRS = (("t", "T"), ("ct", "CT"))


def tabs(heatmaps: dict, movement: dict) -> list[dict]:
    counts = {
        "heatmaps": heatmaps.get("combinations") or 0,
        "movement": movement.get("combinations") or 0,
    }
    return [{**t, "n": counts.get(t["key"], 0)} for t in TABS]


def parsed_maps_by_team() -> dict[int, set[int]]:
    """``{team_id: {map_id, ...}}`` -- a side on a parsed round, the rule the plan uses."""
    by_team: dict[int, set[int]] = {}
    for column in (Round.ct_team_id, Round.t_team_id):
        for team_id, map_id in db().execute(
            select(column, Round.match_map_id)
            .join(MatchMap, MatchMap.id == Round.match_map_id)
            .where(MatchMap.parsed_at.is_not(None), column.is_not(None))
            .distinct()
        ):
            by_team.setdefault(team_id, set()).add(map_id)
    return by_team


def pick() -> dict:
    """The picker: every team a plan can be built for, with its sample size."""
    counts = parsed_maps_by_team()
    teams = db().scalars(select(Team).where(Team.id.in_(list(counts))).order_by(Team.name))
    return {
        "teams": [{"id": t.id, "name": t.name, "maps": len(counts[t.id])} for t in teams],
        "parsed_maps": db().scalar(
            select(func.count()).select_from(MatchMap).where(MatchMap.parsed_at.is_not(None))
        )
        or 0,
    }


def stamp() -> str:
    """Changes whenever any map is parsed or reparsed, or a Review is rebuilt --
    what the cache keys on.

    Global rather than per fixture, because the metric pool and the role
    baseline are measured against every parsed team.
    """
    count, latest = (
        db()
        .execute(
            select(func.count(MatchMap.id), func.max(MatchMap.parsed_at)).where(
                MatchMap.parsed_at.is_not(None)
            )
        )
        .one()
    )
    # The Playbook's Levers and Cautions read the Reviews, which the worker
    # rebuilds after a parse (docs/adr/0008).
    reviews = review_pool.stamp()
    return f"{count}-{int(latest.timestamp()) if latest else 0}-{reviews}"


# --------------------------------------------------------------- helpers ---
def _record(entry: dict | None, *, thin: bool = True) -> dict | None:
    if not entry:
        return None
    out = {"won": entry["won"], "lost": entry["lost"], "win_pct": entry["win_pct"]}
    if thin:
        out["thin"] = bool(entry.get("thin"))
    return out


def _places(rows) -> list[dict]:
    return [{"place": mn.place(r["place"]), "count": r["count"]} for r in rows or ()]


def _setup_rows(setup: dict) -> list[dict]:
    return [
        {
            "name": r["name"],
            "role": mn.role(r["role_key"] or "") if r.get("role_key") else "",
            "post": mn.place(r["post"] or "") if r.get("post") else "",
            "post_kills": r["post_kills"],
            "total_kills": r["total_kills"],
            "concentration": r["concentration"],
        }
        for r in (setup or {}).get("players") or ()
    ]


def _metric_rows(rows) -> list[dict]:
    return [
        {
            "label": mn.metric(m["key"]),
            "why": mn.METRIC_WHY.get(m["key"], ""),
            "value": m["value"],
            "unit": m["unit"],
            "pool_mean": round(float(m["pool_mean"]), 1),
            "z": m["z"],
        }
        for m in rows
    ]


def _profile(prof: dict) -> dict:
    ranked = prof.get("ranked") or []
    return {
        "empty_note": bool(prof.get("empty_note")),
        "maps": prof["maps"],
        "rounds": (prof.get("metrics") or {}).get("rounds", 0),
        "pool_n": ranked[0]["pool_n"] if ranked else 0,
        "strengths": _metric_rows(prof["strengths"]),
        "weaknesses": _metric_rows(prof["weaknesses"]),
        "best_relative": _metric_rows(prof["best_relative"]),
        "worst_relative": _metric_rows(prof["worst_relative"]),
    }


def _scopes(my_team: Team, opponent: Team):
    """The two team blocks: (scope colour, report key, continuity key, team)."""
    return (("mine", "mine", "mine", my_team), ("theirs", "opponent", "theirs", opponent))


# ---------------------------------------------------------------- charts ---
def _chart_map_pool(report, my_team, opponent) -> str:
    rows = []
    for row in report["board"]["board"]:
        if row["mine_pct"] is None and row["theirs_pct"] is None:
            continue
        rows.append(
            {
                "label": row["map"].replace("de_", ""),
                "mine": row["mine_pct"],
                "theirs": row["theirs_pct"],
                "mine_note": (
                    f"{row['mine']['won']}-{row['mine']['lost']}" if row["mine"] else "not parsed"
                ),
                "theirs_note": (
                    f"{row['theirs']['won']}-{row['theirs']['lost']}"
                    if row["theirs"]
                    else "not parsed"
                ),
            }
        )
    return charts.team_compare_bars(
        rows,
        mine_label=my_team.name,
        theirs_label=opponent.name,
        title="Map win rate — every parsed map",
    )


def _chart_metrics(report, my_team, opponent) -> str:
    rows = []
    for key, meta in report["metrics_meta"].items():
        a = report["my_team"]["metrics"].get(key)
        b = report["opponent"]["metrics"].get(key)
        if a is None or b is None:
            continue
        rows.append(
            {
                "label": meta["label"],
                "mine": a,
                "theirs": b,
                "mine_note": meta["why"],
                "theirs_note": meta["why"],
            }
        )
    return charts.team_compare_bars(
        rows,
        mine_label=my_team.name,
        theirs_label=opponent.name,
        value_suffix="",
        title="Core metrics, own matches only",
    )


def _chart_h2h_delta(report, my_team, opponent) -> str:
    rows = [
        {
            "label": r["label"],
            "value": r["delta"],
            "display": f"{r['delta']:+g}",
            "colour": "var(--mark-h2h)" if r["worse"] else "var(--mark-mine)",
            "note": f"{r['own']} in our own matches, {r['versus']} against them",
        }
        for r in report["my_delta"].get("rows", [])
    ]
    return charts.diverging_bars(
        rows,
        title=f"{my_team.name}: own form minus form against {opponent.name}",
        pos_label="better against them",
        neg_label="worse against them",
    )


def _chart_roles(report) -> str:
    rows = [
        {
            "label": f"{r['side'].upper()} {r['role_label']}",
            "value": r["delta"] or 0,
            "display": f"{r['delta']:+.2f}" if r["delta"] is not None else "n/a",
            "note": f"{r['mine']} {r['mine_fit']} vs {r['theirs']} {r['theirs_fit']}",
        }
        for r in report["roles"]["comparison"]
        if r["delta"] is not None
    ]
    return charts.diverging_bars(
        rows,
        title="Role-for-role fit gap",
        domain=1.0,
        pos_label="our man ahead",
        neg_label="their man ahead",
    )


# ---------------------------------------------------------------- panels ---
def panel(tab: str, report: Mapping, my_team: Team, opponent: Team, *,
          heatmaps: dict | None = None, movement: dict | None = None) -> dict:  # fmt: skip
    """What one panel needs, and nothing else."""
    if tab == "decision":
        # It does *not* need the verdict: that reads `roles`, which is most of a
        # page's cost and this panel never shows it.
        return {
            "decision": decision.build(report, my_team, opponent),
            "h2h_maps": report["sample"]["h2h_maps"],
        }

    if tab in ("verdict", "todo"):
        raw = gameplan.verdict(report, my_team, opponent)
        if tab == "todo":
            # The Maps' Playbooks are fetched one at a time (playbook_view.panel).
            maps = playbook_view.maps(report)
            return {"actions": _todo_actions(raw["actions"], maps, my_team, opponent), "maps": maps}
        facts = raw["facts"]
        return {
            "headline": mn.headline(raw, my_team.name, opponent.name),
            "points": mn.points(raw["points"]),
            "record": {"won": facts["record"]["won"], "lost": facts["record"]["lost"]},
            "worst_side": mn.side(facts["worst_side"], short=True) if facts["worst_side"] else None,
            "sample": {
                "my_maps": report["sample"]["my_maps"],
                "opponent_maps": report["sample"]["opponent_maps"],
                "pool_teams": report["sample"]["pool_teams"],
            },
        }

    if tab == "metrics":
        return {
            "chart": _chart_metrics(report, my_team, opponent),
            "mine": _profile(report["my_team"]),
            "theirs": _profile(report["opponent"]),
        }

    if tab == "h2h":
        return _h2h(report, my_team, opponent)

    if tab == "maps":
        return _maps(report, my_team, opponent)

    if tab == "players":
        return _players(report, my_team, opponent)

    if tab == "duels":
        duels = report["duels"]
        return {
            "chart": charts.matchup_grid(
                duels["rows"],
                duels["cols"],
                duels["cells"],
                title="Head-to-head duels — our players down, theirs across",
            ),
            "has_rows": bool(duels["rows"]),
            "totals": duels.get("totals") or [],
            "dropped": duels.get("dropped") or {"mine": [], "theirs": []},
        }

    if tab == "roles":
        return _roles(report, my_team, opponent)

    if tab == "edge":
        teams = []
        for scope, key, _, team in _scopes(my_team, opponent):
            ma = (report["man_advantage"] or {}).get(key) or {}
            teams.append(
                {
                    "scope": scope,
                    "team": team.name,
                    "man_advantage": ma if ma.get("rounds") else None,
                    "linchpins": (report["linchpins"] or {}).get(key) or [],
                }
            )
        return {"teams": teams}

    if tab == "heatmaps":
        return {"index": heatmaps or {}, "words": mn.HEATMAP_WORDS}

    if tab == "movement":
        return {"index": movement or {}, "words": mn.MOVEMENT_WORDS}

    raise KeyError(tab)


# The veto calls whose Maps will likely be played: their first Lever and Caution
# join the action list, after the veto's own lines.
PLAYED_CALLS = ("pick", "contest")
VETO_ACTIONS = ("ban", "pick", "no_pick")


def _todo_actions(raw: list[dict], maps: list[dict], my_team, opponent) -> list[dict]:
    """The verdict's actions, with each likely Map's first Lever and Caution
    after the veto lines."""
    lifted, said = [], set()
    for m in maps:
        if m["call"] not in PLAYED_CALLS:
            continue
        # A line read across all Maps would repeat on every Map: say it once.
        lever, caution = levers.top(levers.build(my_team, opponent, m["map"]), said)
        for entry in (lever, caution):
            if entry is not None:
                said.add(levers.identity(entry))
                lifted.append(mn.advice_action(entry, m["label"], opponent.name))
    worded = mn.actions(raw)
    at = max((i + 1 for i, a in enumerate(raw) if a["kind"] in VETO_ACTIONS), default=0)
    if raw and raw[0]["kind"] == "stale_record":
        at = max(at, 1)
    return worded[:at] + lifted + worded[at:]


def _h2h(report, my_team, opponent) -> dict:
    h2h = report["head_to_head"]
    delta = report["my_delta"]
    cont = report["continuity"] or {}
    out = {
        "totals": h2h.get("totals") or {},
        "continuity_note": mn.continuity_note(cont),
        "delta_rows": [
            {
                "label": mn.metric(r["key"]),
                "why": mn.METRIC_WHY.get(r["key"], ""),
                "own": r["own"],
                "versus": r["versus"],
                "delta": r["delta"],
                "unit": r["unit"],
                "worse": r["worse"],
            }
            for r in delta.get("rows", [])
        ],
        "own_rounds": delta.get("own_rounds", 0),
        "versus_rounds": delta.get("versus_rounds", 0),
        "chart": _chart_h2h_delta(report, my_team, opponent) if delta.get("rows") else "",
        "by_map": [{**e, "map_label": mn.game_map(e["map"])} for e in h2h.get("by_map") or []],
        "matches": [
            {
                "match_id": m.get("match_id"),
                "played_at": (m["played_at"] or "")[:10],
                "my_maps_won": m["my_maps_won"],
                "their_maps_won": m["their_maps_won"],
                "maps": [
                    {
                        "map_label": mn.game_map(s["map"]),
                        "map_number": s.get("map_number"),
                        "my_score": s["my_score"],
                        "their_score": s["their_score"],
                        "won": s["won"],
                    }
                    for s in m["maps"]
                ],
            }
            for m in h2h.get("matches") or []
        ],
        "continuity": None,
    }
    if cont.get("available"):
        sides = []
        for scope, _, h2h_key, _ in _scopes(my_team, opponent):
            s = cont["sides"][h2h_key]
            sides.append(
                {
                    "scope": scope,
                    "team": s["team"],
                    "n": s["n"],
                    "of": s["of"],
                    "current": s["current"],
                    "unseen": s["unseen"],
                }
            )
        out["continuity"] = {"stale": bool(cont.get("stale")), "sides": sides}
    return out


def _maps(report, my_team, opponent) -> dict:
    board = [
        {
            "map": b["map"],
            "map_label": mn.game_map(b["map"]),
            "mine": _record(b["mine"]),
            "theirs": _record(b["theirs"]),
            "h2h": _record(b["h2h"], thin=False),
            "call": b["verdict"]["call"],
            "call_label": mn.VETO_CALL.get(b["verdict"]["call"], b["verdict"]["call"]),
            "confidence": mn.MAP_CONFIDENCE.get(
                b["verdict"]["confidence"], b["verdict"]["confidence"]
            ),
        }
        for b in report["board"]["board"]
    ]
    # Our CT plan is read off *their* T half, and their hot places on that map
    # are the T ones -- joined here because "the other side" is computed.
    setups = {e["map"]: e["sides"] for e in report["map_matrix"]}
    cards = []
    for plan in report["map_plans"]:
        sides = setups.get(plan["map"]) or {}
        hot = plan.get("hot_places") or {}
        verdict = plan.get("verdict") or {}
        theirs = plan.get("theirs")
        cards.append(
            {
                "map": plan["map"],
                "map_label": mn.game_map(plan["map"]),
                "call": verdict.get("call", "unknown"),
                "call_label": mn.VETO_CALL.get(verdict.get("call", ""), ""),
                "confidence": mn.MAP_CONFIDENCE.get(verdict.get("confidence", ""), ""),
                "ours": _record(plan.get("ours"), thin=False),
                "theirs": (
                    {
                        **_record(theirs, thin=False),
                        "median_plant_sec": theirs["plants"].get("median_plant_sec"),
                    }
                    if theirs
                    else None
                ),
                "sides": [
                    {
                        "key": key,
                        "label": mn.side(key, short=True),
                        "their_label": mn.side(other, short=True),
                        "plan": mn.plan_lines(plan.get(key) or []),
                        "mine": _setup_rows((sides.get(key) or {}).get("mine")),
                        "theirs": _setup_rows((sides.get(key) or {}).get("theirs")),
                        "their_kills_from": _places((hot.get(other) or {}).get("kills_from")),
                        "their_dies_at": _places((hot.get(other) or {}).get("dies_at")),
                    }
                    for key, other in (("ct", "t"), ("t", "ct"))
                ],
                "cautions": mn.caution_lines(plan.get("cautions") or []),
            }
        )
    health = report["bombsite_health"]
    return {
        "chart": _chart_map_pool(report, my_team, opponent),
        "board": board,
        "bombsite": {
            "healthy": health["healthy"],
            "mismatched": health["mismatched"],
            "checked": health["checked"],
        },
        "cards": cards,
    }


def _form(f: dict | None) -> dict | None:
    if not f:
        return None
    keys = ("rounds", "adr", "kd", "kast_pct", "opening_win_pct", "opening_kills",
            "opening_deaths", "hs_pct")  # fmt: skip
    return {k: f.get(k) for k in keys}


def _players(report, my_team, opponent) -> dict:
    """Both teams' current five as one list; who was left out comes back by name.

    Restricted to the players each side is fielding (the duel matrix's rule): a
    man who no longer plays is history rather than preparation.
    """
    cards, hidden = [], []
    for scope, key, _, team in _scopes(my_team, opponent):
        for player in report["players"][key]:
            if not player["in_lineup"]:
                hidden.append(player["name"])
                continue
            roles = []
            for side, label in SIDE_PAIRS:
                r = player["role"].get(side) or {}
                if r.get("role"):
                    roles.append(
                        {
                            "side": side,
                            "label": label,
                            "role": mn.role(r["role"]),
                            "fit": mn.FIT.get(r["fit_verdict"], r["fit_verdict"])
                            if r.get("fit_verdict")
                            else "",
                        }
                    )
            cards.append(
                {
                    "scope": scope,
                    "team": team.name,
                    "id": player["player_id"],
                    "name": player["name"],
                    # A new signing's numbers are from the Team they last played for.
                    "elsewhere": player.get("elsewhere", ""),
                    "roles": roles,
                    "own": _form(player["form"]["own"]),
                    "vs": _form(player["form"]["vs"]),
                    "instructions": mn.instructions(player.get("instructions") or []),
                }
            )
    return {"cards": cards, "hidden": hidden}


def _roles(report, my_team, opponent) -> dict:
    section = report["roles"]
    comparison = [
        {
            "side": r["side"],
            "side_label": mn.side(r["side"], short=True),
            "role": mn.role(r["role"]),
            "mine": r["mine"],
            "mine_fit": r["mine_fit"],
            "theirs": r["theirs"],
            "theirs_fit": r["theirs_fit"],
            "delta": r["delta"],
        }
        for r in section["comparison"]
    ]
    teams = []
    for scope, key, _, team in _scopes(my_team, opponent):
        sec = section[key]
        missing = []
        for side, label in SIDE_PAIRS:
            gone = (sec["coverage"].get(side) or {}).get("missing") or []
            if gone:
                missing.append({"side": side, "label": label, "roles": [mn.role(r) for r in gone]})
        players = []
        for p in sec["players"]:
            if not p.get("in_current_lineup", True):
                continue
            sides = []
            for side, label in SIDE_PAIRS:
                v = p["roles"].get(side) or {}
                if not v.get("role"):
                    continue
                fit = (p.get("fit") or {}).get(side) or {}
                sides.append(
                    {
                        "side": side,
                        "label": label,
                        "role": mn.role(v["role"]),
                        "confidence": mn.CONFIDENCE.get(v["confidence"], v["confidence"]),
                        "fit": mn.FIT.get(fit.get("verdict"), fit.get("verdict") or ""),
                        "fit_score": fit.get("score"),
                        "cohort_size": fit.get("cohort_size"),
                        "blurb": mn.ROLE_BLURB.get(v["role"], ""),
                        "evidence": [
                            {"signal": e["signal"], "value": e["value"], "z": e["z"]}
                            for e in v.get("evidence") or []
                        ],
                    }
                )
            players.append(
                {
                    "name": p["name"],
                    "elsewhere": p.get("elsewhere", ""),
                    "rating": p["rating"],
                    "rounds": p["overall"]["rounds"],
                    "adr": p["overall"]["adr"],
                    "kd_ratio": p["overall"]["kd_ratio"],
                    "sides": sides,
                }
            )
        teams.append(
            {
                "scope": scope,
                "team": team.name,
                "maps": sec["maps"],
                "missing": missing,
                "players": players,
            }
        )
    return {
        "chart": _chart_roles(report) if comparison else "",
        "comparison": comparison,
        "teams": teams,
    }
