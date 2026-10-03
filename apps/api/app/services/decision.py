"""Эзний давхар: гурван өгүүлбэр, дөрвөн тоо, гурван үйлдэл.

Тоглолтын өмнөх тайлан хоёр өөр хүнд хэрэгтэй. Шинжээч бүх зүйлийг уншина;
эзэн, IGL хоёр **шийдвэр** гаргана. Тэдний асуулт гурав л байдаг: хожиж чадах
уу, аль газрын зургийг сонгох вэ, юу өөрчлөх вэ.

:mod:`app.services.gameplan` бүх тоог аль хэдийн бодсон байдаг. Энэ модуль
шинэ тоо бодохгүй -- зөвхөн тэдгээрээс *хамгийн шийдвэрлэх* дөрвийг ялгаж
аваад, нэг дэлгэцэнд багтаах хэлбэрт оруулна. Тиймээс энд гарч ирсэн тоо бүр
хуудасны доод хэсэгт өөрийн нотолгоотойгоо давхар байх ёстой: дүгнэлт нь
нотолгооноосоо салж чадахгүй.

Нэг картад нэг тоо. Хоёр тоо тавьсан мөчид карт хүснэгт болж, хүн уншихаа
болино -- энэ нь дизайны дүрэм биш, ажиглалт.

cstat-ийн ``hltv/services/decision.py``-аас шилжүүлсэн.
"""

from __future__ import annotations

from app.services import mn

# Хожих боломжийг үнэлэх босгууд. Арван хоёр үзүүлэлтээс хэдэн дээр нь бид
# урд байна вэ гэдгээр хэмжинэ -- хоёр багийг өөр хоорондоо биш, ижил
# аргачлалаар өөрсдийн тоглолт дээр нь.
EVEN_METRICS = 5
STRONG_METRICS = 7
# Энэ хэмжээнээс дээш савлалт бол "хөшүүрэг" -- өөрчилж чадах зүйл.
LEVER_SWING = 20.0
LEVER_COLLAPSE = 8.0


def build(report: dict, my_team, opponent) -> dict:
    """Эзний шийдвэрийн дэлгэц. ``gameplan.build`` -ийн үр дүнг л уншина."""
    ahead, total, per_metric = _form_balance(report)
    stale = bool((report.get("continuity") or {}).get("stale"))
    levers = _levers(report)
    call, label, tone = _call(ahead, total, stale, levers)

    return {
        "call": call,
        "label": label,
        "tone": tone,
        "lead": _lead(call, report, my_team, opponent, ahead, total, stale),
        "cards": _cards(report, opponent),
        "moves": _moves(report, levers, my_team, opponent),
        "balance": {"ahead": ahead, "total": total, "metrics": per_metric},
        "confidence": _confidence(report),
    }


# ----------------------------------------------------------- хүчний тэнцвэр
def _form_balance(report: dict):
    """Хэдэн үзүүлэлт дээр бид урд байна вэ -- өөрсдийн тоглолт дээр хэмжсэн.

    Хоёр багийг шууд харьцуулах нь зөв: энд аль аль нь ижил pool-той
    z-score-оор биш, өөрсдийн формоороо зэрэгцэж байна. Толгойн тоо (1-6)
    биш, чадварын зэрэгцүүлэлт.
    """
    mine = (report.get("my_team") or {}).get("metrics") or {}
    theirs = (report.get("opponent") or {}).get("metrics") or {}
    rows, ahead = [], 0
    for key in mn.METRICS:
        a, b = mine.get(key), theirs.get(key)
        if a is None or b is None:
            continue
        win = float(a) >= float(b)
        ahead += 1 if win else 0
        rows.append({"key": key, "label": mn.metric(key), "mine": a, "theirs": b, "ahead": win})
    return ahead, len(rows), rows


def _levers(report: dict) -> list[dict]:
    """Өөрчилж чадах зүйлс: том савлалт бүхий олдворууд.

    Хөшүүрэг гэдэг нь зүгээр л сул тал биш -- *үйлдлээр өөрчлөгддөг* сул тал.
    Тэдний тулгуур тоглогчийг эрт алах нь хөшүүрэг; ADR бага байх нь биш.
    """
    out = []
    for pin in (report.get("linchpins") or {}).get("opponent") or []:
        if pin["swing"] >= LEVER_SWING:
            out.append({"kind": "linchpin", "swing": pin["swing"], "data": pin})
    for row in (report.get("my_delta") or {}).get("collapses") or []:
        if abs(row["delta"]) >= LEVER_COLLAPSE:
            out.append({"kind": "collapse", "swing": abs(row["delta"]), "data": row})
    for pin in (report.get("linchpins") or {}).get("mine") or []:
        if pin["swing"] >= LEVER_SWING:
            out.append({"kind": "protect", "swing": pin["swing"], "data": pin})
    out.sort(key=lambda r: -r["swing"])
    return out


def _call(ahead: int, total: int, stale: bool, levers: list[dict]):
    """Хожиж чадах уу гэдэгт өгөх ганц үг.

    Гурван хүчин зүйл: хүчний тэнцвэр, толгойн тооны хамаарал, өөрчилж чадах
    хөшүүргийн тоо. Хөшүүрэггүй тэнцүү баг бол тэнцүү; хөшүүрэгтэй бага зэрэг
    дутуу баг бол боломжтой -- ялгаа нь тоглолтын өмнө юу хийж чадахад байна.
    """
    if not total:
        return "unknown", "ӨГӨГДӨЛ ХҮРЭЛЦЭХГҮЙ", "warn"
    # Хүчний зөрүү нь шийднэ. Толгойн тооны хуучирсан байдал (``stale``) нь
    # *тэр тоог* тайлбарлана, чадварын зөрүүг арилгахгүй -- 12-оос 2 дээр урд
    # байгаа багийг "тэнцүү" гэж нэрлэвэл хуудас итгэл алдана. Хөшүүрэг нь
    # ойрхон тохиолдолд л шийдвэрлэнэ, хол зөрүүг нөхөхгүй.
    if ahead >= STRONG_METRICS:
        return "winnable", "ХОЖИХ БОЛОМЖТОЙ", "good"
    if ahead >= EVEN_METRICS:
        return (
            ("winnable", "ХОЖИХ БОЛОМЖТОЙ", "good")
            if len(levers) >= 2
            else ("close", "ТЭНЦҮҮ — БЭЛТГЭЛЭЭС ХАМААРНА", "warn")
        )
    if ahead >= EVEN_METRICS - 2:
        return "close", "ДУТУУ — ХӨШҮҮРЭГ ДЭЭР ТОГЛОНО", "warn"
    if levers:
        return "hard", "ХҮНД — ГЭХДЭЭ ХӨШҮҮРЭГ БАЙНА", "crit"
    return "hard", "ХҮНД", "crit"


def _lead(call, report, my_team, opponent, ahead, total, stale) -> str:
    """Хоёр өгүүлбэр. Эхнийх нь дүгнэлт, хоёр дахь нь яагаад."""
    h2h = (report.get("head_to_head") or {}).get("totals") or {}
    won, lost = h2h.get("maps_won") or 0, h2h.get("maps_lost") or 0
    cont = report.get("continuity") or {}
    sides = cont.get("sides") or {}
    mine_c = sides.get("mine") or {}

    bits = []
    if stale and mine_c:
        bits.append(
            f"{won}-{lost} гэдэг тоо хуучирсан: одоогийн {mine_c.get('of', 5)}-аас "
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

    if total:
        bits.append(
            f"Өөрсдийн формоор {total} үзүүлэлтийн {ahead} дээр нь бид урд байна"
            + (" — цаасан дээр тэнцүү." if ahead >= EVEN_METRICS else " — зөрүү бодитой.")
        )
    return " ".join(bits)


# ------------------------------------------------------------------ картууд
def _cards(report: dict, opponent) -> list[dict]:
    """Дөрвөн карт, тус бүрд нэг тоо, нэг үйлдэл.

    Сонгох дараалал: тэдний хамгийн эмзэг тал, манай хамгийн том уналт, манай
    хамгийн сул үзүүлэлт, бид аль хэдийн тэнцүү байгаа газар. Эхний гурав нь
    юу засахыг, сүүлийнх нь юунд найдахыг хэлнэ.
    """
    cards: list[dict] = []

    pins = (report.get("linchpins") or {}).get("opponent") or []
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

    weak = (
        (report.get("my_team") or {}).get("weaknesses")
        or (report.get("my_team") or {}).get("worst_relative")
        or []
    )
    if weak:
        w = weak[0]
        rounds = ((report.get("my_team") or {}).get("metrics") or {}).get("rounds")
        cards.append(
            {
                "value": f"{w['value']}{w.get('unit') or ''}",
                "unit": "",
                "label": mn.metric(w["key"]),
                "action": "багийн сул тал",
                # Түүврийг монголоор, жишгийг бөөрөнхийлж: 51.1889 гэсэн тоо
                # нарийвчлалыг биш, хайнга байдлыг л илэрхийлнэ.
                "detail": f"жишиг {round(float(w['pool_mean']), 1)}"
                + (f" · {mn.sample(rounds=rounds)}" if rounds else ""),
                "tone": "crit",
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
