"""Эзний давхар: гурван өгүүлбэр, дөрвөн тоо, гурван үйлдэл.

Тоглолтын өмнөх тайлан хоёр өөр хүнд хэрэгтэй. Шинжээч бүх зүйлийг уншина;
эзэн, IGL хоёр **шийдвэр** гаргана. Тэдний асуулт гурав л байдаг: хожиж чадах
уу, аль газрын зургийг сонгох вэ, юу өөрчлөх вэ.

Хожих магадлалыг Forecast (:mod:`app.services.forecast`) хэлнэ. Бусад тоог
:mod:`app.services.gameplan` аль хэдийн бодсон байдаг: энэ модуль тэдгээрээс
*хамгийн шийдвэрлэх* дөрвийг ялгаж аваад, нэг дэлгэцэнд багтаах хэлбэрт
оруулна. Тиймээс энд гарч ирсэн тоо бүр хуудасны доод хэсэгт өөрийн
нотолгоотойгоо давхар байх ёстой: дүгнэлт нь нотолгооноосоо салж чадахгүй.

Нэг картад нэг тоо. Хоёр тоо тавьсан мөчид карт хүснэгт болж, хүн уншихаа
болино -- энэ нь дизайны дүрэм биш, ажиглалт.

cstat-ийн ``hltv/services/decision.py``-аас шилжүүлсэн.
"""

from __future__ import annotations

from app.services import forecast, lineup, mn

# Энэ хэмжээнээс дээш савлалт бол "хөшүүрэг" -- өөрчилж чадах зүйл.
LEVER_SWING = 20.0
LEVER_COLLAPSE = 8.0
# The call is made on the format most series are played in.
CALL_FORMAT = "bo3"


def build(report: dict, my_team, opponent) -> dict:
    """Эзний шийдвэрийн дэлгэц: Forecast (docs/plans/03), карт, гурван үйлдэл.

    Хожиж чадах уу гэдгийг хоёр багийн Rating хэлнэ: өрсөлдөгчдийнх нь хүчийг
    тооцсон, шалгагдсан тоо. Өмнө нь 12 үзүүлэлтээс хэд дээр нь урд байгааг
    тоолдог байсан ч энэ нь өрсөлдөгчдийн хүчийг тооцдоггүй байсан (GP-2)."""
    stale = bool((report.get("continuity") or {}).get("stale"))
    levers = _levers(report)
    fc = forecast.build(
        my_team,
        opponent,
        my_lineup=_picked(my_team),
        their_lineup=_picked(opponent),
    )
    call, label, tone = _call(fc)
    return {
        "call": call,
        "label": label,
        "tone": tone,
        "lead": _lead(fc, report, my_team, opponent, stale),
        "forecast": _forecast(fc, my_team, opponent),
        "cards": _cards(report, opponent),
        "moves": _moves(report, levers, my_team, opponent),
        "confidence": _confidence(report),
    }


def _picked(team) -> list[str] | None:
    chosen = lineup.chosen(team)
    return [p.name for p in chosen] if chosen else None


# --------------------------------------------------------------- Forecast
def _call(fc: dict):
    """Хожиж чадах уу гэдэгт өгөх ганц үг: Bo3-ын Forecast-аар."""
    series = (fc.get("series") or {}).get(CALL_FORMAT)
    if not series:
        return "unknown", "RATING АЛГА", "warn"
    word, tone = mn.forecast_scale(series["expected"])
    call = {"good": "winnable", "warn": "close", "crit": "hard"}[tone]
    return call, f"{word.upper()} · ~{mn.round5(series['expected'])}%", tone


def _forecast(fc: dict, my_team, opponent) -> dict:
    """The Forecast as the page shows it: worded, rounded to 5, with its limits."""
    series = []
    for fmt, s in (fc.get("series") or {}).items():
        word, tone = mn.forecast_scale(s["expected"])
        series.append(
            {
                "format": mn.FORMAT[fmt],
                "pct": mn.round5(s["expected"]),
                "p": s["expected"],
                "word": word,
                "tone": tone,
                "often": mn.forecast_often(s["expected"]),
                "trust": mn.forecast_trust(s.get("reliability")),
            }
        )
    ratings = []
    for team, r in ((my_team, fc["ratings"]["mine"]), (opponent, fc["ratings"]["theirs"])):
        ratings.append(
            {
                "team": team.name,
                "rating": round(r["rating"]) if r else None,
                "series": r["series"] if r else 0,
                "region": (r or {}).get("region") or "",
                "last": str(r["last"]) if r and r["last"] else "",
            }
        )
    return {
        "series": series,
        "ratings": ratings,
        "maps": [
            {
                "map": mn.game_map(m["map"]),
                "pct": mn.round5(m["p"]),
                "played_mine": m["played_mine"],
                "played_theirs": m["played_theirs"],
            }
            for m in fc.get("maps") or []
        ],
        "maps_used": bool(fc.get("offsets_used")),
        "limits": [mn.forecast_limit(item) for item in fc.get("limits") or []],
        "model": fc.get("model") or "",
    }


def _levers(report: dict) -> list[dict]:
    """Өөрчилж чадах зүйлс: том савлалт бүхий олдворууд.

    Хөшүүрэг гэдэг нь зүгээр л сул тал биш -- *үйлдлээр өөрчлөгддөг* сул тал.
    Тэдний тулгуур тоглогчийг эрт алах нь хөшүүрэг; ADR бага байх нь биш.
    """
    out = []
    # A linchpin counts only past the permutation test against his teammates (PL-8).
    for pin in (report.get("linchpins") or {}).get("opponent") or []:
        if pin["swing"] >= LEVER_SWING and pin.get("significant"):
            out.append({"kind": "linchpin", "swing": pin["swing"], "data": pin})
    for row in (report.get("my_delta") or {}).get("collapses") or []:
        if abs(row["delta"]) >= LEVER_COLLAPSE:
            out.append({"kind": "collapse", "swing": abs(row["delta"]), "data": row})
    for pin in (report.get("linchpins") or {}).get("mine") or []:
        if pin["swing"] >= LEVER_SWING and pin.get("significant"):
            out.append({"kind": "protect", "swing": pin["swing"], "data": pin})
    out.sort(key=lambda r: -r["swing"])
    return out


def _lead(fc, report, my_team, opponent, stale) -> str:
    """Дүгнэлт, яагаад, хэр итгэх вэ."""
    h2h = (report.get("head_to_head") or {}).get("totals") or {}
    won, lost = h2h.get("maps_won") or 0, h2h.get("maps_lost") or 0
    cont = report.get("continuity") or {}
    sides = cont.get("sides") or {}
    mine_c = sides.get("mine") or {}

    bits = []
    series = (fc.get("series") or {}).get(CALL_FORMAT)
    r_mine, r_theirs = fc["ratings"]["mine"], fc["ratings"]["theirs"]
    if series and r_mine and r_theirs:
        bits.append(
            f"Rating: {my_team.name} {round(r_mine['rating'])}, "
            f"{opponent.name} {round(r_theirs['rating'])}."
        )
        bits.append(
            mn.forecast_line(CALL_FORMAT, series["expected"], my_team.name, opponent.name)[:-1]
            + f": {mn.forecast_often(series['expected'])}."
        )
    if stale and mine_c:
        bits.append(
            f"Хоорондын {won}-{lost} гэдэг тоо хуучирсан: одоогийн {mine_c.get('of', 5)}-аас "
            f"зөвхөн {mine_c.get('n', 0)} нь тэр тоглолтуудад байсан"
            + (
                f", {mn.plural_players(mine_c.get('unseen'))} тэдэнтэй огт тоглож үзээгүй"
                if mine_c.get("unseen")
                else ""
            )
            + "."
        )
    elif won or lost:
        bits.append(f"H2H {won}-{lost}.")
    return " ".join(bits)


# ------------------------------------------------------------------ картууд
def _cards(report: dict, opponent) -> list[dict]:
    """Дөрвөн карт, тус бүрд нэг тоо, нэг үйлдэл.

    Сонгох дараалал: тэдний хамгийн эмзэг тал, манай хамгийн том уналт, манай
    хамгийн сул үзүүлэлт, бид аль хэдийн тэнцүү байгаа газар. Эхний гурав нь
    юу засахыг, сүүлийнх нь юунд найдахыг хэлнэ.
    """
    cards: list[dict] = []

    pins = [
        p for p in (report.get("linchpins") or {}).get("opponent") or [] if p.get("significant")
    ]
    if pins:
        p = pins[0]
        cards.append(
            {
                "value": mn.signed(p["swing"], 0),
                "unit": "оноо",
                "label": f"{p['name']}-г эрт алахад",
                "action": "эхний 30 сек",
                "detail": f"{mn.pct(p['other_pct'])} → {mn.pct(p['early_pct'])} "
                f"({p['early_deaths']} раунд)",
                "tone": "good",
            }
        )

    collapses = (report.get("my_delta") or {}).get("collapses") or []
    if collapses:
        c = collapses[0]
        cards.append(
            {
                "value": mn.signed(c["delta"], 1),
                "unit": c.get("unit") or "",
                "label": mn.metric(c["key"]),
                "action": "тэдний эсрэг унадаг",
                "detail": f"{c['own']}{c.get('unit') or ''} → {c['versus']}{c.get('unit') or ''}",
                "tone": "crit",
            }
        )

    mine = report.get("my_team") or {}
    # A Weakness stands out below the Pool (CONTEXT.md); with none, the card shows
    # our lowest number for what it is, not as a weakness.
    flagged = bool(mine.get("weaknesses"))
    weak = mine.get("weaknesses") or mine.get("worst_relative") or []
    if weak:
        w = weak[0]
        rounds = (mine.get("metrics") or {}).get("rounds")
        cards.append(
            {
                "value": f"{w['value']}{w.get('unit') or ''}",
                "unit": "",
                "label": mn.metric(w["key"]),
                "action": "багийн сул тал" if flagged else "харьцангуй хамгийн доогуур",
                # Түүврийг монголоор, жишгийг бөөрөнхийлж: 51.1889 гэсэн тоо
                # нарийвчлалыг биш, хайнга байдлыг л илэрхийлнэ.
                "detail": f"жишиг {round(float(w['pool_mean']), 1)}"
                + (f" · {mn.sample(rounds=rounds)}" if rounds else ""),
                "tone": "crit" if flagged else "warn",
            }
        )

    ma = report.get("man_advantage") or {}
    ours, theirs = (ma.get("mine") or {}).get("up"), (ma.get("opponent") or {}).get("up")
    if ours and theirs and ours.get("reached"):
        cards.append(
            {
                "value": mn.pct(ours["win_pct"], 0),
                "unit": "",
                "label": "Хүн давуу үед хожил",
                "action": (
                    "тэднээс дээгүүр"
                    if ours["win_pct"] >= theirs["win_pct"]
                    else "тэдэнтэй ойролцоо"
                ),
                "detail": f"{ours['won']}/{ours['reached']} · тэд {mn.pct(theirs['win_pct'], 0)}",
                "tone": "good" if ours["win_pct"] >= theirs["win_pct"] else "warn",
            }
        )
    return cards[:4]


# ------------------------------------------------------------------ үйлдэл
def _moves(report: dict, levers: list[dict], my_team, opponent) -> list[dict]:
    """Гурван үйлдэл. Илүүг өгвөл аль нь ч хийгдэхгүй."""
    moves: list[dict] = []

    seen_kinds = set()
    for lever in levers:
        if len(moves) >= 3:
            break
        kind, d = lever["kind"], lever["data"]
        # Төрөл тус бүрээс нэг. Хоёр "X-г хамгаал" бол нэг заавар давхардсан нь.
        if kind in seen_kinds:
            continue
        seen_kinds.add(kind)
        if kind == "linchpin":
            moves.append(
                {
                    "what": f"{d['name']}-г эхний 30 секундэд ал",
                    "why": f"Тэр эрт үхэхэд {opponent.name} {mn.pct(d['other_pct'])}-аас "
                    f"{mn.pct(d['early_pct'])} болж унадаг "
                    f"({d['early_won']}/{d['early_deaths']} раунд). "
                    "Түүний төлөө хоёр тоглогч солих нь ч ашигтай.",
                    "tone": "good",
                }
            )
        elif kind == "protect":
            moves.append(
                {
                    "what": f"{d['name']}-г нээлтээс хамгаал",
                    "why": f"Тэр эрт үхэхэд бид {mn.pct(d['other_pct'])}-аас "
                    f"{mn.pct(d['early_pct'])} болж унадаг "
                    f"({d['early_deaths']} раунд). Эхний холбоог тэр авах ёсгүй.",
                    "tone": "warn",
                }
            )
        elif kind == "collapse":
            moves.append(
                {
                    "what": f"{mn.metric(d['key'])} — энэ дээр бэлтгэ",
                    "why": f"Өөрсдийн тоглолтод {d['own']}{d.get('unit') or ''}, "
                    f"тэдний эсрэг {d['versus']}{d.get('unit') or ''} "
                    f"({mn.signed(d['delta'])}). {mn.METRIC_WHY.get(d['key'], '')}",
                    "tone": "crit",
                }
            )

    if len(moves) < 3:
        board = (report.get("board") or {}).get("board") or []
        bans = [b for b in board if b["verdict"]["call"] == "ban"][:2]
        if bans:
            moves.append(
                {
                    "what": "Вето: " + ", ".join(mn.game_map(b["map"]) for b in bans) + " хориглох",
                    "why": "; ".join(
                        f"{mn.game_map(b['map'])}: {b['verdict']['why']}" for b in bans
                    ),
                    "tone": "warn",
                }
            )
    return moves[:3]


def _confidence(report: dict) -> str:
    s = report.get("sample") or {}
    return (
        f"Энэ дүгнэлт манай {s.get('my_maps', 0)}, тэдний "
        f"{s.get('opponent_maps', 0)}, хоорондын {s.get('h2h_maps', 0)} map "
        f"дээр тулгуурлаж, {s.get('pool_teams', 0)} багийн жишигтэй "
        "харьцуулсан. Батлагдсан үнэн биш, шалгах чиглэл."
    )
