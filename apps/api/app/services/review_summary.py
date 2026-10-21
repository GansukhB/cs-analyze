"""The Summary (CONTEXT.md): each Team's account of a Round, a Match Map and a Match.

Told only from a Review's stored facts (its Findings, and each Round's buys,
kills, plant and Win probability) and worded with ``mn.summary_*`` on every
read, so a threshold or a sentence can change with nothing rebuilt.

A number says something only past its threshold and with enough Rounds behind
it. The thresholds are the 25th and 75th percentiles of each number over the
113 Match Maps reviewed when this was written (226 Team-maps); the Patterns'
(:data:`PATTERN_P75`) are measured again with :func:`pattern_percentiles`
(``python -m app.cli summary-thresholds``) whenever a detector changes, and say
when in :data:`PATTERN_P75_FROM`. Everything a Summary lists is weighed in
Rounds, so one list can rank a Pattern of Findings (the Swing they cost or won,
or :data:`ZERO_SWING_VALUE` for the ones that carry none) against a number such
as force buys (how far the Rounds came out from the Win probability they started
with).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from app.services import mn

# (bad at most, good at least, fewest): a rate and how many it needs.
OPENING = (0.40, 0.60, 6)
TRADE = (0.18, 0.26, 8)
FULL_V_FULL = (0.37, 0.64, 6)
POST_PLANT = (0.65, 0.96, 4)
FORCE_BAD = (0.17, 3)
FORCE_GOOD = (0.50, 2)
RETAKE_GOOD = (0.33, 4)
LIGHT_BAD = (0.50, 3)  # a full buy against an eco or force; one loss to an eco is enough
STREAK = 6
COMEBACK_WP = 0.20  # won from this low
SWUNG_WP = 0.80  # lost from this high
COMEBACK_MIN = 2
PATTERN_MIN = 3
# Findings per 24 Rounds at the 75th percentile: a Pattern repeats at least this
# often. A code missing here was too rare to measure: three of it are a Pattern.
PATTERN_P75_FROM = "113 Reviews at REVIEW_SCHEMA 5, Win probability v2, 2026-10"
PATTERN_P75 = {
    "advantage_lost": 2.8, "awp_miss": 1.0, "big_frag": 2.8, "blind_unpunished": 4.2,
    "bomb_lost": 1.0, "clutch": 2.3, "crosshair": 1.4, "died_in_advantage": 1.3, "entry": 5.1,
    "fire_delay": 1.3, "flash_kill": 7.1, "lost_weapon_save": 11.3, "moving_shots": 2.1,
    "multikill": 4.2, "nade_damage_kill": 6.6, "no_gun_in_hand": 1.1, "plant": 4.2,
    "retake": 1.4, "saw_first_lost": 4.8, "saw_no_shot": 1.4, "team_flash": 9.4,
    "team_flashed_death": 2.8, "time_out": 1.0, "unfinished": 6.2, "unused_utility": 2.5,
}  # fmt: skip
GOOD_UTILITY = {"flash_kill", "nade_damage_kill", "fire_delay"}
# The Rounds one event is worth when its Findings carry no Swing (or too little
# to rank it): a Round run out of time or a lost defuse is about half a Round; a
# rifle thrown away costs the next buy, more when the Team then can't full-buy;
# a wasted or team flash, a little.
ZERO_SWING_VALUE = {
    "time_out": 0.5, "kitless": 0.5, "defuse_chance": 0.5, "fire_delay": 0.2,
    "lost_weapon_save": 0.15, "team_flash": 0.05, "blind_unpunished": 0.05,
    "late_execute": 0.3, "early_rotate": 0.3,
}  # fmt: skip
LOST_SAVE_BY_NEXT_BUY = {"full": 0.05, "force": 0.25, "eco": 0.25}


def value(f: dict) -> float:
    """What one Finding is worth in Rounds: its Swing, or what a Finding of its
    code is worth when it carries none."""
    floor = ZERO_SWING_VALUE.get(f["code"], 0.0)
    if f["code"] == "lost_weapon_save":
        floor = LOST_SAVE_BY_NEXT_BUY.get((f.get("facts") or {}).get("next_buy") or "", floor)
    return max(abs(f["swing"]), floor)


# Dying untraded and not trading are one number (the trade rate), not Patterns.
TRADE_CODES = {"untraded", "no_trade"}
FOCUS_POINTS = 3
FOCUS_MIN_COST = 0.25  # Rounds
ROUND_BULLETS = 3
ROUND_FOCUS_SWING = -0.15
SIDES = {"all": ("ct", "t"), "ct": ("ct",), "t": ("t",)}


def is_good(finding: dict) -> bool:
    """A Finding for its Team: a Key play or a Utility effect that helped."""
    return finding["kind"] == "key_play" or finding["code"] in GOOD_UTILITY


def advice(key: str) -> str:
    return mn.SUMMARY_ADVICE.get("trade" if key in TRADE_CODES else key, "")


# ------------------------------------------------------------- one Round ---
class _Round:
    """One stored Round from one Team's side."""

    def __init__(self, r: dict, side: str) -> None:
        self.r = r
        self.n = r["n"]
        self.side = side
        self.won = r["winner_side"] == side
        self.buy = r.get(f"{side}_buy") or ""
        self.their_buy = r.get("t_buy" if side == "ct" else "ct_buy") or ""
        wp = r.get("wp") or []
        self.wp = [(p[0], p[1] if side == "ct" else 1.0 - p[1]) for p in wp]
        self.start = self.wp[0][1] if self.wp else 0.5
        self.plant = next((e for e in r.get("events") or [] if e["kind"] == "plant"), None)

    def mine(self, sid: str | None) -> bool:
        return bool(sid) and self.r["sides"].get(sid) == self.side

    def delta(self, kill: dict) -> float:
        """This Team's Win probability change on a stored kill."""
        for e in self.r.get("events") or []:
            if (
                e["kind"] == "kill"
                and e.get("victim") == kill["v"]
                and abs(e["t"] - kill["t"]) < 0.01
            ):
                return e["d_ct"] if self.side == "ct" else -e["d_ct"]
        return 0.0

    def wp_after_plant(self) -> float:
        if self.plant is None:
            return self.start
        before = self.start
        for t, p in self.wp:
            if t > self.plant["t"]:
                break
            before = p
        d = self.plant["d_ct"] if self.side == "ct" else -self.plant["d_ct"]
        return min(1.0, max(0.0, before + d))

    def opening(self) -> dict | None:
        return next((k for k in self.r.get("kills") or [] if k.get("opening")), None)


def _ref(map_number: int | None, n: int, t: float | None = 0.0, sid: str | None = None) -> dict:
    return {"map_number": map_number, "round": n, "t": t or 0.0, "sid": sid}


def _bullet(f: dict, n: int, words: dict, map_number) -> dict:
    """A Finding as one line of a Round's Summary."""
    return {
        "text": words.get(f["id"], {}).get("title") or mn.REVIEW_CODE.get(f["code"], ""),
        "label": mn.REVIEW_CODE.get(f["code"], f["code"]),
        "swing": f["swing"],
        "finding": f["id"],
        **_ref(map_number, n, f.get("t"), (f.get("sids") or [None])[0]),
    }


def round_teams(r: dict, findings: list[dict], words: dict, who, map_number=None) -> list[dict]:
    """Each Team's Summary of one Round: one line, what went well, what went
    wrong, and a Focus point when the Team lost it to a costly Mistake."""
    out = []
    for side in ("ct", "t"):
        rr = _Round(r, side)
        mine = [f for f in findings if f["side"] == side]
        good = sorted((f for f in mine if is_good(f)), key=lambda f: -f["swing"])
        bad = sorted((f for f in mine if not is_good(f)), key=lambda f: f["swing"])
        lows = [p for _t, p in rr.wp]
        line = {"side": side, "won": rr.won, "buy": rr.buy, "reason": r.get("reason"),
                "site": r.get("site")}  # fmt: skip
        if rr.won and lows and min(lows) <= COMEBACK_WP:
            line["low"] = min(lows)
        if not rr.won and lows and max(lows) >= SWUNG_WP:
            line["high"] = max(lows)

        goods = [_bullet(f, rr.n, words, map_number) for f in good[:ROUND_BULLETS]]
        bads = [_bullet(f, rr.n, words, map_number) for f in bad[:ROUND_BULLETS]]
        k = rr.opening()
        if k is not None:
            got = rr.mine(k["a"])
            fact = {
                "text": mn.summary_opening({"got": got, "killer": k["a"], "victim": k["v"]}, who),
                "label": "Opening",
                "swing": round(rr.delta(k), 4),
                "finding": None,
                **_ref(map_number, rr.n, k["t"], k["a"] if got else k["v"]),
            }
            # The opening is already there when an entry or its death is listed.
            listed = {(b["round"], round(b["t"], 1)) for b in goods + bads}
            target = goods if got else bads
            if (rr.n, round(k["t"], 1)) not in listed and len(target) < ROUND_BULLETS:
                target.append(fact)
        focus = None
        if not rr.won and bad and bad[0]["swing"] <= ROUND_FOCUS_SWING and advice(bad[0]["code"]):
            worst = _bullet(bad[0], rr.n, words, map_number)
            focus = {**worst, "advice": advice(bad[0]["code"])}
        out.append(
            {
                "side": side,
                "team_id": r.get(f"{side}_team_id"),
                "won": rr.won,
                "line": mn.summary_round_line(line),
                "good": goods,
                "bad": bads,
                "focus": focus,
            }
        )
    return out


# ---------------------------------------------------------- one Match Map ---
def _fewest(count: int, sides: tuple) -> int:
    """With one Side picked, a number needs half the Rounds."""
    return count if len(sides) == 2 else max(2, math.ceil(count / 2))


def _counts(pairs, key: str = "sid") -> list[dict]:
    return [{key: k, "n": n} for k, n in pairs]


def _item(key: str, kind: str, good: bool, weight: float, text: str, refs: list, **extra) -> dict:
    label = mn.SUMMARY_LABEL.get(key) or mn.REVIEW_CODE.get(key, key)
    item = {
        "key": key,
        "kind": kind,
        "good": good,
        "label": label,
        "text": text,
        "weight": round(max(0.0, weight), 3),
        "refs": refs,
        "count": extra.pop("count", len(refs)),
        "advice": "" if good else advice(key),
    }
    item.update(extra)
    return item


def _over(rounds: list[_Round], won: bool) -> float:
    """Rounds above (won) or below (lost) what their start promised."""
    return sum((1.0 - r.start) if won else r.start for r in rounds if r.won == won)


def team_summary(
    stored: dict, team_id, scope: str, who, map_number: int | None = None
) -> dict | None:
    """One Team's Summary of a Match Map, over both Sides or one."""
    sides = SIDES[scope]
    rounds = []
    for r in stored["rounds"]:
        for side in sides:
            if r.get(f"{side}_team_id") == team_id:
                rounds.append(_Round(r, side))
    if not rounds:
        return None
    numbers: list[dict] = []
    items: list[dict] = []
    won = sum(1 for r in rounds if r.won)

    def ref(r: _Round, t=0.0, sid=None) -> dict:
        return _ref(map_number, r.n, t, sid)

    def number(key: str, value: str, tone: str = "") -> None:
        numbers.append({"key": key, "label": mn.SUMMARY_LABEL.get(key, key), "value": value,
                        "tone": tone})  # fmt: skip

    numbers.append({"key": "rounds", "label": "Раунд", "value": f"{won}–{len(rounds) - won}",
                    "tone": ""})  # fmt: skip
    if len(sides) == 2:
        for side in ("ct", "t"):
            part = [r for r in rounds if r.side == side]
            if part:
                w = sum(1 for r in part if r.won)
                numbers.append({"key": side, "label": mn.side(side, short=True),
                                "value": f"{w}–{len(part) - w}", "tone": ""})  # fmt: skip

    # Pistol rounds.
    pistols = [r for r in rounds if r.buy == "pistol"]
    if pistols:
        w = sum(1 for r in pistols if r.won)
        tone = "good" if w == len(pistols) else "bad" if w == 0 else ""
        number("pistol", f"{w}/{len(pistols)}", tone)
        if tone:
            items.append(_item("pistol", "metric", tone == "good", _over(pistols, tone == "good"),
                               mn.summary_metric("pistol", tone == "good",
                                                 {"won": w, "n": len(pistols)}, who),
                               [ref(r) for r in pistols]))  # fmt: skip

    # Opening duels.
    openings = [(r, k) for r in rounds if (k := r.opening()) is not None]
    if openings:
        got = [(r, k) for r, k in openings if r.mine(k["a"])]
        n, w = len(openings), len(got)
        bad, good, fewest = OPENING
        tone = ""
        if n >= _fewest(fewest, sides):
            tone = "good" if w / n >= good else "bad" if w / n <= bad else ""
        number("opening", f"{w}/{n}", tone)
        if tone:
            mine = got if tone == "good" else [(r, k) for r, k in openings if not r.mine(k["a"])]
            who_key = "a" if tone == "good" else "v"
            players = Counter(k[who_key] for _r, k in mine).most_common()
            weight = sum(abs(r.delta(k)) for r, k in mine)
            items.append(_item("opening", "metric", tone == "good", weight,
                               mn.summary_metric("opening", tone == "good",
                                                 {"won": w, "n": n, "players": players}, who),
                               [ref(r, k["t"], k[who_key]) for r, k in mine],
                               players=_counts(players)))  # fmt: skip

    # Trades: deaths traded, deaths left untraded, and who could have traded.
    by_n = {r.n: r for r in rounds}
    deaths = [(r, k) for r in rounds for k in r.r.get("kills") or [] if r.mine(k["v"])]
    if deaths:
        traded = sum(1 for _r, k in deaths if k.get("traded"))
        n = len(deaths)
        bad, good, fewest = TRADE
        tone = ""
        if n >= _fewest(fewest, sides):
            tone = "good" if traded / n >= good else "bad" if traded / n <= bad else ""
        number("trade", mn.review_pct(traded / n), tone)
        if tone == "bad":
            untraded = [f for f in stored["findings"] if f["code"] == "untraded"
                        and f["round"] in by_n and f["side"] == by_n[f["round"]].side]  # fmt: skip
            missed = [f for f in stored["findings"] if f["code"] == "no_trade"
                      and f["round"] in by_n and f["side"] == by_n[f["round"]].side]  # fmt: skip
            players = Counter(f["sids"][0] for f in untraded).most_common()
            missers = Counter(f["sids"][0] for f in missed).most_common()
            items.append(_item("trade", "metric", False, sum(-f["swing"] for f in untraded),
                               mn.summary_metric("trade", False,
                                                 {"traded": traded, "deaths": n,
                                                  "players": players, "missers": missers}, who),
                               [_ref(map_number, f["round"], f["t"], f["sids"][0])
                                for f in untraded],
                               count=n - traded,
                               players=_counts(players)))  # fmt: skip
        elif tone == "good":
            trades = []
            for r, k in deaths:
                if k.get("traded"):
                    nxt = next((x for x in r.r["kills"] if x["v"] == k["a"] and x["t"] >= k["t"]
                                and r.mine(x["a"])), None)  # fmt: skip
                    if nxt is not None:
                        trades.append((r, nxt))
            items.append(_item("trade", "metric", True, sum(abs(r.delta(k)) for r, k in trades),
                               mn.summary_metric("trade", True,
                                                 {"traded": traded, "deaths": n}, who),
                               [ref(r, k["t"], k["a"]) for r, k in trades],
                               count=traded))  # fmt: skip

    # Buys.
    def buy_number(key: str, part: list[_Round], bad, good, fewest_bad, fewest_good) -> None:
        if not part:
            return
        w, n = sum(1 for r in part if r.won), len(part)
        tone = ""
        if good is not None and n >= _fewest(fewest_good, sides) and w / n >= good:
            tone = "good"
        elif bad is not None and n >= _fewest(fewest_bad, sides) and w / n <= bad:
            tone = "bad"
        number(key, f"{w}/{n}", tone)
        if tone:
            items.append(_item(key, "metric", tone == "good", _over(part, tone == "good"),
                               mn.summary_metric(key, tone == "good",
                                                 {"won": w, "n": n,
                                                  "rounds": [r.n for r in part
                                                             if r.won == (tone == "good")]},
                                                 who),
                               [ref(r) for r in part if r.won == (tone == "good")]))  # fmt: skip

    full = [r for r in rounds if r.buy == "full" and r.their_buy == "full"]
    buy_number("full_v_full", full, FULL_V_FULL[0], FULL_V_FULL[1], FULL_V_FULL[2],
               FULL_V_FULL[2])  # fmt: skip
    force = [r for r in rounds if r.buy == "force"]
    buy_number("force", force, FORCE_BAD[0], FORCE_GOOD[0], FORCE_BAD[1], FORCE_GOOD[1])
    eco = [r for r in rounds if r.buy == "eco"]
    if any(r.won for r in eco):
        w = sum(1 for r in eco if r.won)
        items.append(_item("eco", "metric", True, _over(eco, True),
                           mn.summary_metric("eco", True,
                                             {"won": w, "n": len(eco),
                                              "rounds": [r.n for r in eco if r.won]}, who),
                           [ref(r) for r in eco if r.won]))  # fmt: skip
    light = [r for r in rounds if r.buy == "full" and r.their_buy in ("eco", "force")]
    if light:
        lost = [r for r in light if not r.won]
        to_eco = any(r.their_buy == "eco" for r in lost)
        w, n = len(light) - len(lost), len(light)
        rate_bad = n >= _fewest(LIGHT_BAD[1], sides) and w / n <= LIGHT_BAD[0]
        if lost and (to_eco or rate_bad):
            items.append(_item("full_v_light", "metric", False, _over(light, False),
                               mn.summary_metric("full_v_light", False,
                                                 {"won": w, "n": n,
                                                  "rounds": [r.n for r in lost]}, who),
                               [ref(r) for r in lost]))  # fmt: skip

    # After the plant: as T holding it, as CT taking it back.
    planted = [r for r in rounds if r.side == "t" and r.plant is not None]
    if planted:
        w, n = sum(1 for r in planted if r.won), len(planted)
        bad, good, fewest = POST_PLANT
        tone = ""
        if n >= fewest:
            tone = "good" if w / n >= good else "bad" if w / n <= bad else ""
        number("post_plant", f"{w}/{n}", tone)
        if tone:
            part = [r for r in planted if r.won == (tone == "good")]
            weight = sum((1 - r.wp_after_plant()) if r.won else r.wp_after_plant() for r in part)
            items.append(_item("post_plant", "metric", tone == "good", weight,
                               mn.summary_metric("post_plant", tone == "good",
                                                 {"won": w, "n": n,
                                                  "rounds": [r.n for r in part]}, who),
                               [ref(r, r.plant["t"]) for r in part]))  # fmt: skip
    retakes = [r for r in rounds if r.side == "ct" and r.plant is not None]
    if retakes:
        w, n = sum(1 for r in retakes if r.won), len(retakes)
        tone = "good" if n >= RETAKE_GOOD[1] and w / n >= RETAKE_GOOD[0] else ""
        number("retake", f"{w}/{n}", tone)
        if tone:
            part = [r for r in retakes if r.won]
            items.append(_item("retake", "metric", True,
                               sum(1 - r.wp_after_plant() for r in part),
                               mn.summary_metric("retake", True,
                                                 {"won": w, "n": n,
                                                  "rounds": [r.n for r in part]}, who),
                               [ref(r, r.plant["t"]) for r in part]))  # fmt: skip

    # Runs of Rounds, and Rounds won from far behind.
    run: list[_Round] = []
    runs = []
    for r in sorted(rounds, key=lambda x: x.n):
        if run and run[-1].won != r.won:
            runs.append(run)
            run = []
        run.append(r)
    runs.append(run)
    for part in runs:
        if len(part) >= STREAK:
            key = "win_streak" if part[0].won else "loss_streak"
            items.append(_item(key, "metric", part[0].won, _over(part, part[0].won),
                               mn.summary_metric(key, part[0].won,
                                                 {"rounds": [r.n for r in part]}, who),
                               [ref(r) for r in part]))  # fmt: skip
    comebacks = [r for r in rounds if r.won and r.wp and min(p for _t, p in r.wp) <= COMEBACK_WP]
    if len(comebacks) >= COMEBACK_MIN:
        items.append(_item("comeback", "metric", True,
                           sum(1 - min(p for _t, p in r.wp) for r in comebacks),
                           mn.summary_metric("comeback", True,
                                             {"n": len(comebacks),
                                              "rounds": [r.n for r in comebacks]}, who),
                           [ref(r) for r in comebacks]))  # fmt: skip

    # Patterns: the same Finding again and again.
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in stored["findings"]:
        if f["code"] in TRADE_CODES:
            continue
        if f["round"] is None:
            if len(sides) == 2 and f.get("team_id") == team_id:
                groups[f["code"]].append(f)
        elif f["round"] in by_n and f["side"] == by_n[f["round"]].side:
            groups[f["code"]].append(f)
    for code, found in groups.items():
        rate = len(found) / len(rounds) * 24
        # Every Team gets frags and dies untraded: only more than usual is a Pattern.
        if len(found) < PATTERN_MIN or rate < PATTERN_P75.get(code, 0.0):
            continue
        players = Counter(f["sids"][0] for f in found if f.get("sids")).most_common()
        spots = Counter((f.get("facts") or {}).get("spot") or "" for f in found).most_common()
        spots = [(s, c) for s, c in spots if s and c >= 2]
        facts = {"count": len(found), "players": players, "spots": spots}
        items.append(_item(code, "pattern", is_good(found[0]), sum(value(f) for f in found),
                           mn.summary_pattern(code, facts, who),
                           [_ref(map_number, f["round"], f["t"], (f.get("sids") or [None])[0])
                            for f in found if f["round"] is not None],
                           count=len(found),
                           players=_counts(players), spots=_counts(spots, "name")))  # fmt: skip

    strengths = sorted((i for i in items if i["good"]), key=lambda i: -i["weight"])
    problems = sorted((i for i in items if not i["good"]), key=lambda i: -i["weight"])
    return {
        "team_id": team_id,
        "rounds": len(rounds),
        "won": won,
        "numbers": numbers,
        "strengths": strengths,
        "problems": problems,
        "focus": focus_points(problems),
    }


def focus_points(problems: list[dict]) -> list[dict]:
    """What to work on first: the costliest problems that come with advice."""
    out = [p for p in problems if p["weight"] >= FOCUS_MIN_COST and p["advice"]]
    return out[:FOCUS_POINTS]


def map_summary(stored: dict, team_ids: list, who, map_number: int | None = None) -> dict:
    """Both Teams' Summaries of a Match Map, over both Sides and each one."""
    return {
        scope: [s for t in team_ids if (s := team_summary(stored, t, scope, who, map_number))]
        for scope in SIDES
    }


# --------------------------------------------------------------- a Match ---
def match_summary(maps: list[dict], team_ids: list, labels: dict) -> list[dict]:
    """Each Team's Summary of a Match from its Match Maps' Summaries.

    ``maps`` holds, per reviewed Match Map, ``map_number``, ``summary`` (its
    ``map_summary``'s ``all`` list) and ``players`` (the stored Review's);
    ``labels`` names each Map by number. A Pattern counts here when it shows on
    two Maps or more.
    """
    out = []
    for team_id in team_ids:
        per_map = []
        for m in maps:
            summary = next((s for s in m["summary"] if s["team_id"] == team_id), None)
            if summary is not None:
                per_map.append((m["map_number"], summary))
        if not per_map:
            continue
        merged: dict[tuple, dict] = {}
        for number, summary in per_map:
            for item in summary["strengths"] + summary["problems"]:
                key = (item["key"], item["good"])
                if key not in merged:
                    merged[key] = {**item, "maps": [], "weight": 0.0, "refs": [], "count": 0,
                                   "texts": []}  # fmt: skip
                m = merged[key]
                m["maps"].append(number)
                m["weight"] = round(m["weight"] + item["weight"], 3)
                m["refs"] += item["refs"]
                m["count"] += item["count"]
                m["texts"].append({"map_number": number, "text": item["text"]})
        across = [m for m in merged.values() if len(m["maps"]) >= 2]
        for m in merged.values():
            if len(m["maps"]) >= 2:
                m["text"] = mn.summary_across(m, labels)
            else:  # a Focus point from one Map says which
                m["text"] = f"{labels.get(m['maps'][0], '')}: {m['text']}"
        strengths = sorted((m for m in across if m["good"]), key=lambda m: -m["weight"])
        problems = sorted((m for m in across if not m["good"]), key=lambda m: -m["weight"])
        every = sorted((m for m in merged.values() if not m["good"]), key=lambda m: -m["weight"])
        out.append(
            {
                "team_id": team_id,
                "maps_played": len(per_map),
                "rounds": sum(s["rounds"] for _n, s in per_map),
                "won": sum(s["won"] for _n, s in per_map),
                "strengths": strengths,
                "problems": problems,
                "focus": focus_points(every),
                "players": _players(maps, team_id),
            }
        )
    return out


def _players(maps: list[dict], team_id) -> list[dict]:
    """A Team's Players over the Match: Swing summed, and their Findings by kind."""
    rows: dict[str, dict] = {}
    for m in maps:
        for p in m["players"]:
            if p.get("team_id") != team_id:
                continue
            row = rows.setdefault(p["sid"], {"sid": p["sid"], "name": p["name"], "maps": 0,
                                             "rounds": 0, "swing": 0.0,
                                             "counts": defaultdict(int)})  # fmt: skip
            row["maps"] += 1
            row["rounds"] += p["rounds"]
            row["swing"] += p["swing"]
            for kind, c in (p.get("counts") or {}).items():
                row["counts"][kind] += c
    out = []
    for row in rows.values():
        row["swing"] = round(row["swing"], 4)
        row["swing_per_round"] = round(row["swing"] / row["rounds"], 4) if row["rounds"] else 0.0
        row["counts"] = dict(row["counts"])
        out.append(row)
    return sorted(out, key=lambda r: -r["swing"])


def pattern_percentiles(payloads, q: float = 0.75, fewest_maps: int = 20) -> dict[str, float]:
    """Each Finding code's rate per 24 Rounds at the ``q`` quantile over every
    Team-map in ``payloads`` (stored Reviews), counting Team-maps where it is 0;
    codes seen on fewer than ``fewest_maps`` Team-maps are left out (too rare to
    measure: three are a Pattern)."""
    rates: dict[str, list[float]] = defaultdict(list)
    team_maps = 0
    for stored in payloads:
        rounds: Counter = Counter()
        sides: dict[tuple, int] = {}
        for r in stored["rounds"]:
            for side in ("ct", "t"):
                team = r.get(f"{side}_team_id")
                if team is not None:
                    rounds[team] += 1
                    sides[(r["n"], side)] = team
        found: dict[int, Counter] = defaultdict(Counter)
        for f in stored["findings"]:
            team = sides.get((f["round"], f["side"]))
            if team is not None and f["code"] not in TRADE_CODES:
                found[team][f["code"]] += 1
        for team, n in rounds.items():
            team_maps += 1
            for code, k in found[team].items():
                rates[code].append(24 * k / n)
    out = {}
    for code, seen in rates.items():
        if len(seen) < fewest_maps:
            continue
        every = sorted(seen + [0.0] * (team_maps - len(seen)))
        out[code] = round(every[min(len(every) - 1, int(q * len(every)))], 1)
    return dict(sorted(out.items()))
