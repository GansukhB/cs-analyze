"""After the Match: what a Briefing predicted against what happened (docs/plans/06 GP-8).

Each habit line a Briefing froze keeps the habit as the Playbook found it
(``spec``). On each Map the Match played, the opponent's Rounds there are read
the same way the Playbook reads them, and each habit is checked: in how many of
the Rounds it could show it did, against how often it showed before, and how
many of those Rounds we won (the counter at work). Lines the Match can't judge
(a player line, a Map not played, a Briefing made before the specs were kept)
are counted, not guessed. With the Maps played and the Forecast's series
chance, it is the measure of how well the anti-strat read the opponent.
"""

from __future__ import annotations

import statistics
from collections import Counter

from sqlalchemy import select

from app.models import Briefing, Match, MatchMap, Round, Team
from app.services import briefings, mapstrategy, playbook
from app.services.dbctx import db

# A habit "showed" when its rate in the Match reached this share of its rate before.
SHOWED_SHARE = 0.5
# A median plant time holds within this many seconds.
PLANT_TIME_SLACK = 10.0
# Too few Rounds for a habit to be judged.
MIN_CHANCES = 2


def match_for(briefing: Briefing) -> Match | None:
    """The Match the Briefing was for: the one it names, else the first between
    the two Teams after it was made."""
    session = db()
    if briefing.match_id:
        return session.get(Match, briefing.match_id)
    pair = {briefing.my_team_id, briefing.opponent_id}
    return session.scalar(
        select(Match)
        .where(
            Match.team1_id.in_(pair),
            Match.team2_id.in_(pair),
            Match.team1_id != Match.team2_id,
            Match.played_at >= briefing.created_at,
        )
        .order_by(Match.played_at)
        .limit(1)
    )


def _rounds(mm: MatchMap) -> list[playbook._Round]:
    rows = (
        db()
        .execute(select(Round).where(Round.match_map_id == mm.id).order_by(Round.number))
        .scalars()
    )
    return [
        playbook._Round(
            id=r.id,
            match_map_id=mm.id,
            match_id=mm.match_id,
            map_number=mm.map_number,
            number=r.number,
            tickrate=mm.tickrate or 64,
            freeze_end=r.freeze_end_tick,
            end=r.end_tick,
            plant=r.bomb_plant_tick,
            site=r.bomb_site,
            winner=r.winner_team_id,
            ct_team=r.ct_team_id,
            t_team=r.t_team_id,
            ct_buy=r.ct_buy,
            t_buy=r.t_buy,
            h2h=True,
        )  # fmt: skip
        for r in rows
    ]


def _verdict(hits: list, chances: list, before: dict, mine: int) -> dict:
    """How a habit fared over ``chances`` Rounds, ``hits`` of which showed it."""
    rate_before = (before.get("n") or 0) / before["of"] if before.get("of") else None
    rate = len(hits) / len(chances) if chances else None
    judged = len(chances) >= MIN_CHANCES and rate is not None
    showed = (
        judged
        and rate > 0
        and (rate_before is None or rate >= SHOWED_SHARE * rate_before)
    )  # fmt: skip
    return {
        "judged": judged,
        "showed": bool(showed),
        "hits": len(hits),
        "chances": len(chances),
        "rate_before": round(100 * rate_before) if rate_before is not None else None,
        "rate": round(100 * rate) if rate is not None else None,
        "won": sum(1 for r in hits if r.winner == mine),
        "refs": [r.ref for r in hits[:6]],
    }


def check_habit(spec: dict, before: dict, rounds, detail, sites, them: int, mine: int) -> dict:
    """One habit against the opponent's Rounds of one Map."""
    kind, side = spec.get("kind"), spec.get("side") or ""
    theirs = [r for r in rounds if r.side_of(them) == side] if side else list(rounds)
    setups = playbook._setups(them, theirs, side, detail, sites) if side else {}
    full = {rid: s for rid, s in setups.items() if sum(s["count"].values()) >= 4}
    by_id = {r.id: r for r in theirs}

    def verdict(hits, chances):
        return _verdict(hits, chances, before, mine)

    if kind == "site":
        planted = [r for r in theirs if r.plant and r.site in ("A", "B")]
        return verdict([r for r in planted if r.site == spec.get("site")], planted)
    if kind == "rush":
        return verdict(
            [r for r in theirs if r.plant and r.secs(r.plant) <= mapstrategy.RUSH_PLANT_SEC],
            theirs,
        )
    if kind == "plant_time":
        planted = [r for r in theirs if r.plant]
        if len(planted) < MIN_CHANCES:
            return verdict([], planted)
        median = statistics.median(r.secs(r.plant) for r in planted)
        held = abs(median - float(spec.get("median") or 0)) <= PLANT_TIME_SLACK
        out = verdict(planted if held else [], planted)
        out.update(rate=None, rate_before=None, median=round(median, 1))
        return out
    if kind == "setup":
        leans = playbook.LEANS
        pattern = tuple((spec.get("pattern") or {}).get(lean, 0) for lean in leans)
        hits = [
            by_id[rid]
            for rid, s in full.items()
            if tuple(s["count"].get(lean, 0) for lean in leans) == pattern
        ]
        return verdict(hits, [by_id[rid] for rid in full])
    if kind == "stack":
        site = spec.get("site")
        hits = [by_id[rid] for rid, s in full.items()
                if s["count"].get(site, 0) >= playbook.STACK_FROM]  # fmt: skip
        return verdict(hits, [by_id[rid] for rid in full])
    if kind == "soft_site":
        site = spec.get("site")
        other = "B" if site == "A" else "A"
        held = [by_id[rid] for rid, s in full.items()
                if s["count"].get(site, 0) < s["count"].get(other, 0)]  # fmt: skip
        return verdict(held, [by_id[rid] for rid in full])
    if kind == "spot":
        player = spec.get("player_id")
        stood = [(by_id[rid], place) for rid, s in setups.items()
                 for p, place, _lean in s["spots"] if p == player]  # fmt: skip
        return verdict([r for r, place in stood if place == spec.get("place")],
                       [r for r, _p in stood])  # fmt: skip
    if kind == "opening":
        place = spec.get("place")
        hits = []
        for r in theirs:
            k = detail.first_kill.get(r.id)
            if k is None:
                continue
            at = k.attacker_place if k.attacker_side == side else k.victim_place
            if at == place:
                hits.append(r)
        return verdict(hits, theirs)
    if kind == "retake":
        faced = [r for r in theirs if r.plant]
        won = [r for r in faced if r.winner == them]
        weak = spec.get("weak")
        if weak is None:  # judged by the fixed bars: weak at or under half
            weak = (spec.get("pct") or 0) <= 50
        out = verdict([r for r in faced if r not in won] if weak else won, faced)
        out["pct"] = round(100 * len(won) / len(faced)) if faced else None
        return out
    if kind == "after_pistol_loss":
        after = []
        for r in rounds:
            prev = next((x for x in rounds if x.number == r.number - 1), None)
            if (
                prev
                and prev.number in playbook.PISTOL_ROUNDS
                and prev.winner != them
                and prev.winner
            ):
                after.append(r)
        return verdict([r for r in after if r.buy(them) == spec.get("buy")], after)
    return {"judged": False, "showed": False, "hits": 0, "chances": 0, "rate_before": None,
            "rate": None, "won": 0, "refs": [], "unchecked": kind}  # fmt: skip


def check(briefing: Briefing, match: Match | None = None) -> dict:
    session = db()
    match = match or match_for(briefing)
    content = briefings.unpack(briefing.payload)
    mine, them = briefing.my_team_id, briefing.opponent_id
    out = {"match_id": match.id if match else None, "maps": [], "totals": {},
           "veto": None, "forecast": None}  # fmt: skip
    if match is None:
        return out
    played = {
        mm.game_map.name: mm
        for mm in session.scalars(select(MatchMap).where(MatchMap.match_id == match.id))
        if mm.game_map is not None and mm.is_parsed
    }
    totals = Counter()
    for m in content.get("maps") or []:
        mm = played.get(m["map"])
        lines = []
        rounds = _rounds(mm) if mm else []
        detail = playbook._detail(rounds) if rounds else None
        sites = playbook.site_centroids(m["map"]) if rounds else {}
        for item in m.get("items") or []:
            if item.get("kind") != "habit":
                continue
            spec = item.get("spec") or {}
            if not spec or not rounds:
                totals["unchecked"] += 1
                lines.append({"title": item["title"], "section": item.get("section") or "",
                              "result": None})  # fmt: skip
                continue
            result = check_habit(spec, item.get("seen") or {}, rounds, detail, sites, them, mine)
            totals["judged"] += int(result["judged"])
            totals["showed"] += int(result["showed"])
            totals["unchecked"] += int(not result["judged"])
            if result["showed"]:
                totals["hit_rounds"] += result["hits"]
                totals["won_rounds"] += result["won"]
            lines.append({"title": item["title"], "section": item.get("section") or "",
                          "result": result})  # fmt: skip
        out["maps"].append({"map": m["map"], "label": m.get("label") or m["map"],
                            "played": mm is not None, "map_number": mm.map_number if mm else None,
                            "lines": lines})  # fmt: skip
    out["totals"] = dict(totals)
    briefed = {m["map"] for m in content.get("maps") or []}
    out["veto"] = {
        "played": sorted(played),
        "briefed": sorted(briefed),
        "hit": len(briefed & set(played)),
    }
    fc = content.get("forecast")
    if fc and fc.get("series") and match.winner_id:
        names = dict(
            session.execute(select(Team.id, Team.name).where(Team.id.in_((mine, them)))).all()
        )
        p = fc["series"][0].get("p")
        won = match.winner_id == mine
        out["forecast"] = {
            "format": fc["series"][0].get("format"),
            "p": p,
            "won": won,
            "brier": round((p - (1.0 if won else 0.0)) ** 2, 3) if p is not None else None,
            "winner": names.get(match.winner_id, ""),
        }
    return out
