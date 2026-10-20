"""The Review as the match page shows it: the stored facts, worded.

:mod:`app.services.review` stores each Finding as facts; this words them with
``mn.review_*`` on every read, so a sentence can change without rebuilding a
single Review. Nothing here touches the Tick Data.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Match, MatchMap
from app.services import mn, review, review_summary

# At the same moment, the play before what it cost.
_KIND_ORDER = {"key_play": 0, "mistake": 1, "missed_chance": 2, "utility": 3}


def panel(db: Session, match_map: MatchMap) -> dict | None:
    """The page's Review of ``match_map``, or None when it has no Tick Data."""
    stored = review.ensure(db, match_map)
    if stored is None:
        return None
    names = {p["sid"]: p["name"] for p in stored["players"]}
    teams = {}
    for team in (match_map.team1, match_map.team2):
        if team is not None:
            teams[team.id] = team.name
    for p in stored["players"]:
        if p.get("team_id") is not None:
            teams.setdefault(p["team_id"], p.get("team") or "")

    def who(sid):
        return names.get(sid, "?") if sid else "?"

    def team(team_id):
        return teams.get(team_id, "")

    findings, words_by_id = [], {}
    for f in stored["findings"]:
        words = mn.review_finding(f, who)
        words_by_id[f["id"]] = words
        findings.append({
            **{k: f[k] for k in ("id", "kind", "code", "round", "t", "side", "team_id", "sids",
                                 "swing", "sight")},
            "kind_label": mn.REVIEW_KIND.get(f["kind"], f["kind"]),
            "code_label": mn.REVIEW_CODE.get(f["code"], f["code"]),
            **words,
        })  # fmt: skip
    # A Round reads as it was played; the match-wide ones (no Round) go last.
    findings.sort(key=lambda f: (f["round"] is None, f["round"] or 0, f["t"] or 0.0,
                                 _KIND_ORDER.get(f["kind"], 9)))  # fmt: skip
    by_round: dict[int, list[str]] = {}
    for f in findings:
        if f["round"] is not None:
            by_round.setdefault(f["round"], []).append(f["id"])
    raw_by_round: dict[int, list[dict]] = {}
    for f in stored["findings"]:
        if f["round"] is not None:
            raw_by_round.setdefault(f["round"], []).append(f)
    number = match_map.map_number

    rounds = [
        {
            **{k: r[k] for k in ("n", "winner_side", "winner_team_id", "ct_team_id", "t_team_id",
                                 "reason", "site", "ct_buy", "t_buy", "seconds", "wp", "events",
                                 "swing", "sides", "decider")},
            "summary": mn.review_round(r, who, team),
            "findings": by_round.get(r["n"], []),
            "teams": review_summary.round_teams(
                r, raw_by_round.get(r["n"], []), words_by_id, who, number
            ),
        }
        for r in stored["rounds"]
    ]  # fmt: skip
    # What this Map's Tick Data could not show (docs/adr/0006; RV-5).
    lacking = [c for c in stored.get("needs_sightings") or []]
    lacking += [c for c in stored.get("needs_loadout") or [] if c not in lacking]
    missing = ""
    if lacking:
        labels = ", ".join(mn.REVIEW_CODE[c] for c in lacking)
        what = " ба ".join(
            w
            for w, gone in (
                ("Sighting", stored.get("needs_sightings")),
                ("Loadout", stored.get("needs_loadout")),
            )
            if gone
        )
        missing = (
            f"Энэ map хуучин schema-аар ({what}-гүй) боловсруулагдсан тул дараах дүгнэлтүүд "
            f"байхгүй: {labels}. Бусад нь бүрэн."
        )
    return {
        "version": stored["version"],
        "sightings": stored["sightings"],
        "missing": missing,
        "teams": [{"id": k, "name": v} for k, v in teams.items()],
        "players": stored["players"],
        "rounds": rounds,
        "findings": findings,
        "kinds": mn.REVIEW_KIND,
        "summary": review_summary.map_summary(stored, list(teams), who, number),
    }


def match_panel(db: Session, match: Match) -> dict:
    """The Match's Summary: one line per Map, and each Team's Patterns across
    the Maps, Focus points and Players. A Map with no Tick Data has its score
    only."""
    teams = {t.id: t.name for t in (match.team1, match.team2) if t is not None}
    maps, rows, names = [], [], {}
    for match_map in sorted(match.map_results, key=lambda m: m.map_number):
        label = mn.game_map(match_map.game_map.name if match_map.game_map else "")
        row = {
            "map_number": match_map.map_number,
            "label": label,
            "scoreline": match_map.scoreline,
            "winner_team_id": match_map.winner_id,
            "reviewed": False,
            "teams": [],
        }
        rows.append(row)
        stored = review.ensure(db, match_map) if match_map.is_parsed else None
        if stored is None:
            continue
        names.update({p["sid"]: p["name"] for p in stored["players"]})

        def who(sid, names=names):
            return names.get(sid, "?") if sid else "?"

        summary = review_summary.map_summary(stored, list(teams), who, match_map.map_number)
        row["reviewed"] = True
        for s in summary["all"]:
            row["teams"].append({
                "team_id": s["team_id"],
                "won": s["won"],
                "rounds": s["rounds"],
                "strength": s["strengths"][0] if s["strengths"] else None,
                "problem": s["problems"][0] if s["problems"] else None,
            })  # fmt: skip
        maps.append({"map_number": match_map.map_number, "summary": summary["all"],
                     "players": stored["players"]})  # fmt: skip
    labels = {r["map_number"]: r["label"] for r in rows}
    return {
        "teams": [{"id": k, "name": v} for k, v in teams.items()],
        "maps": rows,
        "summaries": review_summary.match_summary(maps, list(teams), labels),
        "names": names,
    }
