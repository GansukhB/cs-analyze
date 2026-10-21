"""Between Maps (docs/plans/06 GP-4): what the opponent did differently on a Map
they just played, against their usual, for the few minutes before the next one.

Read off the played Match Map's Review against every other Review of theirs
(review_pool's tallies, all Maps): per Side, the opening duels and trades won,
the Rounds won after the plant and in retakes, how often they forced; the
Findings they made more than usual; and each Player's Swing per Round. A line
is said when the chance it is more than luck (``stats.chance_higher``, or a
normal reading for Swing) passes :data:`SURE`. What carries to the next Map is
how they play today, not where they went on this one, so sites are left out.
Like the other Game Plan services this takes no session: bind one with
``dbctx.using``.
"""

from __future__ import annotations

import statistics
from statistics import NormalDist

from sqlalchemy import select

from app.models import Match, MatchMap, Team
from app.services import mn, review, review_pool, review_summary, stats
from app.services.dbctx import db

SURE = 0.9
RECENT = 6
LINES = 6
MIN_EVENTS = 5  # on the played Side, for a rate
MIN_USUAL = 20  # on their other Maps, for a rate
MIN_CODE = 3  # Findings of one code on the played Map
MIN_PLAYER_ROUNDS = 12
MIN_PLAYER_USUAL = 40
# The Summary's rates, by the Side they are read on.
RATES = {"opening": ("ct", "t"), "trade": ("ct", "t"), "post_plant": ("t",), "retake": ("ct",)}


def _maps(team_id: int, data: review_pool.Data) -> list[dict]:
    """The Team's reviewed Match Maps, newest first."""
    ids = {t.mm for t in data.by_team.get(team_id, [])}
    if not ids:
        return []
    rows = db().execute(
        select(MatchMap.id, MatchMap.match_id, MatchMap.map_number, Match.played_at,
               Match.team1_id, Match.team2_id)
        .join(Match, Match.id == MatchMap.match_id)
        .where(MatchMap.id.in_(ids))
    ).all()  # fmt: skip
    others = {t for r in rows for t in (r.team1_id, r.team2_id) if t and t != team_id}
    names = dict(db().execute(select(Team.id, Team.name).where(Team.id.in_(others))).all())
    by_mm = {t.mm: t.map for t in data.by_team[team_id]}
    out = []
    for r in sorted(rows, key=lambda r: (r.played_at is None, r.played_at), reverse=True):
        against = next((t for t in (r.team1_id, r.team2_id) if t and t != team_id), None)
        out.append({
            "mm": r.id, "match": r.match_id, "num": r.map_number, "map": by_mm[r.id],
            "label": mn.MAPS.get(by_mm[r.id], by_mm[r.id]), "against": names.get(against, "?"),
            "played_at": r.played_at.date().isoformat() if r.played_at else None,
        })  # fmt: skip
    return out


def _rate_lines(here: list, usual: list) -> list[dict]:
    out = []
    for key, sides in RATES.items():
        for side in sides:
            h = [e for t in here if t.side == side for e in t.events.get(key, ())]
            u = [e for t in usual if t.side == side for e in t.events.get(key, ())]
            if len(h) < MIN_EVENTS or len(u) < MIN_USUAL:
                continue
            k1, k0 = sum(1 for e in h if e[1]), sum(1 for e in u if e[1])
            out.append(_judge("rate", key, side, k1, len(h), k0, len(u)))
    # How often they forced: force Rounds of all Rounds on the Side, past the pistols.
    for side in ("ct", "t"):
        h = [t for t in here if t.side == side]
        u = [t for t in usual if t.side == side]
        n1 = sum(len(t.rounds) for t in h) - len(h)
        n0 = sum(len(t.rounds) for t in u) - len(u)
        if n1 < MIN_EVENTS or n0 < MIN_USUAL:
            continue
        k1 = sum(len(t.events.get("force", ())) for t in h)
        k0 = sum(len(t.events.get("force", ())) for t in u)
        out.append(_judge("force_share", "force_share", side, k1, n1, k0, n0))
    return [x for x in out if x]


def _judge(kind, key, side, k1, n1, k0, n0) -> dict | None:
    up = stats.chance_higher(k1, n1, k0, n0)
    if max(up, 1 - up) < SURE:
        return None
    return {"kind": kind, "key": key, "side": side, "k": k1, "n": n1,
            "usual": round(k0 / n0, 3), "more": up >= SURE, "chance": round(max(up, 1 - up), 3),
            "weight": abs(k1 / n1 - k0 / n0)}  # fmt: skip


def _code_lines(here: list, usual: list) -> list[dict]:
    """Findings they made more of than usual (fewer of one says little on one Map)."""
    out = []
    for code in review.CODE_KIND:
        for side in ("ct", "t"):
            h = [t for t in here if t.side == side and review_pool.can_show(t, code)]
            u = [t for t in usual if t.side == side and review_pool.can_show(t, code)]
            c1 = sum(len(t.codes.get(code, ())) for t in h)
            r1, r0 = sum(len(t.rounds) for t in h), sum(len(t.rounds) for t in u)
            if c1 < MIN_CODE or r0 < MIN_USUAL or not r1:
                continue
            c0 = sum(len(t.codes.get(code, ())) for t in u)
            up = stats.chance_higher(c1, r1, c0, r0)
            if up >= SURE:
                out.append({"kind": "code", "key": code, "side": side, "k": c1, "n": r1,
                            "usual": round(c0 / r0, 3), "more": True, "chance": round(up, 3),
                            "weight": c1 / r1 - c0 / r0,
                            "good": review.CODE_KIND[code] == "key_play"
                            or code in review_summary.GOOD_UTILITY})  # fmt: skip
    return out


def _players(here: list, usual: list, names: dict[str, str]) -> list[dict]:
    out = []
    sids = {sid for t in here for sid in t.players}
    for sid in sids:
        h = [s for t in here for _n, s in t.players.get(sid, ())]
        u = [s for t in usual for _n, s in t.players.get(sid, ())]
        if len(h) < MIN_PLAYER_ROUNDS or len(u) < MIN_PLAYER_USUAL:
            continue
        m1, m0, sd = statistics.fmean(h), statistics.fmean(u), statistics.pstdev(u)
        if sd <= 0:
            continue
        up = NormalDist().cdf((m1 - m0) / (sd / len(h) ** 0.5))
        out.append({"sid": sid, "name": names.get(sid, "?"), "rounds": len(h),
                    "here": round(m1, 4), "usual": round(m0, 4),
                    "hot": up >= SURE, "cold": up <= 1 - SURE})  # fmt: skip
    out.sort(key=lambda p: -(p["here"] - p["usual"]))
    return out


def changes(team: Team, played: int | None) -> dict:
    """The Team's recent reviewed Match Maps and, for ``played`` (default the
    newest), what differed from their usual."""
    data = review_pool.data()
    recent = _maps(team.id, data)
    shown = next((m for m in recent if m["mm"] == played), recent[0] if recent else None)
    if shown is None:
        return {"recent": [], "played": None, "lines": [], "players": [], "usual_maps": 0}
    mine = data.by_team.get(team.id, [])
    here = [t for t in mine if t.mm == shown["mm"]]
    usual = [t for t in mine if t.mm != shown["mm"]]
    lines = _rate_lines(here, usual) + _code_lines(here, usual)
    lines.sort(key=lambda x: -x["weight"])
    for x in lines[:LINES]:
        x["text"] = mn.between_line(x)
    return {
        "recent": recent[:RECENT],
        "played": shown,
        "lines": [{k: v for k, v in x.items() if k != "weight"} for x in lines[:LINES]],
        "players": [p for p in _players(here, usual, data.names) if p["hot"] or p["cold"]],
        "usual_maps": len({t.mm for t in usual}),
    }
