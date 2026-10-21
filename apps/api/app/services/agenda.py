"""A Review meeting's agenda for one Team's Match (docs/plans/07 RV-10).

Built from the Match's Summary and its Maps' Reviews, in the order a 45-60
minute session runs: how the score went and who swung it, the Focus points
that decided it (with their Rounds), pistols and conversion, the other side's
strengths, each Player's best and worst play, what went well (always said),
then at most three things to practise and one line per Player for his
Development plan.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from app.models import Match, Round
from app.services import me, mn, playbook, review, review_view

MINUTES = {"flow": 5, "focus": 15, "phases": 8, "theirs": 5, "players": 12, "good": 5, "actions": 5}
FOCUS = 3
PRACTICE = 3


def _refs(refs: list[dict], limit: int = 3) -> list[dict]:
    """The first ``limit`` distinct Rounds a line points at."""
    seen, out = set(), []
    for r in refs:
        key = (r["map_number"], r["round"])
        if key in seen:
            continue
        seen.add(key)
        out.append({"map_number": r["map_number"], "round": r["round"]})
        if len(out) == limit:
            break
    return out


def build(db, match: Match, team_id: int) -> dict:
    panel = review_view.match_panel(db, match)
    names = {t["id"]: t["name"] for t in panel["teams"]}
    ours = next((s for s in panel["summaries"] if s["team_id"] == team_id), None) or {}
    theirs = next((s for s in panel["summaries"] if s["team_id"] != team_id), None) or {}
    other = next((t for t in names if t != team_id), None)

    def outcome(m: dict) -> str:
        if not m["winner_team_id"]:
            return ""
        return " — хожсон" if m["winner_team_id"] == team_id else " — алдсан"

    flow = [{"text": f"{m['label']}: {m['scoreline']}{outcome(m)}"} for m in panel["maps"]]
    for p in (ours.get("players") or [])[:3]:
        flow.append({"text": f"Swing: {p['name']} {p['swing']:+.2f} раунд ({p['rounds']} раунд)"})

    focus = [
        {"text": f["text"], "advice": f.get("advice") or "", "refs": _refs(f.get("refs") or [])}
        for f in (ours.get("focus") or [])[:FOCUS]
    ]
    repeated = [
        p for p in ours.get("problems") or [] if len(p.get("maps") or []) >= 2 and p not in focus
    ]
    for p in repeated[:2]:
        focus.append({"text": "Давтагдсан: " + p["text"], "advice": p.get("advice") or "",
                      "refs": _refs(p.get("refs") or [])})  # fmt: skip

    # Pistols, Map by Map.
    rows = db.execute(
        select(Round.match_map_id, Round.number, Round.winner_team_id, Round.ct_team_id,
               Round.t_team_id)
        .where(Round.match_map_id.in_([m.id for m in match.map_results]))
        .order_by(Round.match_map_id, Round.number)
    ).all()  # fmt: skip
    phases = []
    by_number = {m.id: m for m in match.map_results}
    for mm_id in sorted({r[0] for r in rows}, key=lambda i: by_number[i].map_number):
        c = playbook._conversion_rows([r for r in rows if r[0] == mm_id])[team_id]
        label = mn.game_map(by_number[mm_id].game_map.name if by_number[mm_id].game_map else "")
        phases.append(
            {
                "text": (
                    f"{label}: pistol {c['pistols_won']}/{c['pistols']}, хожсоны дараах 2 раунд "
                    f"{c['converted']}/{c['chances']}, алдсаны дараа break "
                    f"{c['broken']}/{c['breaks']}"
                )
            }
        )

    players = []
    mistakes: dict[str, Counter] = {}
    for mm in sorted(match.map_results, key=lambda m: m.map_number):
        stored = review.ensure(db, mm, stale_ok=True) if mm.is_parsed else None
        if not stored:
            continue
        side_of = {}
        for r in stored.get("rounds") or []:
            for sid, side in (r.get("sides") or {}).items():
                team = r.get(f"{side}_team_id")
                if team is not None:
                    side_of[sid] = team
        who_names = {p["sid"]: p.get("name") or "?" for p in stored.get("players") or []}

        def who(sid, who_names=who_names):
            return who_names.get(sid, "?") if sid else ""

        for f in stored.get("findings") or []:
            for sid in f.get("sids") or []:
                if side_of.get(sid) != team_id:
                    continue
                # A side-wide Finding costs each Player his own death only (me._own_swing).
                swing = me._own_swing(f, sid)
                if swing is None:
                    continue
                players.append(
                    {"sid": sid, "swing": swing, "map_number": mm.map_number,
                     "round": f.get("round"), "f": f, "who": who}
                )  # fmt: skip
                if review.CODE_KIND.get(f["code"]) in ("mistake", "missed_chance"):
                    mistakes.setdefault(sid, Counter())[f["code"]] += 1

    per_player = []
    for p in ours.get("players") or []:
        his = [e for e in players if e["sid"] == p["sid"]]
        best = max(his, key=lambda e: e["swing"], default=None)
        worst = min(his, key=lambda e: e["swing"], default=None)
        lines = []
        for tag, e, keep in (
            ("Шилдэг", best, lambda v: v > 0),
            ("Хамгийн үнэтэй алдаа", worst, lambda v: v < 0),
        ):
            if e and keep(e["swing"]):
                worded = mn.review_finding(e["f"], e["who"])
                lines.append(
                    {
                        "text": f"{tag}: {worded['title']} ({e['swing']:+.2f} раунд)",
                        "refs": [{"map_number": e["map_number"], "round": e["round"]}],
                    }
                )
        per_player.append({"player": p["name"], "swing": p["swing"], "lines": lines})

    good = [
        {"text": s["text"], "refs": _refs(s.get("refs") or [])}
        for s in (ours.get("strengths") or [])[:3]
    ]
    their_good = [{"text": s["text"]} for s in (theirs.get("strengths") or [])[:3]]

    practice = [
        {"text": f["advice"] or f["text"]}
        for f in (ours.get("focus") or [])[:PRACTICE]
        if f.get("advice")
    ]
    plans = []
    names_by_sid = {p["sid"]: p["name"] for p in ours.get("players") or []}
    for sid, codes in mistakes.items():
        code, n = codes.most_common(1)[0]
        if n >= 2:
            plans.append({"text": f"{names_by_sid.get(sid, '?')}: {mn.REVIEW_CODE.get(code, code)} "
                                  f"({n} удаа) — Development plan-д"})  # fmt: skip

    sections = [
        ("flow", "Онооны урсгал ба Swing", flow),
        ("focus", "Шийдвэрлэсэн Focus point-ууд", focus),
        ("phases", "Pistol ба хувиргалт", phases),
        ("theirs", f"{names.get(other, 'Тэд')}-ийн сайн хийсэн нь", their_good),
        ("players", "Тоглогчид", []),
        ("good", "Сайн болсон", good),
        ("actions", "Үйлдэл", [{"text": "Дасгал: " + x["text"]} for x in practice] + plans),
    ]
    return {
        "team": names.get(team_id, "?"),
        "opponent": names.get(other, "") or match.opponent_label,
        "minutes": sum(MINUTES.values()),
        "sections": [
            {"key": key, "title": title, "minutes": MINUTES[key], "items": items}
            for key, title, items in sections
        ],
        "players": per_player,
    }
