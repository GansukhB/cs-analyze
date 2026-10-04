"""Монгол хэлний үг хэллэгийн давхарга.

Шинжилгээний сервисүүд **тоо ба түлхүүр** буцаадаг; хүнд харагдах өгүүлбэрийг
энд угсарна. Ингэснээр монгол текст нэг файлд төвлөрч, шинжилгээний логик
хэлнээс хамааралгүй хэвээр үлдэнэ -- эсрэг тохиолдолд орчуулга нь арван модуль
дундуур тарж, аль нэгийг нь засахад нөгөө нь англиар үлддэг.

Дүрэм: энэ модуль ORM-д хандахгүй, тоо бодохгүй. Зөвхөн хэлбэржүүлнэ.

cstat-ийн ``hltv/services/mn.py``-аас бүтнээр нь шилжүүлсэн.
"""

from __future__ import annotations

# --------------------------------------------------------------- толь бичиг --
SIDE = {"ct": "CT (хамгаалалт)", "t": "T (довтолгоо)"}
SIDE_SHORT = {"ct": "CT", "t": "T"}

MAPS = {
    "de_mirage": "Mirage",
    "de_dust2": "Dust II",
    "de_nuke": "Nuke",
    "de_inferno": "Inferno",
    "de_ancient": "Ancient",
    "de_anubis": "Anubis",
    "de_overpass": "Overpass",
    "de_cache": "Cache",
    "de_train": "Train",
    "de_vertigo": "Vertigo",
}

ROLES = {
    "awper": "AWP-чин",
    "entry": "Entry",
    "support": "Support",
    "lurker": "Lurker",
    "trader": "Trader",
    "anchor": "Anchor",
    "rotator": "Rotator",
}

ROLE_BLURB = {
    "awper": "Багийн винтовыг барина. Нээлтийн kill болон дараагийн раундад AWP "
    "амьд үлдсэн эсэхээр үнэлнэ.",
    "entry": "Бусдын өмнө эхний холбоог авна. Хэдэн удаа нээж байгаа, тэр үхэхэд "
    "раунд амьд үлдэж байгаа эсэхээр үнэлнэ.",
    "support": "Өөр хүний авах орон зайг худалдаж авна. Гранатын damage, тэр "
    "гранат шидсэн раундад баг юу хийснээр үнэлнэ.",
    "lurker": "Бусад тоглогчдоос тусдаа, хожуу бөгөөд ганцаараа тоглоно. Kill хийх зорилготой биш, "
    "тусгаар тоглосонооороо ямар үр дүн авчирснаар үнэлнэ.",
    "trader": "Нэвтрэгчийн мөрөн дээр орж солилтыг барина. Хохирлынх нь хэдэн "
    "хувь солилтын цонхонд ирснээр үнэлнэ.",
    "anchor": "Нэг цэгийг, ихэвчлэн цөөн тоогоор, тусламж ирэх хүртэл барина. "
    "Худалдаж авсан хугацаа, олон алалтаар үнэлнэ; ADR-аар хэзээ ч биш.",
    "rotator": "Нэг байрлалаар биш, map дотор хөдөлгөөнтэй тоглоно -- эрт хяналт авч эргэлдэнэ. "
    "Эрт үхэлгүйгээр эрт kill авахаар үнэлнэ.",
}

METRICS = {
    "ct_win_pct": "CT раунд хожил",
    "t_win_pct": "T раунд хожил",
    "pistol_win_pct": "Гар бууны раунд ялалт",
    "opening_win_pct": "Нээлтийн тулаан",
    "plant_rate": "Сайт дээр bomb тавих",
    "post_plant_win_pct": "Bomb тавьсны дараах хамгаалалт",
    "retake_win_pct": "Retake",
    "traded_death_pct": "Trade",
    "multi_kill_rate": "Multikill rate",
    "adr": "ADR",
    "kast_pct": "KAST",
    "util_per_round": "Utilty per ruond",
}

METRIC_WHY = {
    "ct_win_pct": "Хамгаалах ба retake чадвар.",
    "t_win_pct": "Эзэлгээ хийж, bomb тавих чадвар.",
    "pistol_win_pct": "Хоёр гар бууны раунд зургаан раунд хүртэл үнэтэй.",
    "opening_win_pct": "Эхний холбоог хэн авч байна.",
    "plant_rate": "T раунд хэдэн удаа bomb тавих хүртэл хүрч байна.",
    "post_plant_win_pct": "Тавьсан bomb-ийг раунд болгож хувиргах чадвар.",
    "retake_win_pct": "Тэд тавьсны дараа раундыг retake хийх чадвар.",
    "traded_death_pct": "Үхсэн хүний ард хэн нэгэн байна уу.",
    "multi_kill_rate": "Нэг тоглогч дангаараа авсан раунд.",
    "adr": "Раунд тутмын damage.",
    "kast_pct": "Тоглогч раундад ямар нэг хувь нэмэр оруулсан давтамж.",
    "util_per_round": "Раунд тутмын утаа ба молотов.",
}

WEAPONS = {
    "awp": "AWP",
    "ak47": "AK-47",
    "m4a1": "M4",
    "usp/p2000": "USP/P2000",
    "glock": "Glock",
    "deagle": "Deagle",
    "galilar": "Galil",
    "famas": "Famas",
    "mp9": "MP9",
    "mac10": "MAC-10",
    "tec9": "Tec-9",
    "elite": "Dual Berettas",
    "fiveseven": "Five-SeveN",
    "p250": "P250",
    "mp7": "MP7",
    "ssg08": "Scout",
    "aug": "AUG",
    "sg556": "SG 553",
    "hegrenade": "HE граната",
    "inferno": "Молотов",
    "cz75a": "CZ-75",
    "ump45": "UMP-45",
    "nova": "Nova",
    "xm1014": "XM1014",
    "sawedoff": "Sawed-Off",
    "negev": "Negev",
    "m249": "M249",
    "p90": "P90",
    "bizon": "PP-Bizon",
    "revolver": "R8",
    "world": "орчин",
}

VETO_CALL = {
    "ban": "Ban",
    "pick": "Pick",
    "contest": "тэмцэлдэх",
    "blind": "мэдээлэлгүй",
    "avoid": "зайлсхийх",
    "unknown": "өгөгдөлгүй",
}

CONFIDENCE = {
    "clear": "тодорхой",
    "likely": "магадгүй",
    "split": "хоёрдмол",
    "thin": "цөөн өгөгдөл",
    "none": "өгөгдөл хүрэлцэхгүй",
}

# Вето дүгнэлтийн итгэл. Үүргийн итгэлээс тусдаа шаталбар: ``_map_verdict`` нь
# түүврийн хэмжээнээс low/medium/high буцаадаг бөгөөд эдгээрийг CONFIDENCE-д
# нэгтгэвэл нэг түлхүүр хоёр өөр асуултын хариу болно.
MAP_CONFIDENCE = {
    "high": "өндөр",
    "medium": "дунд",
    "low": "бага",
    "none": "өгөгдөлгүй",
}

FIT = {
    "strong": "хүчтэй",
    "solid": "хэвийн",
    "below par": "жишгээс доогуур",
    "struggling": "хүндрэлтэй",
    "no cohort": "харьцуулах бүлэггүй",
}

# Газрын зургийн дуудлагууд -- зөвхөн хамгийн түгээмэл нь. Байхгүй нэр
# англиараа үлдэнэ: буруу орчуулснаас эх нэрээр нь үлдээх нь дээр, учир нь
# тоглогчид эдгээр нэрийг англиар нь дууддаг.
PLACES = {
    "BombsiteA": "A цэг",
    "BombsiteB": "B цэг",
    "Middle": "Төв",
    "Mid": "Төв",
    "TopofMid": "Төвийн дээд",
    "CTSpawn": "CT төрөлт",
    "TSpawn": "T төрөлт",
    "Catwalk": "Catwalk",
    "Connector": "Connector",
    "Apartments": "Apartments",
    "Underpass": "Underpass",
    "Palace": "Palace",
    "PalaceInterior": "Palace дотор",
    "Ramp": "Ramp",
    "Outside": "Гадна",
    "Lobby": "Lobby",
    "Rafters": "Rafters",
    "Banana": "Banana",
    "Water": "Ус",
    "LowerPark": "Доод парк",
    "UpperPark": "Дээд парк",
    "Walkway": "Walkway",
    "Main": "Main",
    "LongA": "Long A",
    "ExtendedA": "Extended A",
    "MidDoors": "Төвийн хаалга",
    "BDoors": "B хаалга",
    "UnderA": "A доор",
    "Checkers": "Checkers",
    "SnipersNest": "Snipers Nest",
    "Stairs": "Шат",
    "Truck": "Ачааны машин",
    "Shop": "Дэлгүүр",
    "Tunnels": "Хонгил",
    "Canal": "Суваг",
    "Alley": "Гудамж",
    "SideAlley": "Хажуугийн гудамж",
    "House": "Байшин",
    "BackAlley": "Ар гудамж",
    "TYard": "T хашаа",
    "OutsideA": "A гадна",
    "AStairs": "A шат",
    "AMain": "A Main",
    "Construction": "Барилга",
    "Pipe": "Хоолой",
    "Fountain": "Усан оргилуур",
    "TStairs": "T шат",
    "TRamp": "T ramp",
    "LowerMid": "Доод төв",
    "SecondMid": "Хоёрдугаар төв",
    "Balcony": "Тагт",
    "Hut": "Овоохой",
    "Street": "Гудамж",
    "OutsideLong": "Гадна Long",
    "BackofA": "A-гийн ар",
    "Vents": "Агааржуулалт",
    "Heaven": "Heaven",
    "Hell": "Hell",
    "Pit": "Pit",
    "Quad": "Quad",
    "Elevator": "Цахилгаан шат",
    "Squeaky": "Squeaky",
}


# -------------------------------------------------------------- хэлбэржүүлэгч
def side(value: str, short: bool = False) -> str:
    table = SIDE_SHORT if short else SIDE
    return table.get((value or "").lower(), (value or "").upper())


def game_map(name: str) -> str:
    return MAPS.get(name, (name or "").replace("de_", "").title())


def role(key: str) -> str:
    return ROLES.get(key, key or "тодорхойгүй")


def weapon(key: str) -> str:
    return WEAPONS.get(key, key or "?")


def place(key: str) -> str:
    return PLACES.get(key, key or "")


def places(items, limit: int = 3) -> str:
    """[{place, count}] -> 'A цэг (17), Төв (9)'."""
    out = []
    for row in list(items or [])[:limit]:
        name = place(row.get("place") if isinstance(row, dict) else row)
        count = row.get("count") or row.get("kills") if isinstance(row, dict) else None
        out.append(f"{name} ({count})" if count else name)
    return ", ".join(out)


def metric(key: str) -> str:
    return METRICS.get(key, key)


def pct(value, nd: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{nd}f}%".replace(".0%", "%")


def signed(value, nd: int = 1, unit: str = "") -> str:
    if value is None:
        return "—"
    return f"{value:+.{nd}f}{unit}".replace(".0", "", 1) if nd == 0 else f"{value:+.{nd}f}{unit}"


def plural_players(names) -> str:
    names = list(names or [])
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " ба " + names[-1]


def sample(rounds: int | None = None, maps: int | None = None, events: int | None = None) -> str:
    """Түүврийн хэмжээг нэг хэллэгээр. Хэмжээгүй дүгнэлт бол таамаг."""
    bits = []
    if maps:
        bits.append(f"{maps} газрын зураг")
    if rounds:
        bits.append(f"{rounds} раунд")
    if events:
        bits.append(f"{events} тохиолдол")
    return ", ".join(bits)


# ------------------------------------------------------ зөвлөмж хэлбэржүүлэх
def _plc(rows, limit=3) -> str:
    return places(rows, limit)


def instruction(item: dict) -> dict:
    """Бүтэцтэй зааврыг монгол өгүүлбэр болгоно.

    ``mine=True`` бол манай тоглогчид хандсан заавар, ``False`` бол эсрэг
    тоглогчийн эсрэг яаж тоглох тухай. Ижил өгөгдлөөс хоёр өөр өгүүлбэр гарна:
    "чи энд зогс" ба "түүнийг эндээс сал" гэдэг нэг тоо, хоёр үйлдэл.
    """
    kind, mine = item.get("kind"), item.get("mine")
    s = side(item.get("side", ""), short=True)
    m = game_map(item.get("map", "")) if item.get("map") else ""

    if kind == "signature_weapon":
        w = weapon(item["weapon"])
        share = f"{item['share'] * 100:.0f}%"
        if mine:
            return _row(
                "Зэвсэг",
                f"{s}: алалтынх нь {share} нь {w} "
                f"({item['kills']} kill, HS {item['hs_pct']}%). "
                "Эдийн засгийг энэ зэвсэгт тааруулж төлөвлө.",
                "weapon",
            )
        return _row(
            "Зэвсгээс салга",
            f"{s}: алалтынх нь {share} нь {w} "
            f"({item['kills']} kill, HS {item['hs_pct']}%). "
            + (
                "Эхний раундад дарамтал -- AWP-гүй бол тэр өөр хүн болно."
                if item["weapon"] == "awp"
                else "Тэр энэ зэвсгээр тухтай байх зайг өг."
            ),
            "weapon",
        )

    if kind == "opening_profile":
        k, d, wp = item["kills"], item["deaths"], item["win_pct"]
        rate = f"{item['rate'] * 100:.0f}%"
        if mine:
            if wp >= 55:
                return _row(
                    "Нээлт", f"Нээлтийн тулаанд {k}-{d} ({wp}%). Түүнд эхний холбоог өг.", "opening"
                )
            if wp <= 42:
                return _row(
                    "Нээлт",
                    f"Нээлтийн тулаанд {k}-{d} ({wp}%) -- "
                    f"раундынхаа {rate}-д эхний тулаан авдаг мөртлөө хожихгүй. "
                    "Түүнийг эхний холбооноос ав, эсвэл ганцааранг нь бүү явуул.",
                    "opening",
                )
            return _row("Нээлт", f"Нээлтийн тулаанд {k}-{d} ({wp}%).", "opening")
        if wp >= 55:
            return _row(
                "Эхний холбоо",
                f"Нээлтийн тулаанд {k}-{d} ({wp}%) хождог. "
                "Тэнцүү нөхцөлд бүү тулгар -- солилт бэлдээд ор.",
                "opening",
            )
        return _row(
            "Эхний холбоо",
            f"Нээлтийн тулаанд {k}-{d} ({wp}%) -- эхний холбоог түүн рүү чиглүүл.",
            "opening",
        )

    if kind == "utility_engine":
        if mine:
            return _row(
                "Гранат",
                f"{s}: раунд тутам {item['per_round']} гранат "
                f"({item['smokes']} утаа, {item['infernos']} молотов). "
                "Багийн гранатын гол эх сурвалж -- түүнийг эрт бүү алд.",
                "utility",
            )
        return _row(
            "Гранатын машин",
            f"{s}: раунд тутам {item['per_round']} гранат "
            f"({item['smokes']} утаа, {item['infernos']} молотов). "
            "Тэр үхвэл тэдний бүтэц унана -- эхний бай болгож болно.",
            "utility",
        )

    if kind == "flash_engine":
        if mine:
            return _row(
                "Флаш",
                f"{s}: раунд тутам {item['per_round']} флаш туслалцаа "
                f"({item['flashes']}). Түүний флаш дор орох хүн тодорхой байг.",
                "utility",
            )
        return _row(
            "Флаш",
            f"{s}: раунд тутам {item['per_round']} флаш туслалцаа "
            f"({item['flashes']}) -- тэдний нэвтрэлт түүний флашаас эхэлдэг. "
            "Флаш сонсогдвол дараа нь хэн орохыг таа.",
            "utility",
        )

    if kind == "kills_from":
        p = _plc(item["places"])
        if mine:
            return _row(
                f"{m} {s} байрлал",
                f"Алалтаа {p}-аас авдаг. Энэ бол түүний ажлын байр -- тэндээс нь бүү зөө.",
                "position",
            )
        return _row(
            f"{m} {s} өнцөг",
            f"Алалтаа {p}-аас авдаг. Эдгээр өнцгийг утаа/молотовоор хаа, эсвэл өөр талаас нь ор.",
            "position",
        )

    if kind == "dies_at":
        p = _plc(item["places"])
        if mine:
            return _row(
                f"{m} {s} сул тал",
                f"{p} дээр байнга үхдэг. Тэр байрлалыг өөрчил, эсвэл тэнд дэмжлэг тавь.",
                "leak",
            )
        return _row(
            f"{m} {s} завсар",
            f"{p} дээр байнга үхдэг. Тэр газрыг дарамтал -- тэнд тэр сул.",
            "leak",
        )

    if kind in ("duel_loses", "duel_wins"):
        opp, f, a, n = item["opponent"], item["for"], item["against"], item["net"]
        where = _plc(item.get("kills_from") or [], 2)
        if kind == "duel_wins":
            txt = f"{opp}-ийн эсрэг {f}-{a} ({n:+d}), {item['duels']} тулаан."
            if where:
                txt += f" Голдуу {where}-аас."
            return _row("Ашигтай дуэль" if mine else "Тэдний сул хос", txt, "duel_good")
        died = _plc(item.get("died_at") or [], 2)
        txt = f"{opp}-ийн эсрэг {f}-{a} ({n:+d}), {item['duels']} тулаан."
        if died:
            txt += f" Голдуу {died} дээр унадаг."
        txt += (
            " Энэ уулзалтаас зайлсхий -- тоо, гранатаар шийд."
            if mine
            else " Энэ хосыг давтахыг эрэлхийл."
        )
        return _row("Аюултай дуэль" if mine else "Ашигтай хос", txt, "duel_bad")

    if kind in ("drops_vs_them", "rises_vs_them"):
        label = METRICS.get(item["metric"], item["metric"])
        own, vs = item["own"], item["vs"]
        arrow = "унана" if kind == "drops_vs_them" else "өснө"
        who = "Манай" if mine else "Түүний"
        return _row(
            f"{label} {arrow}",
            f"{who} өөрийн тоглолтод {own}, энэ багийн эсрэг {vs} "
            f"({item['delta']:+g}), {item['rounds']} раунд дээр.",
            "delta_bad" if kind == "drops_vs_them" else "delta_good",
        )

    if kind == "bad_route":
        return _row(
            f"{m} {s} зам",
            f"{item['route']} -- {item['rounds']} раундад {item['kills']}-"
            f"{item['deaths']} ({item['net_per_round']:+g}/раунд). "
            "Энэ замыг өөрчил.",
            "route",
        )

    return _row(kind or "?", str(item), "other")


def _row(title: str, text: str, tone: str) -> dict:
    return {"title": title, "text": text, "tone": tone}


def instructions(items) -> list:
    return [instruction(i) for i in (items or [])]


# ------------------------------------------------- дүгнэлт хэлбэржүүлэх ----
def headline(v: dict, my_team: str, opponent: str) -> str:
    """Хамгийн эхэнд уншигдах өгүүлбэр, тоонуудаасаа салж чадахгүй."""
    f = v["facts"]
    if v.get("headline_kind") == "no_h2h":
        return (
            f"{opponent}-ийн эсрэг задлан шинжилсэн тоглолт байхгүй. Доорх "
            "хэсгүүд зөвхөн хоёр багийн өөрсдийн түвшинг харуулна."
        )
    r = f["record"]
    out = (
        f"{my_team} нь {opponent}-ийн эсрэг {r['played']} газрын зурагт "
        f"{r['won']}-{r['lost']} байна. "
    )
    if f.get("stale"):
        c = f["continuity"]["sides"]["mine"]
        out += (
            f"Гэхдээ энэ дүн хуучирсан: одоогийн {c['of']} тоглогчоос зөвхөн "
            f"{c['n']} нь тэр тоглолтуудад оролцсон"
        )
        if c["unseen"]:
            out += f", {plural_players(c['unseen'])} тэдэнтэй огт тоглож үзээгүй"
        out += ". Үүнийг таамаг биш, түүх гэж унш. "
    top = f.get("top_collapse")
    if f.get("worst_side") and top:
        out += (
            f"Алдагдал ерөнхий биш: манай {side(f['worst_side'], short=True)} "
            f"тал дээр гардаг. {metric(top['key'])} өөрсдийн тоглолтод "
            f"{top['own']}{top['unit']} байсан бол эдний эсрэг "
            f"{top['versus']}{top['unit']} болж {top['delta']:+g} унана -- "
            "эхлээд энэ тоог засах ёстой."
        )
    else:
        out += "Түүвэр цөөн тул аль хагаст алдагдаж байгааг хэлэх боломжгүй."
    return out


def point(p: dict) -> str:
    k = p["kind"]
    if k == "collapse":
        return (
            f"{metric(p['key'])}: өөрсдийн тоглолтод {p['own']}{p['unit']}, "
            f"эдний эсрэг {p['versus']}{p['unit']} ({p['delta']:+g}). "
            f"{METRIC_WHY.get(p['key'], '')}"
        )
    if k == "holds":
        return (
            f"{metric(p['key'])} эдний эсрэг өөрчлөгдөхгүй "
            f"({p['own']}{p['unit']} → {p['versus']}{p['unit']}) -- "
            "энэ бол тэдний буруу биш, бидний өөрсдийн засах зүйл."
        )
    if k == "linchpin_theirs":
        return (
            f"{p['name']} бол тэдний раундыг барьдаг хүн: тэр эхний 30 "
            f"секундэд үхвэл тэд {p['early_pct']}% "
            f"({p['early_won']}/{p['early_deaths']}) хождог, бусад раундад "
            f"{p['other_pct']}% -- {p['swing']:+.0f} нэгжийн зөрүү."
        )
    if k == "man_advantage_level":
        a, b = p["mine"], p["theirs"]
        return (
            f"Хүний давуу байдлыг бид тэднээс дутуугүй ашигладаг: "
            f"{a['won']}/{a['reached']} ({a['win_pct']}%) — тэд "
            f"{b['won']}/{b['reached']} ({b['win_pct']}%). Ялгаа нь давуу "
            "байдалд орсны дараа биш, түүнд хэр олон удаа ордогт байна."
        )
    return str(p)


def action(a: dict) -> dict:
    k = a["kind"]
    if k == "stale_record":
        return _act(
            "Сүүлийн үеийн формд илүү жин өг",
            continuity_note(a) + " Энэ дүнг одоо байхгүй бүрэлдэхүүн гаргасан тул тэдний "
            "зуршлыг харахад хэрэглэ, магадлал тооцоход биш.",
        )
    if k == "kill_first":
        return _act(
            f"Нээлтийг {a['name']}-д зарцуул",
            f"Тэр эхний 30 секундэд үхэхэд тэдний раунд хожих хувь "
            f"{a['other_pct']}%-аас {a['early_pct']}% болж унана "
            f"({a['early_deaths']} ийм раунд). Өөр ямар ч нээлт "
            "үүнээс үнэтэй биш -- хоёроор солиод ч ашигтай.",
        )
    if k == "protect":
        return _act(
            f"{a['name']}-г нээлтээс хамгаал",
            f"Тэр эрт үхэхэд манай раунд {a['other_pct']}%-аас "
            f"{a['early_pct']}% болж унана ({a['early_deaths']} раунд). "
            "Тэр эхний холбоо авах хүн байх ёсгүй, авах бол ганцаараа биш.",
        )
    if k == "play_numbers":
        return _act(
            "Тоон давуу байдал руу тогло, гоо сайхан руу биш",
            f"Хүн илүү үед бид {a['mine']['win_pct']}% хождог, тэд "
            f"{a['theirs']['win_pct']}%. Нээлтийг дангаар хожихоос "
            "солилт барих нь бидэнд илүү ашигтай.",
        )
    if k == "ban":
        maps = ", ".join(game_map(x["map"]) for x in a["maps"])
        why = " ".join(f"{game_map(x['map'])}: {x['why']}" for x in a["maps"])
        return _act(f"{maps} хориглох", why)
    if k == "pick":
        return _act(f"{game_map(a['map'])} сонгох", a["why"])
    if k == "no_pick":
        return _act(
            "Сонголтоор вето хожихыг бүү хүлээ",
            "Задлан шинжилсэн түүвэрт биднийг тэднээс 20 нэгжээр "
            "давуу харуулах газрын зураг алга. Вето-д тэдний сайн "
            "газрын зургийг хасаж хожих ёстой, өөрийнхийгөө олж биш.",
        )
    if k == "parse_more":
        maps = ", ".join(game_map(m) for m in a["maps"])
        return _act(
            f"{maps} дээр тэдний тоглолтыг задлан шинжил",
            "Бидэнд тэнд тоглолт бий, тэдэнд байхгүй тул боломж мөн үү, "
            "урхи мөн үү гэдгийг хэлэх аргагүй. Энэ жагсаалтын хамгийн "
            "хямд зүйл бөгөөд вето-г өөрчилнө.",
        )
    if k == "duel_hole":
        return _act(
            f"{a['name']}-ийн тулгардаг нөхцөлийг өөрчил",
            f"{a['name']} тэдний одоогийн таван тоглогчийн эсрэг "
            f"{a['for']}-{a['against']} ({a['net']}), {a['duels']} тулаан. "
            "Энэ бол формын уналт биш, түүнийг оруулж байгаа нөхцөл.",
        )
    if k == "role_gap":
        return _act(
            f"{a['mine']}-г {a['theirs']} рүү шууд бүү оруул",
            f"{side(a['side'], short=True)} дээр хоёулаа "
            f"{role(a['role']).lower()}. {a['theirs']} нь {a['theirs_fit']}, "
            f"{a['mine']} нь {a['mine_fit']} -- {a['delta']} зөрүүтэй. "
            "Энэ тулааныг тоо, гранатаар шийд, бай оноогоор биш.",
        )
    if k == "caveat":
        return _act(
            "Үүнийг эцсийн үнэн биш, шалгах чиглэл гэж үз",
            f"Манай {a['my_maps']}, тэдний {a['opponent_maps']} газрын "
            f"зураг, хоорондын {a['h2h_maps']} газрын зураг, "
            f"{a['pool_teams']} багийн сан дээр тулгуурлаж байна. "
            "Тэдний сүүлийн тоглолтуудыг нэмж задлан шинжлэх тусам "
            "энд байгаа тоо бүр хурцаддаг.",
        )
    return _act(k, str(a))


def _act(what: str, why: str) -> dict:
    return {"what": what, "why": why}


def points(items) -> list:
    return [point(p) for p in (items or [])]


def actions(items) -> list:
    return [action(a) for a in (items or [])]


# --------------------------------------- газрын зургийн төлөвлөгөө ---------
def plan_line(item: dict) -> str:
    k = item["kind"]
    if k == "their_site":
        txt = (
            f"Тэд bomb-ийхөө {item['share']:.0%}-ийг {item['site']} цэг рүү "
            f"тавьдаг ({item['plants']}/{item['total']}). {item['site']} цэгийн "
            "хамгаалалтад жин өгч, эргэлтийг богино бай."
        )
        conv = item.get("conversion")
        if conv and conv["win_pct"] <= 55:
            txt += (
                f" Гэхдээ {item['site']} дээр тавьснаа зөвхөн "
                f"{conv['win_pct']}% раунд болгодог ({conv['plants']} тавилт) -- "
                "bomb тавиулаад retake хийх нь бодит хувилбар."
            )
        return txt
    if k == "fast_tempo":
        return (
            f"Тэд {item['median']}с-д тавьдаг, энэ газрын зургийн дундаж "
            f"{item['map_median']}с. Ердийнхөөс хурдан -- гранатаа хожуу "
            "хадгалахгүй, нэвтрэлтийн эсрэг эрт зарцуул."
        )
    if k == "slow_tempo":
        return (
            f"Тэд {item['median']}с-д тавьдаг, дундаж нь {item['map_median']}с. "
            "Ердийнхөөс удаан хүлээдэг -- эрт мэдээлэл нь эрт дайралтаас "
            "үнэтэй, гранат сүүлийн 40 секунд хүртэл амьд байх ёстой."
        )
    if k == "rushes":
        return (
            f"{item['plants']} тавилтын {item['rushes']} нь 35 секундын дотор "
            "буусан -- rush тэдний номд бий. Нэг хүнийг гүнд үлдээ, хоёр "
            "эргэлдэгчийг зэрэг бүү зарцуул."
        )
    if k == "they_win_openings":
        return (
            f"Тэд энд нээлтийн {item['win_pct']}%-ийг хождог. Тэнцүү "
            "нөхцөлд эхний тулаан бүү ав -- солилт руу тогло."
        )
    if k == "weak_retake":
        return (
            f"Тэд энд {item['won']}/{item['faced']} ({item['win_pct']}%) л "
            "буцаан авдаг. Bomb тавих нь бараг раунд хожихтой тэнцүү -- "
            "тааруухан байрлалаас ч тавь."
        )
    if k == "strong_retake":
        return (
            f"Тэд энд {item['win_pct']}% буцаан авдаг "
            f"({item['won']}/{item['faced']}). Тавилт бол раунд биш -- "
            "тавилтын дараах хамгаалалтад гранат, хүн үлдээ."
        )
    if k == "their_ct_soft":
        return (
            f"Тэдний CT хагас энд {item['rounds']} раундад {item['win_pct']}% -- "
            "дайрахад илүү зөөлөн хагас."
        )
    if k == "their_ct_strong":
        return (
            f"Тэдний CT хагас энд {item['rounds']} раундад {item['win_pct']}% -- "
            "хүчтэй хагас; зоригтой биш, удаан тоглох нь дээр."
        )
    if k == "weak_pistols":
        return (
            f"Тэд энд гар бууны {item['won']}/{item['played']} л хождог. "
            "Жинхэнэ гар бууны бэлтгэл, дараагийн хоёр раундыг төлөвлө."
        )
    return str(item)


def caution_line(item: dict) -> str:
    k = item["kind"]
    if k == "few_plants":
        return (
            f"Тэдний зөвхөн {item['plants']} тавилт л задлагдсан -- цэгийн "
            "сонголт хэлэхэд хүрэлцэхгүй."
        )
    if k == "thin_own":
        return (
            f"Бидэнд энд ердөө {item['maps']} газрын зураг байгаа тул "
            "манай тоо бол хандлага биш, ганц үр дүн."
        )
    if k == "weak_own_ct":
        return (
            f"Манай CT хагас энд {item['win_pct']}% -- дээрх төлөвлөгөө "
            "бид барьж чадна гэж үзсэн, энэ нотолгоо дээр бол чадахгүй байна."
        )
    if k == "weak_own_retake":
        return (
            f"Бид энд {item['won']}/{item['faced']} ({item['win_pct']}%) "
            "буцаан авдаг. Тэднийг тавиулах ямар ч төлөвлөгөө бол раунд "
            "алдах төлөвлөгөө."
        )
    if k == "no_own_data":
        return (
            "Бидэнд энэ газрын зураг дээр задлан шинжилсэн тоглолт байхгүй. "
            "Дээрх бүхэн зөвхөн тэднээс уншсан."
        )
    if k == "no_their_data":
        return (
            "Тэдэнд энэ газрын зураг дээр задлан шинжилсэн тоглолт байхгүй "
            "тул тагнах зүйл алга -- энэ бол сул биш, харагдахгүй сонголт."
        )
    return str(item)


def plan_lines(items) -> list:
    return [plan_line(i) for i in (items or [])]


def caution_lines(items) -> list:
    return [caution_line(i) for i in (items or [])]


def continuity_note(c: dict) -> str:
    """Хоорондын дүнг гаргасан бүрэлдэхүүн одоо хэр үлдсэн бэ.

    Энэ өгүүлбэргүйгээр хуудасны хамгийн том тоо худал болно: дүн бол талбайд
    гарах багуудын тухай нотолгоо бөгөөд нэг талын ихэнх нь тэнд байгаагүй бол
    түүнийг таамаг болгож болохгүй.
    """
    sides = c.get("sides") or {}
    mine, theirs = sides.get("mine") or {}, sides.get("theirs") or {}
    if not mine or not theirs:
        # Сервисийн англи ``note``-ыг дамжуулахгүй: энэ давхрын ажил бол монгол
        # хэллэг бөгөөд дамжуулбал хуудсанд англи өгүүлбэр гарч ирнэ. Цорын нэг
        # тохиолдол нь хоорондын мап задлагдаагүй үе.
        return "Хоорондын задлан шинжилсэн мап байхгүй тул тодотгох дүн ч байхгүй."
    out = (
        f"Манай одоогийн {mine['of']} тоглогчоос {mine['n']}, тэдний "
        f"{theirs['of']}-аас {theirs['n']} нь хоорондын тоглолтуудад оролцсон."
    )
    bits = []
    if mine.get("unseen"):
        bits.append(
            f"{plural_players(mine['unseen'])} ({mine['team']}) тэдэнтэй огт тоглож үзээгүй"
        )
    if theirs.get("unseen"):
        bits.append(
            f"{plural_players(theirs['unseen'])} ({theirs['team']}) бидэнтэй тоглож үзээгүй"
        )
    if bits:
        out += " " + "; ".join(bits) + "."
    return out


# ----------------------------------------------- ажлын урсгалын хэллэг ------
# Analyze run-ийн лог. Дүрэм хэвээр: ``tasks.py`` тоо ба түлхүүр л дамжуулна,
# өгүүлбэр энд угсарна. Тул шатны нэр, "алгаслаа" гэдгийн шалтгаан, байтын
# хэлбэр -- бүгд нэг файлд, англи f-string арван модуль дундуур тарахгүй.

STAGES = {
    "queued": "Дараалалд",
    "resolving": "Багуудыг тодорхойлж байна",
    "fetching": "Demo татаж байна",
    "unpacking": "Архив задалж байна",
    "parsing": "Demo боловсруулж байна",
    "analysing": "Шинжилж байна",
    "rendering": "Зураг зурж байна",
    "done": "Дууслаа",
}

# Дулааны зургийн шүүлтүүр ба төлөвийн бичвэрүүд. `_heatmaps.html` хоёр хуудсанд
# хамтарсан тул үгсийг хуудас нь дамжуулна -- ажлын тайлан англиар, төлөвлөгөө
# монголоор. `drawing` доторх `%n` нь цэгийн тоогоор солигдоно.
HEATMAP_WORDS = {
    "map": "Мап",
    "team": "Баг",
    "player": "Тоглогч",
    "all_players": "Бүх тоглогч",
    "side": "Тал",
    "pick": "Харах хэсгээ сонгоно уу.",
    "nothing": "Энэ сонголтод зурах юм алга.",
    "drawing": "%n байрлал зурж байна…",
    "failed": "Үүнийг зурж чадсангүй.",
    "no_background": "мапын дэвсгэргүй",
    # Зөвхөн хоёр давхартай мап (Nuke, Vertigo, Train) сонгогдсон үед харагдана.
    # Толь биш жагсаалт: Django загварт түлхүүрээр толь уншиж чаддаггүй.
    "floor": "Давхар",
    "floors": [
        {"key": "all", "label": "Хоёул"},
        {"key": "upper", "label": "Дээд"},
        {"key": "lower", "label": "Доод"},
    ],
}

# Хөдөлгөөний торны үгс. Дулааны зурагтай ижил шүүлтүүр, өөр асуулт: тэнд
# хаана байсан бэ, энд хаагуур явсан бэ. `%n` нь мөшгисөн раундын тоо.
MOVEMENT_WORDS = dict(
    HEATMAP_WORDS,
    pick="Харах хэсгээ сонгоно уу.",
    nothing="Энэ сонголтод зурах зам алга.",
    drawing="%n раундын зам зурж байна…",
    # Хөдөлгөөнт үзүүлбэрийн товчлуурууд ба уншилт.
    play="▶ Тоглуулах",
    pause="❚❚ Түр зогсоох",
    replay="↻ Дахин",
    step="алхам",
    scrub="Явцын гулсуур",
)

# Хөдөлгөөний зураг ба хүснэгтүүдийн үг хэллэг. `movement.py` зөвхөн тоо ба
# түлхүүр буцаана; өгүүлбэрийг энд угсарна.
MOVEMENT = {
    "all_players": "бүх тоглогч",
    "title": "{who} — хаагуур явдаг вэ",
    "sides": {"ct": "CT тал", "t": "T тал", "all": "хоёр тал"},
    "subtitle": "{map} · {side} · {routes} зам · {traced} мөшгисөн раунд",
    "players_suffix": " · {n} тоглогч",
    # Хоёр давхартай мапын шүүлтүүр (Nuke, Vertigo, Train).
    "floor_suffix": " · {floor}",
    "floors": {"upper": "дээд давхар", "lower": "доод давхар"},
    # Замын тохироо
    "fit_title": "Зам тус бүр хэр таарч байна",
    "fit_note": (
        "Хувь = мөшгисөн раундын хэдэд нь энэ замаар явсан. «Бусад» "
        "багана нь яг ижил замаар явсан өөр тоглогчдын дүн (мөн хэдэн "
        "раунд дээр тулгуурласныг хаалтад бичив) — тухайн тоглогч өөрөө "
        "тэр тоонд ороогүй. Зөрүү нь эдгээрийн ялгаа: {good} ба дээш "
        "бол таарч байна, {bad} ба доош бол таарахгүй байна гэж үзнэ "
        "(сангийн стандарт хазайлт нэг нэгж)."
    ),
    "fit_thin": (
        "Энэ замаар өөр хэн ч хангалттай явж үзээгүй тул харьцуулах "
        "суурь алга; тоонууд нь өөрийнх нь дүн."
    ),
    "col_route": "Зам",
    "col_share": "Хувь",
    "col_rounds": "Раунд",
    "col_player": "Тоглогч",
    "col_kd": "K-D",
    "col_pool": "Бусад",
    "col_net": "Раунд тутам",
    "col_win": "Раунд авсан (бусад)",
    "col_delta": "Бусдаас зөрүү",
    "col_verdict": "Дүгнэлт",
    "suits": "таарч байна",
    "misfits": "таарахгүй байна",
    "even": "ялгаагүй",
    "unknown": "дата  багадсан",
    # Газар нутгийн хөдөлгөөн
    "places_title": "Аль хэсгээр их явдаг вэ, тэндээ юу болдог вэ",
    "places_note": (
        "Дайрсан раунд бүрээр тоолсон. K-D тухайн "
        "callout дотор бүртгэсэн — 10 дайралт тутамд харуулав."
    ),
    "col_place": "Хэсэг",
    "col_passes": "Дайралт",
    "col_kills_10": "Ал / 10",
    "col_deaths_10": "Үхэл / 10",
    "col_place_net": "Зөрүү / 10",
}

# Шатны тоолуурын нэрс. Checklist дээр "3 татсан, 2 алгассан" болж гарна.
COUNTS = {
    "downloaded": "татсан",
    "skipped": "алгассан",
    "missing": "demo байхгүй",
    "failed": "унасан",
    "matches": "матч",
    "archives": "архив",
    "maps": "мап",
    "demos": "demo",
    "parsed": "боловсруулсан",
    "rounds": "раунд",
    "images": "зураг",
    "teams": "баг",
}

# ``ingest_map``-ийн дэд алхмууд ба awpy-ийн уншилт. Хэрэглэгч 8 секунд юу болж
# байгааг харахгүй байхын тулд.
INGEST_STEPS = {
    "pack": "tick датаг багцалж байна",
    "stored": "хадгалсан tick датаг уншиж байна",
    "awpy": "awpy-аар demo уншиж байна",
    "roster": "бүрэлдэхүүн ба талуудыг бичиж байна",
    "rounds": "раундуудыг бичиж байна",
    "events": "kill, хохирол, bomb, гранатыг бичиж байна",
    "player_rounds": "тоглогч тус бүрийн раундыг бодож байна",
    "snapshots": "setup ба bomb тавих үеийн байрлалыг бичиж байна",
    "breakdown": "цэг, буу, гранатын тайланг угсарч байна",
    "routes": "явсан замуудыг гаргаж байна",
    "duels": "тулаануудыг хос хосоор нь тааруулж байна",
    "scores": "оноог тогтоож байна",
    "tickdata": "tick дата, replay, алхсан замыг өгөгдлийн санд бичиж байна",
    "player_match": "матчийн дүнг дахин бодож байна",
}

# ``build_report``-ийн секцүүд.
REPORT_STEPS = {
    "sample": "түүврийг цуглуулж байна",
    "profiles": "тоглогчдын дүр төрхийг бодож байна",
    "head_to_head": "хоорондын дүнг гаргаж байна",
    "roles": "үүрэг ба үүрэгт тохирохыг үнэлж байна",
    "maps": "газрын зургийн тактикийг гаргаж байна",
    "matchups": "хэн хэнийг барьж байгааг тааруулж байна",
    "splits": "энэ тоглолт ба бусад тоглолтыг харьцуулж байна",
    "breakdown": "тоглогч тус бүрийн задаргааг угсарч байна",
    "findings": "дүгнэлтүүдийг шүүж байна",
}


def stage(key: str) -> str:
    return STAGES.get(key, key or "")


def ingest_step(key: str) -> str:
    return INGEST_STEPS.get(key, key or "")


def report_step(key: str) -> str:
    return REPORT_STEPS.get(key, key or "")


def counts(values: dict) -> str:
    """{'downloaded': 3, 'skipped': 2} -> '3 татсан, 2 алгассан'."""
    bits = [f"{v} {COUNTS.get(k, k)}" for k, v in (values or {}).items() if v]
    return ", ".join(bits)


def mb(n: int | None) -> str:
    """Байтыг MB-ээр. Хүн 468 MB гэж уншдаг, 490733568 гэж уншдаггүй."""
    if not n:
        return "—"
    if n < 1_000_000:
        return f"{n / 1_000:.0f} KB"
    if n < 1_000_000_000:
        return f"{n / 1_000_000:.0f} MB"
    return f"{n / 1_000_000_000:.2f} GB"


def duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.0f}с"
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}м {rest:02d}с"


def speed(bytes_per_sec: float | None) -> str:
    if not bytes_per_sec:
        return "—"
    return f"{bytes_per_sec / 1_000_000:.1f} MB/с"


def match_line(m: dict) -> str:
    """Нэг матчийн танилт: хэн хэнтэй, ямар эвент, хэзээ, HLTV-ийн дугаар.

    Багийн нэрийг хэзээ ч орчуулахгүй -- клубын нэр бол нэр. Харин "ямар матч,
    ямар багийн эсрэг" гэдэг асуултын бүх хариу энэ нэг мөрөнд байна.
    """
    who = f"{m.get('team1') or '?'} {m.get('score') or 'vs'} {m.get('team2') or '?'}"
    bits = [who]
    if m.get("event"):
        bits.append(m["event"])
    if m.get("played_at"):
        bits.append(str(m["played_at"])[:10])
    if m.get("id"):
        bits.append(f"match {m['id']}")
    return " · ".join(bits)


# Аль цонхны матч болохыг нэг үгээр. Гурван цонх өөр өөр асуултад хариулдаг тул
# лог мөр аль нь болохыг хэлэх ёстой.
WINDOWS = {
    "h2h": "хоорондын",
    "mine": "манай",
    "theirs": "тэдний",
}


def window(key: str, my_team: str = "", opponent: str = "") -> str:
    if key == "h2h":
        return f"хоорондын тоглолт ({my_team} vs {opponent})"
    if key == "mine":
        return f"{my_team} — өөрийн тоглолтууд"
    if key == "theirs":
        return f"{opponent} — өөрийн тоглолтууд"
    return WINDOWS.get(key, key)


# --------------------------------- нэг тоглогчийн задаргаа (app.services.playerlab)
# Багийн тагнуулын тайлангаас ялгаатай нь: энд "бид"/"тэд" гэсэн хос тал байхгүй,
# зөвхөн нэг тоглогч, дасгалжуулагчаас түүнд хандсан нэг өнцөг. Тиймээс
# `instruction()`-ийн `mine` сэлгэлтийг давтахгүй, тусдаа функцээр угсарна.
_SIGNAL_LABELS = {
    "adr": "ADR",
    "kast_pct": "KAST",
    "kd_ratio": "K/D",
    "opening_win_pct": "нээлтийн тулаан",
}


def _top_signals(z: dict, n: int = 2) -> list:
    """Хамгийн их |z| утгатай хэдэн үзүүлэлтийг, тэмдгийн дагуу нь тайлбарлана."""
    rows = [(k, v) for k, v in (z or {}).items() if v is not None]
    rows.sort(key=lambda r: -abs(r[1]))
    return [
        f"{_SIGNAL_LABELS.get(k, k)} {'дээгүүр' if v >= 0 else 'доогуур'} (z{v:+.1f})"
        for k, v in rows[:n]
    ]


def player_instruction(item: dict) -> dict:
    """Нэг тоглогчийн тайлангийн нэг мөр бүтэцтэйгээс монгол өгүүлбэр болгоно."""
    kind = item.get("kind")
    m = game_map(item.get("map", "")) if item.get("map") else ""
    s = side(item.get("side", ""), short=True)

    if kind in ("map_strong", "map_weak"):
        bits = _top_signals(item.get("z") or {})
        why = f" — {', '.join(bits)}" if bits else ""
        head = "Давуу газар" if kind == "map_strong" else "Сул газар"
        return _row(
            f"{m} {s}",
            f"{head}: {item['rounds']} раунд, ADR {item['adr']}, "
            f"KAST {item['kast_pct']}%, K/D {item['kd_ratio']}{why}.",
            "good" if kind == "map_strong" else "bad",
        )

    if kind == "signature_weapon":
        w = weapon(item["weapon"])
        return _row(
            f"{s} гарын үсэг",
            f"Алалтынхаа {item['share'] * 100:.0f}% "
            f"{w}-аар авдаг ({item['kills']} kill, HS {item['hs_pct']}%). "
            "Эдийн засгаа энэ зэвсэгт тааруулж төлөвлө.",
            "weapon",
        )

    if kind == "weak_weapon":
        w = weapon(item["weapon"])
        return _row(
            f"{s} ажилладаггүй зэвсэг",
            f"{w}-аар {item['damage']} damage, {item['hits']} hit өгсөн ч "
            "нэг ч kill болгож чадаагүй. Тохиргоо, зайгаа шалга.",
            "weak",
        )

    if kind == "smoke_push":
        return _row(
            "Утаагаар нэвтэрдэг",
            f"{item['kills_thru_smoke']} удаа утаагаар харагдахгүй буудаж "
            "kill авсан — түрэлт, лайнап хоёулаа тохирсон байна.",
            "good",
        )

    if kind == "smoke_victim":
        return _row(
            "Утаанд өртдөг",
            f"{item['deaths_thru_smoke']} удаа өрсөлдөгчийн утаа дундуур "
            "буудсан сумаар унасан. Мэдээлэлгүй өнцөг барихаа болих, "
            "эсвэл өөрөө эхлээд гранатаар цэвэрлэ.",
            "weak",
        )

    if kind == "fire_cross":
        return _row(
            "Гал дундуур тулаан (ойролцоо тооцоо)",
            f"Идэвхтэй молотов/инсендиари ойролцоо {item['total']} тулаан "
            f"({item['kills']}-{item['deaths']}, {item['net']:+d}). "
            "Энэ тоо байрлалын ойролцоо тооцооноос гарсан тул хандлага гэж "
            "уншиж, яг тоо гэж бүү ойлго.",
            "good" if item["net"] >= 0 else "weak",
        )

    if kind == "clutch":
        sizes = ", ".join(
            f"{r['situation']} {r['won']}/{r['attempts']}" for r in item.get("by_size") or []
        )
        return _row(
            "Ганцаараа үлдэх (clutch)",
            f"Багийнхаа сүүлчийн амьд үлдсэн хүн байх {item['attempts']} "
            f"тохиолдлын {item['won']}-г ялсан ({item['rate']}%)"
            + (f": {sizes}." if sizes else "."),
            "clutch",
        )

    if kind == "no_contest":
        return _row(
            "Тэмцэлгүй унадаг",
            f"Үхсэн {item['deaths']}-ийнхаа {item['no_contest']} "
            f"({item['pct']}%) дээр алуулсан хүндээ хариу damage өгөөгүй "
            "— ердийн тоглогчийн хувьд энэ ойролцоогоор 66% байдаг тул "
            "энэ нь тэрнээс мэдэгдэхүйц дээгүүр гэсэн үг: харагдахаас "
            "өмнө буудуулж байна. Angle-аа мэдээлэлтэй нээ.",
            "weak",
        )

    if kind in ("route_suits", "route_misfits"):
        route_label = " → ".join(place(p) for p in (item.get("places") or []))
        fit = item["fit"]
        head = "Тохирсон зам" if kind == "route_suits" else "Тохироогүй зам"
        tone = "good" if kind == "route_suits" else "weak"
        return _row(
            f"{m} {s} — {head}",
            f"{route_label}: {item['rounds']} раунд {item['kills']}-"
            f"{item['deaths']} ({fit['net']:+.2f}/раунд), энэ замаар явдаг "
            f"{fit['pool_players']} өөр тоглогчийн дундаж "
            f"{fit['pool_net']:+.2f}/раунд — зөрүү {fit['delta']:+.2f}. "
            + (
                "Энэ зам түүнд тохирсон байна — байнга ашигла."
                if kind == "route_suits"
                else "Энэ зам түүнд тохирохгүй байна — өөр тоглогч эсвэл "
                "өөр чиглэлээр орох талаар бод."
            ),
            tone,
        )

    if kind == "aim_strong":
        return _row(
            "Мэргэн буудлага",
            f"Алалтынхаа {item['held_pct']}% дээр буудахаасаа 1 секундийн "
            f"өмнө нүхэлж аль хэдийн бай руугаа чиглэсэн байсан "
            f"({item['n']} kill дээр). Angle-аа урьдчилж барьж, тааж "
            "буудах чадвар сайн.",
            "good",
        )

    if kind == "defense_holds":
        return _row(
            "Барьсан өнцөгт ордог",
            f"Үхсэн тохиолдлынхоо зөвхөн {item['flick_pct']}%-д л "
            f"алуулсан хүн нь түүнийг олохын тулд эргэх шаардлагатай "
            f"болсон байна ({item['n']} үхэл дээр) — ихэнх тохиолдолд "
            "өрсөлдөгч аль хэдийн чиглэсэн байсан газар руу орж "
            "байна. Тэр өнцгийг мэдэхгүйгээр бүү ор, эсвэл гранатаар "
            "цэвэрлэ.",
            "weak",
        )

    if kind == "defense_clean":
        return _row(
            "Цэвэр алдагдал",
            f"Үхсэн тохиолдлынхоо {item['flick_pct']}%-д алуулсан хүн "
            f"нь түүнийг олохын тулд эргэх шаардлагатай болсон "
            f"байна ({item['n']} үхэл дээр) — барьсан өнцөгт бага "
            "ордог, ихэвчлэн тэнцүү тулаанд унадаг.",
            "good",
        )

    if kind in ("tempo_fast", "tempo_slow"):
        head = "Хурдан ордог" if kind == "tempo_fast" else "Удаан хүлээдэг"
        return _row(
            f"{head}: {item['opponent']}",
            f"{item['opponent']}-ийн эсрэг дундажаар {item['median_contact_sec']}с "
            f"дараа анхны холбоонд ордог ({item['rounds']} раунд, "
            f"раунд хожил {item['round_win_pct']}%).",
            "tempo",
        )

    if kind == "site":
        return _row(
            f"{s} {item['site']} цэг",
            f"{item['rounds']} раунд {item['site']} цэг рүү чиглэсэн үед "
            f"{item['kills']}-{item['deaths']}, ADR {item['adr']}, "
            f"раунд хожил {item['win_pct']}%.",
            "site",
        )

    if kind == "synergy":
        bits = []
        if item["trades_for_me"] or item["trades_by_me"]:
            bits.append(
                f"trade {item['trades_for_me']}/{item['trades_by_me']} "
                "(түүнээс над руу / надаас түүн рүү)"
            )
        if item["assists_for_me"] or item["assists_by_me"]:
            flash = (
                f", {item['flash_assists_for_me']} нь флашаар"
                if item["flash_assists_for_me"]
                else ""
            )
            bits.append(f"assist {item['assists_for_me']}/{item['assists_by_me']}{flash}")
        detail = "; ".join(bits) if bits else f"{item['total_interactions']} харилцан үйлдэл"
        together = f" ({item['rounds_together']} раунд хамт)" if item["rounds_together"] else ""
        return _row("Хамгийн сайн хамтрагч", f"{item['name']}{together} — {detail}.", "synergy")

    return _row(kind or "?", str(item), "other")


def player_instructions(items) -> list:
    return [player_instruction(i) for i in (items or [])]


# ------------------------------------------- нэг мап, тоглогч тус бүрийн дүн ---
# app.services.matchreport.player_map_report-ийн гаралт -- тоо, түлхүүр -- энд
# монгол өгүүлбэр болно. match_detail.html-ийн шинэ хэсэг үүнийг ашиглана.
def player_map_headline(stats: dict, team_avg: dict) -> str:
    """K-D, ADR, KAST -- нэг өгүүлбэрт багтсан тойм."""
    k, d, diff = stats["kills"], stats["deaths"], stats["kd_diff"]
    adr, kast, hs = stats["adr"], stats["kast_pct"], stats["hs_pct"]
    if diff >= 6:
        tone = "энэ мап дээр тодорхой давуу тоглосон"
    elif diff >= 1:
        tone = "эерэг тоглосон"
    elif diff >= -5:
        tone = "тэнцүү шахуу тоглосон"
    else:
        tone = "хүндрэлтэй мап байсан"
    out = f"{k}-{d} ({diff:+d}), {adr} ADR, KAST {kast}%"
    if hs:
        out += f", HS {hs}%"
    avg_adr = team_avg.get("adr")
    if avg_adr:
        out += f" (багийн дундаж {avg_adr} ADR)"
    return out + f" — {tone}."


def player_map_strength(item: dict) -> dict:
    kind = item["kind"]
    if kind == "high_adr":
        return _row(
            "Damage",
            f"Раунд тутамд {item['value']} damage хийж, багийн дундаж "
            f"{item['avg']}-аас өндөр гарсан.",
            "good",
        )
    if kind == "high_kast":
        return _row(
            "Нөлөө",
            f"Раундын {item['value']}%-д нөлөө үзүүлсэн (багийн дундаж {item['avg']}%).",
            "good",
        )
    if kind == "wins_openings":
        return _row(
            "Нээлт",
            f"Нээлтийн тулаанд {item['kills']}-{item['deaths']} "
            f"({item['win_pct']}%) хожсон — эхний холбоог түүнд даатгаж болно.",
            "good",
        )
    if kind == "multikill":
        return _row("Multikill", f"{item['rounds']} раундад ганцаараа 3+ kill авсан.", "good")
    if kind == "aim":
        return _row("Нарийвчлал", f"Алалтынхаа {item['hs_pct']}% нь толгойны цохилт.", "good")
    if kind == "weapon":
        w = weapon(item["weapon"])
        text = f"{w}-ээр {item['kills']} kill авсан"
        if item.get("hs_pct"):
            text += f" (HS {item['hs_pct']}%)"
        return _row("Зэвсэг", text + ".", "good")
    if kind == "position":
        p, s = place(item["place"]), side(item["side"], short=True)
        return _row(
            "Байрлал",
            f"{s} талд {p} дээр {item['kills']}-{item['deaths']} "
            f"({item['net']:+d}) — энэ цэг түүнд ажилладаг.",
            "good",
        )
    if kind == "duel":
        text = f"{item['opponent']}-г {item['kills_for']}-{item['kills_against']} тоогоор дийлдэг"
        if item.get("place"):
            text += f" (ихэвчлэн {place(item['place'])}-аас)"
        return _row("Ашигтай дуэль", text + ".", "good")
    if kind == "molotov":
        return _row(
            "Молотов",
            f"{item['infernos']} молотовоороо {item['fire_damage']} damage "
            f"хийсэн (дунджаар {item['per']}) — байнга хүн түлдэг.",
            "good",
        )
    if kind == "flash":
        return _row("Флаш", f"{item['flash_assists']} flash assist өгсэн.", "good")
    return _row(kind or "?", str(item), "good")


def player_map_weakness(item: dict) -> dict:
    kind = item["kind"]
    if kind == "low_adr":
        return _row(
            "Damage",
            f"Раунд тутамд {item['value']} damage хийсэн нь багийн дундаж "
            f"{item['avg']}-аас доогуур.",
            "bad",
        )
    if kind == "low_kast":
        return _row(
            "Нөлөө",
            f"Раундын зөвхөн {item['value']}%-д нөлөө үзүүлсэн "
            f"(багийн дундаж {item['avg']}%) — олон раунд дундуур өнгөрсөн.",
            "bad",
        )
    if kind == "negative_kd":
        return _row("K-D", f"{item['rounds']} раундад kill-death зөрүү {item['value']:+d}.", "bad")
    if kind == "loses_openings":
        return _row(
            "Нээлт",
            f"Нээлтийн тулаанд {item['kills']}-{item['deaths']} "
            f"({item['win_pct']}%) — түрүүлж оролцоод ялдаггүй.",
            "bad",
        )
    if kind == "untraded":
        return _row(
            "Trade",
            f"{item['deaths']} үхэлээсээ ердөө {item['pct']}% нь "
            "trade хийгдсэн — дэмжлэггүй газар ганцаараа үхдэг.",
            "bad",
        )
    if kind == "bad_weapon":
        w = weapon(item["weapon"])
        return _row(
            "Зэвсэг", f"{w}-ээр {item['damage']} damage хийсэн ч нэг ч kill аваагүй.", "bad"
        )
    if kind == "weak_position":
        p, s = place(item["place"]), side(item["side"], short=True)
        return _row(
            "Байрлал",
            f"{s} талд {p} дээр {item['kills']}-{item['deaths']} "
            f"({item['net']:+d}) — энэ цэг дээр байнга унадаг.",
            "bad",
        )
    if kind == "weak_duel":
        text = f"{item['opponent']}-д {item['kills_against']}-{item['kills_for']} тоогоор дийлддэг"
        if item.get("place"):
            text += f" (ихэвчлэн {place(item['place'])} дээр)"
        return _row("Аюултай дуэль", text + ".", "bad")
    if kind == "wasted_molotov":
        return _row("Молотов", f"{item['infernos']} молотов шидсэн ч хэнийг ч түлээгүй.", "bad")
    return _row(kind or "?", str(item), "bad")


# Weakness тус бүр яг нэг зөвлөмжтэй холбогдоно -- хоёр weakness нэг шалтгаанаас
# үүдэлтэй бол (жиш нь low_kast ба untraded хоёулаа дэмжлэггүй байдлыг заана)
# player_map_entry() давхардсан зөвлөмжийг шүүнэ.
_FOCUS = {
    "low_adr": "Дуэлд илүү идэвхтэй оролцож, damage-ын хувь нэмэгдүүлэхэд анхаар.",
    "low_kast": "Kill, assist, trade эсвэл survive — раунд бүрд дор хаяж нэгээр нь оролц.",
    "negative_kd": "Дуэл сонголтоо болгоомжтой болгож, дэмжлэгтэй орох цэгээс тоглох хэрэгтэй.",
    "loses_openings": "Ганцаараа эхний холбоо руу орохоос зайлсхий — мэдээлэл эсвэл "
    "гранат бэлдээд ор.",
    "untraded": "Нөхдөөсөө хол биш, trade хийж чадах зайд байрлаж тоглох хэрэгтэй.",
    "wasted_molotov": "Молотовоо мэдэгдэж буй байрлал эсвэл түгээмэл зам руу шид, "
    "хоосон газар бүү шид.",
}


def player_map_focus(item: dict) -> str | None:
    kind = item["kind"]
    if kind in _FOCUS:
        return _FOCUS[kind]
    if kind == "weak_position":
        p = place(item["place"])
        return (
            f"{p} дээр ганцаараа бүү зогс — өнцгөө өөрчлөх, эсвэл дэмжлэгтэй хамт ажиллах хэрэгтэй."
        )
    if kind == "weak_duel":
        return (
            f"{item['opponent']}-тэй ганцаараа тулгарахаас зайлсхий — "
            "тоо, гранатаар давуу тал үүсгэж ор."
        )
    if kind == "bad_weapon":
        w = weapon(item["weapon"])
        return (
            f"{w}-ийн оронд эдийн засгаа өөр зэвсэгт зарцуулах, "
            "эсвэл engagement-ийн зайг өөрчлөх хэрэгтэй."
        )
    return None


def player_map_side(side_entry: dict | None) -> dict | None:
    """One side's view (both/ct/t) of ``matchreport.player_map_report``."""
    if side_entry is None:
        return None
    weaknesses = side_entry.get("weaknesses") or []
    focus = []
    for item in weaknesses:
        note = player_map_focus(item)
        if note and note not in focus:
            focus.append(note)
    return {
        "headline": player_map_headline(side_entry["stats"], side_entry.get("team_avg") or {}),
        "strengths": [player_map_strength(i) for i in side_entry.get("strengths") or []],
        "weaknesses": [player_map_weakness(i) for i in weaknesses],
        "focus": focus,
    }


def player_map_entry(entry: dict) -> dict:
    """app.services.matchreport.player_map_report-ийн нэг мөрийг үзүүлбэр рүү хөрвүүлнэ."""
    sides = entry.get("sides") or {}
    return {
        "player_id": entry["player_id"],
        "name": entry["name"],
        "team": entry.get("team"),
        "sides": {key: player_map_side(sides.get(key)) for key in ("both", "ct", "t")},
    }


def player_map_entries(items) -> list:
    return [player_map_entry(i) for i in (items or [])]


# ------------------------------------------------------------------ Playbook --
# :mod:`app.services.playbook`-ийн хэв маяг бүрийг гурван хэсэгт буулгана:
# ``title`` (тэд юу хийдэг), ``detail`` (тоо), ``counter`` (бид юу хийх вэ).
# Цагийг тоглогчид дэлгэцэн дээрээ хардаг раундын цагаар (1:55 → 0:00) бичнэ.
# Callout ба тоглогчийн нэр англиар үлддэг тул тэдэнд нөхцөлийн дагавар
# залгахгүй: "руу", "үед", хаалт, ":" зэргээр өгүүлбэрээ бүтээнэ.
ROUND_SECONDS = 115
STRENGTH = {"weak": "сул", "medium": "дунд", "strong": "хүчтэй"}
GRENADE = {"smoke": "smoke", "inferno": "molotov"}
BUY = {"pistol": "pistol", "eco": "eco", "force": "force", "full": "full buy", "": "—"}
# Molotov ~7 с, smoke ~18 с шатдаг: тэр хугацаанд тэр замаар орохгүй.
GRENADE_SECONDS = {"smoke": 18, "inferno": 7}

_PB_STRENGTH = {"strong": 0, "medium": 1, "weak": 2}
# Дасгалжуулагч эхэлж харах ёстой нь: хаашаа явдаг, хаана цөөн, retake.
_PB_KIND = {
    "site": 0,
    "soft_site": 0,
    "stack": 1,
    "retake": 1,
    "rush": 1,
    "at_plant": 2,
    "set_play": 2,
    "forces": 2,
    "saves": 2,
    "after_pistol_loss": 2,
    "setup": 3,
    "opening": 3,
    "plant_time": 4,
    "spot": 4,
}


def clock(secs: float) -> str:
    """Freeze дууссанаас хойшхи секунд → раундын цаг ('1:35')."""
    left = max(0, round(ROUND_SECONDS - secs))
    return f"{left // 60}:{left % 60:02d}"


def lean_pattern(p: dict) -> str:
    return f"A {p.get('A', 0)} · төв {p.get('mid', 0)} · B {p.get('B', 0)}"


def _other_site(site: str) -> str:
    return "B" if site == "A" else "A"


def _rounds(e: dict) -> str:
    return f"{e['n']}/{e['of']} раундад"


def _grenade(g: dict) -> str:
    return f"{clock(g['at'])} {GRENADE.get(g['type'], g['type'])} → {place(g['place'])}"


def _pb(title: str, detail: str, counter: str, h: dict) -> dict:
    return {
        "kind": h["kind"],
        "title": title,
        "detail": detail,
        "counter": counter,
        "evidence": h.get("evidence"),
    }


def playbook_habit(h: dict, *, whose: str) -> dict:
    """Нэг хэв маяг. ``whose``: ``theirs`` (хариуг бид хийнэ) эсвэл ``mine`` (self-scout)."""
    k, side, e = h["kind"], h.get("side", ""), h.get("evidence") or {}
    ours = whose == "mine"
    at_setup = clock(20)
    if k == "spot":
        title = f"{h['player']} — {place(h['place'])}"
        detail = f"{at_setup} үед {h['player']} {_rounds(e)} энд байдаг."
        if ours:
            counter = "Тэд энэ байрлалыг урьдчилан гранатаар цохиж болно — заримдаа соль."
        elif side == "t":
            counter = (
                f"{at_setup} орчим тэр байрлал руу HE/molotov хая, эсвэл гарцыг нь AWP-аар барь."
            )
        else:
            counter = "Тэр байрлалыг гранатаар нээгээд ор, эсвэл түүнээс хол цэгийг довтол."
        return _pb(title, detail, counter, h)
    if k == "setup":
        pattern = lean_pattern(h["pattern"])
        detail = f"{at_setup} үеийн хуваарь, {_rounds(e)}."
        if side == "t":
            title = f"T default: {pattern}"
            counter = (
                "Default нь энэ — эхний 20 секундэд rotate бүү хий, мэдээлэл хүлээ."
                if not ours
                else "Default маань таагдахуйц — хувилбар нэм."
            )
        else:
            weak = min(("A", "B"), key=lambda s: h["pattern"].get(s, 0))
            title = f"CT setup: {pattern}"
            counter = (
                f"{weak} цэгт хүн цөөн — {weak} руу довтол."
                if not ours
                else "Setup маань таагдахуйц — заримдаа хуваариа өөрчил."
            )
        return _pb(title, detail, counter, h)
    if k == "stack":
        site, other = h["site"], _other_site(h["site"])
        detail = f"{at_setup} үед, {_rounds(e)}."
        if side == "t":
            title = f"{site} тал руу 3+ хүнээр төвлөрдөг"
            counter = (
                f"{at_setup} орчим {site} талд дуу гарвал rotate-ийг эрт эхлүүл; "
                f"{other} цэгийг нэг хүнээр барь."
            )
            if ours:
                counter = "Тэд үүнийг уншаад тэр тал руу stack хийж болно — default-аа хувилбарла."
        else:
            title = f"{site} цэгт 3+ хүнээр stack хийдэг"
            counter = f"{other} руу шууд ор, эсвэл {site} цэгт fake хийж stack-ийг нь хоосон барь."
            if ours:
                counter = f"Stack маань таагдвал тэд {other} руу шууд орно."
        return _pb(title, detail, counter, h)
    if k == "soft_site":
        site, avg = h["site"], h["avg"]
        title = f"{site} цэгийг цөөн хүнээр барьдаг"
        detail = f"{at_setup} үед дунджаар A цэгт {avg['A']}, B цэгт {avg['B']} хүн ({_rounds(e)})."
        counter = (
            f"{site} руу довтол — эсэргүүцэл хамгийн бага."
            if not ours
            else f"{site} цэг маань сул гэдгийг тэд мэдэж болно."
        )
        return _pb(title, detail, counter, h)
    if k == "site":
        site, other = h["site"], _other_site(h["site"])
        title = f"Bomb-ийг ихэвчлэн {site} цэгт тавьдаг"
        detail = f"Тавьсан {e['of']}-ийн {e['n']} нь {site} цэгт ({h['rounds']} T раундаас)."
        counter = (
            f"{site} цэгт жин өг, {other} цэгийг цөөн хүнээр барь; retake-ийг {site} руу "
            "урьдчилан төлөвлө."
            if not ours
            else f"{site} руу хэт олон ордог — {other} руу орохыг нэм."
        )
        return _pb(title, detail, counter, h)
    if k == "plant_time":
        median = h["median"]
        title = f"Bomb-ийг дунджаар {clock(median)} үед тавьдаг"
        detail = f"{e['n']} тавилтын медиан: freeze-ээс хойш {median:.0f} секунд."
        if ours:
            counter = "Тавих цаг маань тогтмол — заримдаа хурдан, заримдаа удаан тогло."
        elif median >= 70:
            counter = f"Хожуу довтолдог — гранатаа {clock(60)} хүртэл хадгал."
        elif median <= 45:
            counter = "Хурдан довтолдог — эхний 40 секундэд гранатаа зарцуулахад бэлэн бай."
        else:
            counter = "Хэвийн хэмнэл — эхний мэдээллээр rotate хий."
        return _pb(title, detail, counter, h)
    if k == "rush":
        where = ", ".join(f"{s} {n}" for s, n in sorted(h["sites"].items()) if s)
        title = "Rush хийдэг"
        detail = f"{e['n']} удаа 35 секундэд багтаан bomb тавьсан ({where})."
        counter = (
            "Эхний 35 секундэд цэг бүрт хүн үлдээ, rush-ийн зам руу гранатаа эрт хая."
            if not ours
            else "Rush-ийн цаг маань тогтмол — тэд эрт stack хийж магадгүй."
        )
        return _pb(title, detail, counter, h)
    if k == "set_play":
        planted = h.get("planted") or {}
        where = ", ".join(f"{s} {n}" for s, n in sorted(planted.items()))
        detail = (
            f"{_rounds(e)}, {h['won']}-ийг хожсон"
            + (f"; дараа нь тавьсан: {where}" if where else "")
            + "."
        )
        first, last = h["grenades"][0], h["grenades"][-1]
        target = h.get("target") or ""
        if ours:
            counter = "Гранатын дараалал маань давтагддаг — тэд эсрэг гранат бэлдэж болно."
        elif side == "t" and target:
            counter = (
                f"{clock(first['at'])} үед {GRENADE.get(first['type'], first['type'])} "
                f"{place(first['place'])} руу буувал {target} руу ирэх дохио — {target} руу "
                "эрт rotate хий."
            )
        elif side == "t":
            counter = "Default-ийн гранат — дараа нь хаашаа явах нь тогтворгүй, эрт rotate бүү хий."
        else:
            wait = round(last["at"] + GRENADE_SECONDS.get(last["type"], 7))
            counter = (
                f"{clock(wait)} хүртэл тэр замуудаар бүү ор — гранат нь шатаж дуустал "
                "хүлээ эсвэл өөр зам сонго."
            )
        title = "Set play: " + " · ".join(_grenade(g) for g in h["grenades"])
        return _pb(title, detail, counter, h)
    if k == "opening":
        won, n = h["won"], e["n"]
        title = f"Эхний тулаан — {place(h['place'])}"
        who = "бид" if ours else "тэд"
        detail = f"Раундын эхний kill {_rounds(e)} энд болдог; {who} {won}/{n}-ийг хождог."
        if ours:
            counter = "Эхний тулаан маань нэг газарт төвлөрдөг — тэд урьдчилан барьж болно."
        elif won / n >= 0.5:
            counter = "Энд эхний дуэлийг ганцаараа бүү ав — trade-тай тогло."
        else:
            counter = "Энд эхний дуэлийг ав — тэд энд ихэвчлэн унадаг."
        return _pb(title, detail, counter, h)
    if k == "retake":
        weak = h["pct"] <= 50
        title = f"Retake {'сул' if weak else 'хүчтэй'}: {h['pct']}%"
        if not h["won"]:
            detail = f"Bomb тавигдсан {h['faced']} раундаас нэгийг ч буцааж хожоогүй."
        else:
            only = " л" if weak else ""
            detail = f"Bomb тавигдсан {h['faced']} раундаас {h['won']}-ийг нь{only} буцааж хожсон."
        if ours:
            counter = "Тэд үүнийг мэдвэл bomb тавихыг л зорино."
        elif weak:
            counter = "Bomb тавих нь раундыг бараг шийднэ — тавиад post-plant тогло."
        else:
            counter = "Тавилт бол раунд биш — тавьсны дараа гранат, хүн үлдээ."
        return _pb(title, detail, counter, h)
    if k == "at_plant":
        site = h["site"]
        title = f"{site} цэгт bomb тавигдахад тэнд {h['on_site']} хүн"
        detail = f"Амьд {h['alive']} хүний дунджаар {h['on_site']} нь цэг дээр ({_rounds(e)})."
        counter = (
            f"{site} руу хурдан ор — rotate ирэхээс өмнө цэгийг ав."
            if not ours
            else f"{site} цэгийг хамгаалах хүн цөөн — тэд үүнийг ашиглаж болно."
        )
        return _pb(title, detail, counter, h)
    if k == "forces":
        title = "Мөнгө дутахад force хийдэг"
        detail = f"Eco/force раундын {e['n']}/{e['of']} нь force, {h['won']}-ийг хожсон."
        counter = (
            "Force раундад ойрын зайн тулаанаас зайлсхий: SMG/shotgun-аас зай барь, AWP-аа хамгаал."
        )
        return _pb(title, detail, counter, h)
    if k == "saves":
        title = "Мөнгө дутахад хэмнэдэг"
        detail = f"Eco/force раундын {e['n']}/{e['of']} нь eco."
        counter = "Eco-д нь stack/rush-д бэлэн бай, гэхдээ буугаа алдах эрсдэлгүй тогло."
        return _pb(title, detail, counter, h)
    if k == "after_pistol_loss":
        buy = h["buy"]
        title = f"Pistol алдсаны дараа {BUY.get(buy, buy)}"
        detail = f"Дараагийн раунд: {_rounds(e)}."
        counter = (
            "2-р раундад force-д бэлтгэ: armor авч, ойрын өнцгөөс зайлсхий."
            if buy == "force"
            else "2-р раундад тэд хэмнэнэ — мэдээлэл аваад цэгээ хадгал."
        )
        return _pb(title, detail, counter, h)
    return _pb(k, str({key: v for key, v in h.items() if key != "evidence"}), "", h)


def playbook_habits(items, *, whose: str = "theirs") -> list:
    def order(h):
        e = h.get("evidence") or {}
        kind = _PB_KIND.get(h["kind"], 5) + (
            2 if h["kind"] == "set_play" and not h.get("target") else 0
        )
        return (kind, _PB_STRENGTH.get(e.get("strength"), 3), -e.get("n", 0))

    return [playbook_habit(h, whose=whose) for h in sorted(items or [], key=order)]


def playbook_pistol(row: dict) -> dict:
    bits = [side(row["side"], short=True), "хожсон" if row["won"] else "хожигдсон"]
    if row.get("site"):
        bits.append(f"{row['site']} цэгт тавьсан")
    if row.get("pattern"):
        bits.append(f"setup {lean_pattern(row['pattern'])}")
    after = []
    if row.get("next_buy"):
        after.append(BUY.get(row["next_buy"], row["next_buy"]))
    if row.get("next_won") is not None:
        after.append("хожсон" if row["next_won"] else "хожигдсон")
    return {
        "ref": row["ref"],
        "h2h": row["h2h"],
        "text": " · ".join(bits),
        "next": ("дараагийн раунд: " + ", ".join(after)) if after else "",
    }


def playbook_player(p: dict) -> dict:
    tags, lines = [], []
    for side_key in ("ct", "t"):
        s = p["sides"].get(side_key)
        if not s:
            continue
        label = side(side_key, short=True)
        if s["awper"]:
            tags.append(f"AWP ({label})")
        attempts = s["opening_kills"] + s["opening_deaths"]
        if s["rounds"] and attempts / s["rounds"] >= 0.25:
            tags.append(f"entry ({label})")
        spot = s.get("spot")
        where = f"{place(spot['place'])} {spot['n']}/{spot['of']}" if spot else "—"
        lines.append(
            f"{label}: {where} · нээлт {s['opening_kills']}–{s['opening_deaths']} "
            f"· {s['rounds']} раунд"
        )
    duels = [f"{d['player']} {d['deaths']}–{d['kills']}" for d in p.get("duels", [])[:3]]
    return {
        "player": p["player"],
        "tags": tags,
        "lines": lines,
        "duels": ("h2h-д манайх (хожсон–алдсан): " + ", ".join(duels)) if duels else "",
    }


# ----------------------------------------------------------------- Assistant --
# Туслах (app.services.assistant): хэрэгсэл ажиллаж байх үеийн төлөв, тогтмол хариунууд.
ASSISTANT_TOOL = {
    "list_teams": "Баг хайж байна",
    "team_overview": "Багийн үзүүлэлтийг уншиж байна",
    "map_strategy": "Мапын стратеги уншиж байна",
    "role_report": "Тоглогчдын үүргийг уншиж байна",
    "scouting_report": "Скаутын тайлан гаргаж байна",
    "gameplan_section": "Game Plan-ыг уншиж байна",
}
ASSISTANT_NOT_CONFIGURED = (
    "Туслах энэ сервер дээр тохируулагдаагүй байна (CLAUDE_API_KEY алга). Админд хандана уу."
)
ASSISTANT_TOO_MANY_LOOKUPS = (
    "Энэ асуулт нэг удаад зөвшөөрөгдсөнөөс олон хайлт шаардлаа. "
    "Нэг баг эсвэл нэг мапаар нарийсгаад дахин асууна уу."
)
ASSISTANT_NOTHING = "Энэ асуултад хэлэх зүйл олдсонгүй."
ASSISTANT_REFUSED = "Энэ асуултад хариулж чадахгүй нь. Өөрөөр асууж үзнэ үү."
ASSISTANT_FAILED = "Туслах алдаа гаргалаа. Дахин оролдоно уу."


def assistant_status(tool: str, names: list[str], extra: str = "") -> str:
    """Хэрэгсэл ажиллаж байх үеийн нэг мөр: «Мапын стратеги уншиж байна — Vitality, MOUZ…»."""
    label = ASSISTANT_TOOL.get(tool, tool)
    bits = ", ".join([*names, *([extra] if extra else [])])
    return f"{label} — {bits}…" if bits else f"{label}…"
