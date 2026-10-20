"""Монгол хэлний үг хэллэгийн давхарга.

Шинжилгээний сервисүүд **тоо ба түлхүүр** буцаадаг; хүнд харагдах өгүүлбэрийг
энд угсарна. Ингэснээр монгол текст нэг файлд төвлөрч, шинжилгээний логик
хэлнээс хамааралгүй хэвээр үлдэнэ -- эсрэг тохиолдолд орчуулга нь арван модуль
дундуур тарж, аль нэгийг нь засахад нөгөө нь англиар үлддэг.

Дүрэм: энэ модуль ORM-д хандахгүй, тоо бодохгүй. Зөвхөн хэлбэржүүлнэ.

Flash-д өртсөн тоглогч «цайрсан», бусдыг өртүүлсэн нь «цайруулсан»; «сохор»,
«сохорсон», «сохорлосон» гэж бичихгүй. Багийнхаа тоглогчийг «багийн гишүүн» гэнэ,
«нөхөр» гэж бичихгүй.

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
    "declared": "Staff зарласан",
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


def demo_maps(entries: list[tuple[str, int]]) -> str:
    """An archive's maps, ``(map, part)`` each, a Map in Demo parts named once:
    "Dust II, Nuke (2 хэсэг)"."""
    order: list[str] = []
    parts: dict[str, int] = {}
    for name, part in entries:
        if name not in parts:
            order.append(name)
            parts[name] = 0
        parts[name] += 1 if part else 0
    return ", ".join(
        f"{game_map(name)} ({parts[name]} хэсэг)" if parts[name] else game_map(name)
        for name in order
    )


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

# Shown while the worker measures the Pool again after a Match (pool_cache).
POOL_WARMING = "Game Plan-д зориулж Pool-ийн үзүүлэлтийг шинэчилж байна"

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
    "untraded": "Багийн гишүүдээсээ хол биш, trade хийж чадах зайд байрлаж тоглох хэрэгтэй.",
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
        "review": playbook_review(h.get("review")),
        "evidence": h.get("evidence"),
    }


def playbook_review(note: dict | None) -> str:
    """Review-ээс habit мөрөнд нэмэх нэг өгүүлбэр (тухайн тоглогч эсвэл байрлал)."""
    if not note:
        return ""
    good = _ranked([(REVIEW_CODE.get(c, c), n) for c, n in note.get("good") or []])
    bad = _ranked([(REVIEW_CODE.get(c, c), n) for c, n in note.get("bad") or []])
    bits = []
    if note["kind"] == "player":
        bits.append(f"Swing {review_swing(note['swing'])}/раунд ({note['rounds']} раунд)")
    if good:
        bits.append(f"сайн нь: {good}")
    if bad:
        bits.append(f"алдаа нь: {bad}")
    where = "" if note["kind"] == "player" else f" {place(note['place'])}"
    scope = ", бүх Map-аас" if note.get("scope") == "all_maps" else ""
    return f"Review{where}{scope}: " + "; ".join(bits) + "."


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
        title = (
            f"Bomb-ийг {site} цэгт тавих хандлагатай"
            if h.get("lean")
            else f"Bomb-ийг ихэвчлэн {site} цэгт тавьдаг"
        )
        detail = f"Тавьсан {e['of']}-ийн {e['n']} нь {site} цэгт ({h['rounds']} T раундаас)."
        if h.get("pool_pct") is not None:
            detail += f" Энэ map дээр бусад баг {site} цэгт {h['pool_pct']}% тавьдаг."
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
        weak = h["weak"] if "weak" in h else h["pct"] <= 50
        title = (
            f"Retake {'сул' if weak else 'хүчтэй'} байх хандлагатай: {h['pct']}%"
            if h.get("lean")
            else f"Retake {'сул' if weak else 'хүчтэй'}: {h['pct']}%"
        )
        if not h["won"]:
            detail = f"Bomb тавигдсан {h['faced']} раундаас нэгийг ч буцааж хожоогүй."
        else:
            only = " л" if weak else ""
            detail = f"Bomb тавигдсан {h['faced']} раундаас {h['won']}-ийг нь{only} буцааж хожсон."
        if h.get("pool_pct") is not None:
            detail += f" Энэ map дээр бусад баг дунджаар {h['pool_pct']}% буцааж хождог."
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
    "match_review": "Тоглолтын дүн шинжилгээг уншиж байна",
    "match_summary": "Тоглолтын товч дүгнэлтийг уншиж байна",
}
ASSISTANT_LIMIT = (
    "Өнөөдрийн Туслахын хязгаарт хүрлээ. Маргааш дахин асууна уу, эсвэл Staff-аас хязгаарыг "
    "нэмүүлнэ үү."
)
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


# ------------------------------------------------------------------ Review --
# Тоглолтын дүн шинжилгээ (CONTEXT.md: Review). Finding бүрийн баримтаас
# (app/services/review.py) гарчиг ба тайлбарыг угсарна. ``who(sid)`` тоглогчийн
# нэрийг өгнө.

REVIEW_KIND = {
    "key_play": "Шийдвэрлэсэн үйлдэл",
    "mistake": "Алдаа",
    "missed_chance": "Алдсан боломж",
    "utility": "Utility-ийн нөлөө",
}

REVIEW_CODE = {
    "entry": "Entry",
    "big_frag": "Үнэ цэнтэй frag",
    "multikill": "Multi-kill",
    "clutch": "Clutch",
    "plant": "Plant",
    "defuse": "Defuse",
    "retake": "Retake",
    "untraded": "Trade-гүй ганцаардал",
    "died_in_advantage": "Давуу байдалд үхсэн",
    "team_flashed_death": "Багийн flash-д үхсэн",
    "no_gun_in_hand": "Буугаа бариагүй",
    "unused_utility": "Utility үлдээсэн",
    "lost_weapon_save": "Зэвсэг хадгалаагүй",
    "bomb_lost": "Бөмбөг алдсан",
    "awp_miss": "AWP алдсан",
    "moving_shots": "Гүйж буудсан",
    "crosshair": "Crosshair placement",
    "unscoped_awp": "Scope-гүй AWP",
    "time_out": "Хугацаа алдсан",
    "kitless": "Kit-гүй retake",
    "no_trade": "Trade хийгээгүй",
    "unfinished": "Дуусгаагүй дайсан",
    "blind_unpunished": "Цайрсан дайсныг ашиглаагүй",
    "advantage_lost": "Давуу байдлаа алдсан",
    "defuse_chance": "Defuse хийх боломж",
    "saw_no_shot": "Харсан ч буудаагүй",
    "saw_first_lost": "Түрүүлж харсан ч дуэлиа алдсан",
    "flash_kill": "Flash → kill",
    "nade_damage_kill": "Граната → kill",
    "fire_delay": "Molotov саатуулсан",
    "team_flash": "Багаа цайруулсан",
    "empty_utility": "Хоосон flash",
}

REVIEW_REASON = {
    "ct_killed": "CT-г бүгдийг нь хөнөөв",
    "t_killed": "T-г бүгдийг нь хөнөөв",
    "bomb_exploded": "бөмбөг дэлбэрэв",
    "bomb_defused": "бөмбөгийг defuse хийв",
    "time_ran_out": "хугацаа дуусав",
}

_REVIEW_WEAPONS = {
    "m4a1": "M4A4",
    "m4a1_silencer": "M4A1-S",
    "usp_silencer": "USP-S",
    "hkp2000": "P2000",
    "knife": "хутга",
    "inferno": "молотов",
    "molotov": "молотов",
    "incgrenade": "incendiary",
    "planted_c4": "бөмбөг",
}

_NADES = {
    "Flashbang": "flash",
    "Smoke Grenade": "smoke",
    "High Explosive Grenade": "HE",
    "Molotov": "molotov",
    "Incendiary Grenade": "incendiary",
    "Decoy Grenade": "decoy",
}


def review_weapon(key: str) -> str:
    key = (key or "").strip().lower()
    if key.startswith("knife") or "bayonet" in key or "karambit" in key:
        return "хутга"
    return _REVIEW_WEAPONS.get(key) or WEAPONS.get(key) or key.upper() or "?"


def review_swing(value: float | None) -> str:
    """Swing-ийг хувиар: 0.274 → '+27%'."""
    if value is None:
        return "—"
    points = round(value * 100)
    return f"+{points}%" if points > 0 else (f"−{abs(points)}%" if points < 0 else "0%")


def review_pct(value: float | None) -> str:
    return "—" if value is None else f"{round(value * 100)}%"


def _metres(units) -> str:
    """Тоглоомын нэгжийг метрээр (1 нэгж ≈ 1 инч): 520 → '~13 м'."""
    return f"~{max(1, round((units or 0) * 0.0254))} м"


def _secs(value) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".") + "с"


def _kill_how(f: dict) -> str:
    """'AK-47 буугаар, headshot, утаан дундуур' гэх мэт."""
    bits = [f"{review_weapon(f.get('weapon'))} буугаар"]
    if f.get("headshot"):
        bits.append("headshot")
    if f.get("thrusmoke"):
        bits.append("утаан дундуур")
    if f.get("wallbang"):
        bits.append("хана нэвт")
    if f.get("noscope"):
        bits.append("no-scope")
    return ", ".join(bits)


def _at(spot: str) -> str:
    return f" ({spot})" if spot else ""


def review_finding(finding: dict, who) -> dict:
    """Нэг Finding-ийн ``{title, text}``."""
    code, f, sids = finding["code"], finding.get("facts") or {}, finding.get("sids") or []
    main = who(sids[0]) if sids else ""
    swing = review_swing(finding.get("swing"))
    w0, w1 = review_pct(f.get("wp_before")), review_pct(f.get("wp_after"))
    alive = f.get("alive") or [0, 0]
    title, text = main, ""

    if code == "entry":
        title = f"{main} — entry{_at(f.get('spot'))}"
        text = (
            f"Раундын эхний frag: {main} {who(f.get('victim'))}-г{_at(f.get('victim_spot'))} "
            f"{_kill_how(f)} унагааж, багийнхаа хожих магадлалыг {w0} → {w1} болгов."
        )
        if f.get("flasher"):
            text += f" Flash-ийг {who(f['flasher'])} өгсөн."
    elif code == "big_frag":
        title = f"{main} — үнэ цэнтэй frag{_at(f.get('spot'))}"
        text = (
            f"{alive[0]}v{alive[1]} үед {main} {who(f.get('victim'))}-г{_at(f.get('victim_spot'))} "
            f"{_kill_how(f)} авав: багийн хожих магадлал {w0} → {w1}."
        )
        if f.get("flasher"):
            text += f" Flash-ийг {who(f['flasher'])} өгсөн."
    elif code == "multikill":
        victims = plural_players([who(s) for s in f.get("victims") or []])
        title = f"{main} — {f.get('kills')}K"
        text = (
            f"{main} энэ раундад {_secs(f.get('seconds', 0))} дотор {f.get('kills')} frag авав "
            f"({f.get('headshots', 0)} нь headshot): {victims}. Нийт Swing {swing}."
        )
    elif code == "clutch":
        title = f"{main} — 1v{f.get('vs')} clutch"
        did = f"{f.get('kills')} frag авч" if f.get("kills") else "хэнийг ч алалгүй"
        defused = ", бөмбөгийг defuse хийж" if f.get("defused") else ""
        text = (
            f"Багаасаа ганцаараа үлдээд 1v{f.get('vs')} нөхцөлд {did}{defused} раундыг авав. "
            f"Swing {swing}."
        )
    elif code == "plant":
        title = f"{main} — {f.get('site') or ''} цэгт plant".replace("  ", " ")
        text = (
            f"{f.get('ts')} T, {f.get('cts')} CT амьд байхад, раундын цагт "
            f"{_secs(f.get('clock', 0))} үлдсэн үед бөмбөг тавив. Swing {swing}."
        )
    elif code == "defuse":
        title = f"{main} — defuse"
        kit = "kit-тэй" if f.get("kit") else "kit-гүй"
        ts = f"{f.get('ts')} T амьд байхад " if f.get("ts") else ""
        text = (
            f"{ts}{kit} defuse хийж раундыг авав; бөмбөг дэлбэрэхэд {_secs(f.get('spare', 0))} "
            f"үлдсэн байв. Swing {swing}."
        )
    elif code == "retake":
        title = f"{main} — retake"
        text = (
            f"{f.get('site') or ''} цэгт {f.get('cts')}v{f.get('ts')} retake-д "
            f"{f.get('kills')} frag авч гол хувь нэмрийг оруулав. Swing {swing}."
        )

    elif code == "untraded":
        title = f"{main} — trade-гүй ганцаардал{_at(f.get('spot'))}"
        near = (
            f"хамгийн ойр багийн гишүүн нь {_metres(f['nearest'])} зайтай"
            if f.get("nearest")
            else "ойр багийн гишүүн байгаагүй"
        )
        text = (
            f"{main} {alive[0]}v{alive[1]} үед ганцаараа {who(f.get('killer'))}-д унав; {near} "
            f"байсан тул trade боломжгүй. Багийн хожих магадлал {swing}."
        )
    elif code == "died_in_advantage":
        title = f"{main} — давуу байдалд үхсэн"
        text = (
            f"Баг нь {alive[0]}v{alive[1]} давуу байхад {main}{_at(f.get('spot'))} "
            f"{who(f.get('killer'))}-д унаж, trade хийлгэсэнгүй; раунд алдагдав. Swing {swing}."
        )
    elif code == "team_flashed_death":
        victim = who(f.get("victim"))
        title = f"{main}-ийн flash {victim}-г үхүүлэв"
        text = (
            f"{main}-ийн шидсэн flash багийн хүн {victim}-г {_secs(f.get('seconds', 0))} цайруулж, "
            f"тэр цайрсан байхдаа {who(f.get('killer'))}-д унав. Swing {swing}."
        )
    elif code == "no_gun_in_hand":
        thing = "хутга" if f.get("held_kind") == "knife" else _NADES.get(f.get("held"), "граната")
        put = (
            f"{f['gun']}-аа {_secs(f.get('seconds', 0))}-ийн өмнө хураагаад"
            if f.get("gun")
            else "раунд эхэлснээс хойш буугаа гаргалгүй"
        )
        title = f"{main} — буугаа бариагүй баригдав"
        text = (
            f"{main} {put} гартаа {thing} барьсаар{_at(f.get('spot'))} "
            f"{who(f.get('killer'))}-тай дуэльд орж унав ({alive[0]}v{alive[1]}) — дайсантай "
            f"таарч болох газар буугаа гаргаж яв. Swing {swing}."
        )
    elif code == "unused_utility":
        nades = ", ".join(_NADES.get(n, n) for n in f.get("nades") or [])
        title = f"{main} — utility-гаа ашиглаагүй"
        text = (
            f"{main} гартаа {nades} байсаар{_at(f.get('spot'))} {who(f.get('killer'))}-д унав; "
            f"раунд алдагдсан. Swing {swing}."
        )
    elif code == "lost_weapon_save":
        gun = f.get("gun") or "буу"
        title = f"{main} — {gun}-аа хадгалаагүй"
        if f.get("post"):
            text = (
                f"Раунд дууссаны дараа {main} {gun}-тай{_at(f.get('spot'))} "
                f"{who(f.get('killer'))}-д олдож, буугаа дараагийн раундад алдав."
            )
        else:
            text = (
                f"Багийн хожих магадлал {review_pct(f.get('team_wp'))} ({alive[0]}v{alive[1]}) "
                f"болсон үед хадгалахын оронд тулалдаж {gun}-аа алдав."
            )
    elif code == "bomb_lost":
        title = f"{main} — бөмбөгийг ганцаараа алдав"
        text = (
            f"Бөмбөгтэй{_at(f.get('spot'))} ганцаараа {who(f.get('killer'))}-д унаж, "
            f"бөмбөг тавигдсангүй. Swing {swing}."
        )
    elif code == "awp_miss":
        title = f"{main} — AWP-ийн сум алдав"
        text = (
            f"AWP-аар буудаж оносонгүй, {_secs(f.get('after', 0))}-ийн дараа "
            f"{who(f.get('killer'))}-д унав{_at(f.get('spot'))}. Swing {swing}."
        )
    elif code == "moving_shots":
        title = f"{main} — гүйж буудсан"
        text = (
            f"{who(f.get('killer'))}-тай дуэлд буудсан {f.get('shots')} сумны {f.get('moving')} нь "
            f"хөдөлж байхад гарсан (дунджаар зэвсгийн дээд хурдны {f.get('speed')}%; 40%-иас дээш "
            f"бол сум тархана) — counter-strafe хийгээгүй. Swing {swing}."
        )
    elif code == "crosshair":
        title = f"{main} — crosshair placement"
        text = (
            f"{who(f.get('killer'))} анх харагдах үед {main}-ийн цэнз түүнээс "
            f"{f.get('degrees')}° зөрүүтэй байв; {_secs(f.get('reaction', 0))} дотор унав. "
            f"Swing {swing}."
        )
    elif code == "unscoped_awp":
        title = f"{main} — scope-гүй AWP"
        text = (
            f"AWP-тай боловч scope хийгээгүй байхдаа {who(f.get('killer'))}-тай дуэлд орж "
            f"унав{_at(f.get('spot'))}. Swing {swing}."
        )
    elif code == "time_out":
        title = "T хугацаа алдав"
        text = (
            f"{f.get('ts')} T амьд байсан хэдий ч ({f.get('cts')} CT-тэй) бөмбөг тавилгүй "
            "хугацаа дуусав."
        )
    elif code == "kitless":
        title = "Kit-гүй retake"
        text = (
            f"Сүүлийн T унахад бөмбөг дэлбэрэхэд {_secs(f.get('left', 0))} үлдсэн байв: kit-тэй "
            f"бол defuse амжих байсан (замд {_secs(f.get('travel', 0))}), kit-гүй 10с хүрэлцсэнгүй."
        )

    elif code == "no_trade":
        saw = " алагчийг харсан ч" if f.get("saw") else ""
        title = f"{main} — trade хийгээгүй"
        text = (
            f"{who(f.get('victim'))} {who(f.get('killer'))}-д{_at(f.get('killer_spot'))} унахад "
            f"{main} алагчаас {_metres(f.get('distance'))} зайд байсан,{saw} 5 секундэд trade "
            f"хийсэнгүй. Багийн хожих магадлал {swing}."
        )
    elif code == "unfinished":
        enemy = who(f.get("enemy"))
        title = f"{main} — {enemy}-г дуусгаагүй"
        after = f"{f.get('kills_after')} хүнийг алав" if f.get("kills_after") else "амьд үлдэв"
        won = ", баг нь раундыг авав" if f.get("enemy_won") else ""
        text = (
            f"{main} {enemy}-д {f.get('dealt')} damage өгч {f.get('hp')} HP үлдээсэн; "
            f"{enemy} амьд үлдээд {after}{won}. Swing {swing}."
        )
    elif code == "blind_unpunished":
        enemies = ", ".join(
            f"{who(e['sid'])} ({_secs(e['seconds'])})" for e in f.get("enemies") or []
        )
        title = f"{main} — цайрсан дайсныг ашиглаагүй"
        saw = ", түүнийг харсан" if f.get("saw") else ""
        text = (
            f"{who(f.get('thrower'))}-ийн flash {enemies}-г{_at(f.get('spot'))} цайруулсан; "
            f"{main} {_metres(f.get('distance'))} зайд байсан{saw} ч хэн нь ч алсангүй."
        )
    elif code == "advantage_lost":
        men = f.get("men") or [0, 0]
        deaths = ", ".join(
            f"{who(d['sid'])} ({review_swing(d['swing'])})" for d in f.get("deaths") or []
        )
        title = f"{side(f.get('side', ''), short=True)} — давуу байдлаа алдав"
        text = (
            f"Раундыг {review_pct(f.get('peak'))} магадлалтай ({men[0]}v{men[1]}) тэргүүлж байсан "
            f"ч алдав."
        )
        if deaths:
            text += f" Үүнээс хойш унасан: {deaths}."
    elif code == "defuse_chance":
        kit = " (kit-тэй)" if f.get("kit") else ""
        title = f"{main} — defuse хийх боломж"
        text = (
            f"Сүүлийн T унахад бөмбөг дэлбэрэхэд {_secs(f.get('left', 0))} үлдсэн байсан, {main}-д "
            f"очиж defuse хийхэд {_secs(f.get('need', 0))}{kit} хангалттай байв — гэвч defuse "
            "хийгдсэнгүй."
        )
    elif code == "saw_no_shot":
        enemy = who(f.get("enemy"))
        then = (
            "түүнийг алав"
            if f.get("self_killed")
            else f"багийн гишүүн {who(f.get('victim'))}-г алав"
        )
        title = f"{main} — {enemy}-г харсан ч буудаагүй"
        text = (
            f"{main}{_at(f.get('spot'))} {enemy}-г{_at(f.get('enemy_spot'))} "
            f"{_secs(f.get('seconds', 0))} харсан ч нэг ч сум буудсангүй; удалгүй {enemy} {then}. "
            f"Swing {swing}."
        )
    elif code == "saw_first_lost":
        enemy = who(f.get("enemy"))
        title = f"{main} — түрүүлж харсан ч дуэлиа алдав"
        text = (
            f"{main} {enemy}-г {_secs(f.get('lead', 0))} түрүүлж харсан ({f.get('shots')} сум "
            f"буудсан) боловч {enemy}-ийн {review_weapon(f.get('weapon'))}-д унав. Swing {swing}."
        )

    elif code == "flash_kill":
        killer, victim = who(f.get("killer")), who(f.get("victim"))
        if f.get("own"):
            title = f"{main} — өөрийн flash-аар kill"
            text = f"{main} flash шидээд {_secs(f.get('seconds', 0))} цайрсан {victim}-г өөрөө алав"
        else:
            title = f"{main}-ийн flash → {killer}-ийн kill"
            text = (
                f"{main}-ийн flash {victim}-г {_secs(f.get('seconds', 0))} цайруулж, {killer} алав"
            )
        text += f"{_at(f.get('spot'))}; kill-ийн Swing {review_swing(f.get('kill_swing'))}."
    elif code == "nade_damage_kill":
        nade = "HE" if f.get("nade") == "he" else "молотов"
        title = f"{main}-ийн {nade} → kill"
        text = (
            f"{main}-ийн {nade} {who(f.get('victim'))}-д {f.get('dealt')} damage өгснөөр "
            f"{who(f.get('killer'))}-ийн kill боломжтой болов."
        )
    elif code == "fire_delay":
        if f.get("what") == "defuse":
            title = f"{main}-ийн молотов defuse-ийг саатуулав"
            end = " Бөмбөг дэлбэрэв." if f.get("exploded") else ""
            text = (
                f"Тавьсан бөмбөг дээр{_at(f.get('spot'))} {_secs(f.get('seconds', 0))} шатаж, CT "
                f"defuse хийж чадсангүй.{end}"
            )
        else:
            title = f"{main}-ийн молотов plant-ийг саатуулав"
            text = (
                f"{f.get('ts')} T ойрхон байхад{_at(f.get('spot'))} {_secs(f.get('seconds', 0))} "
                "шатаж, plant хойшлов."
            )
    elif code == "team_flash":
        blinded = ", ".join(
            f"{who(b['sid'])} ({_secs(b['seconds'])})" for b in f.get("blinded") or []
        )
        title = f"{main} — багийнхаа хүмүүсийг цайруулав"
        text = f"{main}-ийн flash{_at(f.get('spot'))} {blinded}-г цайруулав."
        if f.get("died"):
            text += f" {plural_players([who(s) for s in f['died']])} цайрсан байхдаа унав."
    elif code == "empty_utility":
        title = f"{main} — хоосон flash"
        text = (
            f"Энэ мапад шидсэн {f.get('flashes')} flash-ийн {f.get('empty_flashes')} нь нэг ч "
            "дайсныг 1 секундээс дээш цайруулсангүй."
        )
    return {"title": title, "text": text}


def review_round(r: dict, who, team) -> str:
    """Раундын нэг өгүүлбэр: хэн, яаж хожсон, хэн шийдсэн."""
    winner = team(r.get("winner_team_id")) or side(r.get("winner_side", ""), short=True)
    how = REVIEW_REASON.get(r.get("reason") or "", (r.get("reason") or "").replace("_", " "))
    text = f"{winner} ({side(r.get('winner_side', ''), short=True)}) хожив — {how}."
    decider = r.get("decider")
    if decider and (r.get("swing") or {}).get(decider, 0.0) >= 0.05:
        text += (
            f" Хамгийн их нөлөө: {who(decider)} (Swing "
            f"{review_swing((r.get('swing') or {}).get(decider))})."
        )
    return text


# -- Тойм (Summary, CONTEXT.md): нэг багийн раунд, map, match-ийн дүгнэлт ------
SUMMARY_LABEL = {
    "pistol": "Pistol раунд",
    "opening": "Opening duel",
    "trade": "Trade",
    "full_v_full": "Full buy vs full buy",
    "force": "Force buy",
    "eco": "Eco раунд",
    "full_v_light": "Хөнгөн зэвсэгтэй өрсөлдөгч",
    "post_plant": "Plant-ын дараа",
    "retake": "Retake",
    "win_streak": "Дараалсан хожил",
    "loss_streak": "Дараалсан алдагдал",
    "comeback": "Эргүүлсэн раунд",
}

# Focus point бүрийн «юун дээр ажиллах» нэг өгүүлбэр (хэмжүүр болон Finding-ийн code).
SUMMARY_ADVICE = {
    "pistol": "Pistol раундын buy, эхний 20 секундын төлөвлөгөөгөө дахин бэлд.",
    "opening": "Эхний холбоонд ганцаараа бүү ор: flash-тай, хосоороо, мэдээлэлтэй ор.",
    "trade": "Хосоороо хөдөл: багийн гишүүнээ trade хийж чадах зайд байрлаж, тэр унахад шууд "
    "сольж ор.",
    "full_v_full": "Full buy раундын default, execute-ээ шинэчил: utility-гаа нэгтгэж нэг цэг рүү "
    "хамт ор.",
    "force": "Force buy-гаа сонгомол болго: эдийн засгаа тооцоолж, хамтдаа stack хийж тогло.",
    "full_v_light": "Хөнгөн зэвсэгтэй өрсөлдөгчөөс зай барьж, ойрын тулаанаас зайлсхий.",
    "post_plant": "Plant-ын дараах байрлал, crossfire-оо бэлд; молотов, утаагаа defuse "
    "саатуулахад хадгал.",
    "loss_streak": "Дараалан алдаж эхлэхэд timeout авч, эдийн засаг, тактикаа шинэчил.",
    "died_in_advantage": "Давуу байдалтай үед яарч бүү тулалд: хосоороо, utility-тай хаалт хий.",
    "team_flashed_death": "Flash шидэхээсээ өмнө багийн гишүүддээ дуудаж хэл; pop flash-ын замаа "
    "сур.",
    "lost_weapon_save": "Раунд алдагдсан үед save хийх шийдвэрээ эрт гаргаж, буугаа хадгал.",
    "moving_shots": "Counter-strafe хий: буудахын өмнө бүрэн зогс.",
    "awp_miss": "AWP-аар буудсаны дараа байрлалаа соль, шууд дахин peek бүү хий.",
    "bomb_lost": "Бөмбөгтэй тоглогчийг ганцааранг нь бүү үлдээ; бөмбөгөө багийн дунд авч яв.",
    "time_out": "Раундын цагийг хяна: 40 секунд үлдэхэд шийдвэрээ гарга.",
    "kitless": "Kit-ээ авч, retake-д kit-тэй тоглогч эхэлж defuse хийх ёстой.",
    "unused_utility": "Худалдаж авсан utility-гаа үхэхээсээ өмнө ашигла.",
    "no_gun_in_hand": "Дайсантай таарч болох газар буугаа гартаа барьж яв.",
    "crosshair": "Crosshair-ээ дайсан гарч ирэх өнцөг, толгойн өндөрт урьдчилан байрлуул.",
    "unscoped_awp": "AWP-аар peek хийхдээ scope-оо урьдчилан нээ.",
    "unfinished": "Шархдуулсан дайсныг дуусга: шууд repeek хий эсвэл багийн гишүүддээ HP-г нь хэл.",
    "advantage_lost": "Давуу байдлаа хадгал: хосоороо, цагтай тоглож өрсөлдөгчийг өөр дээрээ "
    "ирүүл.",
    "blind_unpunished": "Дайсан цайрсан агшинд шууд peek хийж ашигла.",
    "defuse_chance": "Defuse хийх цонхыг ашигла: smoke-той, багийн гишүүдийн хамгаалалттай суу.",
    "saw_no_shot": "Дайсныг харангуут бууд, эсвэл байрлалыг нь багийн гишүүддээ хэл.",
    "saw_first_lost": "Түрүүлж харсан бол түрүүлж бууд: урьдчилсан байрлал, reaction-оо "
    "дасгалжуул.",
    "team_flash": "Flash-аа багийн гишүүдийнхээ харах чиглэлээс гадуур шид, шидэхээсээ өмнө дууд.",
    "empty_utility": "Flash, HE-гээ мэдээлэлтэй цэг рүү шид; хоосон шидэлт мөнгө, цаг үрнэ.",
}

_OUTCOME = {
    ("ct", True, "t_killed"): "T-г бүгдийг нь хөнөөж хожсон",
    ("ct", True, "bomb_defused"): "бөмбөгийг defuse хийж хожсон",
    ("ct", True, "time_ran_out"): "цагийг хамгаалж хожсон",
    ("t", True, "ct_killed"): "CT-г бүгдийг нь хөнөөж хожсон",
    ("t", True, "bomb_exploded"): "plant хийж, бөмбөг дэлбэрч хожсон",
    ("ct", False, "ct_killed"): "бүгдээрээ унаж алдсан",
    ("ct", False, "bomb_exploded"): "plant-ыг зогсоож чадалгүй алдсан",
    ("t", False, "t_killed"): "бүгдээрээ унаж алдсан",
    ("t", False, "bomb_defused"): "plant хийсэн ч defuse-д алдсан",
    ("t", False, "time_ran_out"): "цаг дуусч алдсан",
}


def summary_round_line(f: dict) -> str:
    """Нэг багийн нэг раунд нэг мөрөөр: «T · force buy — B-д plant хийсэн ч defuse-д алдсан»."""
    sd = f["side"]
    out = _OUTCOME.get((sd, f["won"], f.get("reason") or ""))
    if out is None:
        out = "хожсон" if f["won"] else "алдсан"
    if f.get("site") and ("plant" in out or "defuse" in out):
        out = f"{f['site']}-д {out}"
    text = f"{side(sd, short=True)} · {BUY.get(f.get('buy') or '', f.get('buy') or '—')} — {out}"
    if f["won"] and f.get("low") is not None:
        text += f", хожих магадлал {review_pct(f['low'])} байхаас эргүүлсэн"
    elif not f["won"] and f.get("high") is not None:
        text += f", {review_pct(f['high'])} хүрсэн давуу байдлаа алдсан"
    return text + "."


def summary_opening(f: dict, who) -> str:
    """Раундын opening duel-ийг тухайн багийн талаас."""
    if f["got"]:
        return f"Opening: {who(f['killer'])} → {who(f['victim'])}"
    return f"Opening алдсан: {who(f['victim'])} ← {who(f['killer'])}"


def _ranked(pairs, limit: int = 3) -> str:
    """[('PokemoN-', 3), ('Zesta', 2)] → 'PokemoN- 3, Zesta 2'."""
    return ", ".join(f"{name} {n}" for name, n in pairs[:limit])


def summary_metric(code: str, good: bool, f: dict, who) -> str:
    """Тоон хэмжүүрийн нэг мөр, тоотойгоо."""
    w, n = f.get("won", 0), f.get("n", 0)
    rate = review_pct(w / n) if n else "—"
    rounds = ", ".join(f"R{x}" for x in (f.get("rounds") or [])[:6])
    players = _ranked([(who(s), c) for s, c in f.get("players") or []])
    if code == "pistol":
        if good:
            return f"Pistol раундын {w}/{n}-ийг авсан."
        return f"Pistol раундын {n}/{n}-ийг алдсан."
    if code == "opening":
        if good:
            text = f"Opening duel-ийн {w}/{n}-ийг авсан ({rate})"
            return text + (f"; голлон {players}." if players else ".")
        text = f"Opening duel-ийн {n - w}/{n}-д түрүүлж унасан ({rate} хожил)"
        return text + (f"; ихэвчлэн {players}." if players else ".")
    if code == "trade":
        traded, deaths = f.get("traded", 0), f.get("deaths", 0)
        share = review_pct(traded / deaths) if deaths else "—"
        if good:
            return f"Үхлийн {share} нь trade хийгдсэн ({traded}/{deaths})."
        text = f"Үхлийн ердөө {share} нь trade хийгдсэн ({traded}/{deaths})"
        if players:
            text += f"; trade-гүй унасан: {players}"
        missers = _ranked([(who(s), c) for s, c in f.get("missers") or []])
        if missers:
            text += f"; trade хийх боломжоо алдсан: {missers}"
        return text + "."
    if code == "full_v_full":
        if good:
            return f"Хоёулаа full buy-тай раундын {w}/{n}-ийг хожсон ({rate})."
        return f"Хоёулаа full buy-тай раундын ердөө {w}/{n}-ийг хожсон ({rate})."
    if code == "force":
        if good:
            return f"Force buy-ын {w}/{n}-ийг хожсон ({rounds})."
        return f"Force buy-ын {w}/{n}-ийг л хожсон ({rounds})."
    if code == "eco":
        return f"Eco раундад {w} удаа хожсон ({rounds})."
    if code == "full_v_light":
        return (
            f"Full buy-тай байхдаа eco/force-той өрсөлдөгчид {n - w}/{n} раунд алдсан ({rounds})."
        )
    if code == "post_plant":
        if good:
            return f"Plant хийсэн {n} раундын {w}-ийг хожсон."
        return f"Plant хийсэн {n} раундын ердөө {w}-ийг хожсон ({rounds})."
    if code == "retake":
        return f"Өрсөлдөгч plant хийсэн {n} раундын {w}-д retake хийж хожсон ({rounds})."
    if code in ("win_streak", "loss_streak"):
        first, last = f["rounds"][0], f["rounds"][-1]
        did = "хожсон" if code == "win_streak" else "алдсан"
        return f"R{first}–R{last}: {len(f['rounds'])} раунд дараалан {did}."
    if code == "comeback":
        return f"Хожих магадлал 20%-иас доош байхаас {n} раунд эргүүлж хожсон ({rounds})."
    return str(f)


def summary_pattern(code: str, f: dict, who) -> str:
    """Нэг төрлийн Finding давтагдсан нь: тоо, хэн, хаана."""
    label = REVIEW_CODE.get(code, code)
    text = f"{label} — {f['count']} удаа"
    players = _ranked([(who(s), c) for s, c in f.get("players") or []])
    if players:
        text += f" ({players})"
    spots = [s for s, _c in (f.get("spots") or []) if s][:2]
    if spots:
        text += f", ихэвчлэн {' ба '.join(spots)}-д"
    if f.get("maps"):
        text += f"; {f['maps']} map-д давтагдсан"
    return text + "."


def summary_map_line(f: dict, team) -> str:
    """Match-ийн тоймд нэг map нэг мөрөөр."""
    winner = team(f.get("winner_team_id")) or "?"
    text = f"{f['label']} {f['scoreline']} — {winner} авсан"
    if f.get("key"):
        text += f"; {f['key']}"
    return text + "."


def summary_across(item: dict, labels: dict) -> str:
    """Хэд хэдэн map-д давтагдсан Pattern, хэмжүүр."""
    maps = [labels.get(n, f"Map {n}") for n in item["maps"]]
    did = "давуу тал" if item["good"] else "алдаа"
    return (
        f"{item['label']} — {plural_players(maps)}-д давтагдсан {did} "
        f"(нийт {item['count']}, {summary_weight(item['weight'], item['good'])})."
    )


def summary_weight(rounds: float, good: bool) -> str:
    """Тоймын жин раундаар: 1.37 → '≈ −1.4 раунд'."""
    return f"≈ {'+' if good else '−'}{rounds:.1f} раунд"


# ---------------------------------------------------------- Lever, Caution --
# :mod:`app.services.levers`-ийн мөр бүр: ``title`` (юу хийх), ``facts`` (тоо,
# Pool-тай харьцуулсан), ``counter`` (яаж). Тоо facts-д л байна; counter тоогүй.
ADVICE_LABEL = {
    "opening": "Opening duel хожил",
    "trade": "Trade хийгдсэн үхэл",
    "pistol": "Pistol хожил",
    "full_v_full": "Full vs full хожил",
    "force": "Force buy хожил",
    "eco": "Eco хожил",
    "full_v_light": "Full buy-тайдаа eco/force-д хожих",
    "post_plant": "Plant-ын дараах хожил",
    "retake": "Retake хожил",
    "comeback": "Эргүүлсэн раунд",
}

# (title, counter) per (measure, role). role: their_weak, my_strong → Lever;
# their_strong, my_weak → Caution. my_weak-д байхгүй бол SUMMARY_ADVICE.
ADVICE_TEXT = {
    ("opening", "their_weak"): (
        "Эхний дуэлийг санаачил",
        "Тэд нээлтийн тулаанд сул: эхний 30 секундэд flash-тай хос peek хийж хүний давуу "
        "байдлыг түрүүлж ав.",
    ),
    ("opening", "my_strong"): (
        "Нээлтийн давуу талаа ашигла",
        "Манай opening хүчтэй: эхний тулааныг санаачилж, авсан давуу байдлаа цэг авах руу "
        "шууд хөрвүүл.",
    ),
    ("opening", "their_strong"): (
        "Эхний дуэлийг ганцаараа бүү ав",
        "Тэд нээлтийн тулаанд хүчтэй: эхний 30 секундэд хосоороо, utility-тай тогло; мэдээллийг "
        "peek-ээр биш дуу, utility-гаар ав.",
    ),
    ("opening", "my_weak"): ("Эхний тулаанд бид унадаг", ""),
    ("trade", "their_weak"): (
        "Тэднийг тусгаарлаж ал",
        "Тэд багийн гишүүнээ trade хийдэггүй: ганцаардсан тоглогч руу нь шууд ор, нэгийг алсны "
        "дараа дахин нэг-нэгээр нь тулал.",
    ),
    ("trade", "my_strong"): (
        "Trade-ийн зайгаа хадгал",
        "Манай trade хүчтэй: хосоороо орж, эхний хүн унахад шууд сольж ор — тоо тэнцүүлэх нь "
        "бидэнд ашигтай.",
    ),
    ("trade", "their_strong"): (
        "Алсныхаа дараа байрлалаа соль",
        "Тэд trade-аа хурдан хийдэг: нэгийг алсны дараа тэр өнцөгт бүү үлд, trade-ийн зайнаас гар.",
    ),
    ("trade", "my_weak"): ("Бид trade-гүй унадаг", ""),
    ("pistol", "their_weak"): (
        "Pistol-д санаачлага ав",
        "Тэдний pistol сул: бэлтгэсэн pistol тактикаа (rush, stack) хэрэглээд 2-р раундын "
        "anti-eco-гоо урьдчилж төлөвлө.",
    ),
    ("pistol", "my_strong"): (
        "Pistol-оо давуу тал болго",
        "Манай pistol хүчтэй: бэлтгэсэн тактикаа ашиглаад 2–3-р раундын эдийн засгаа "
        "урьдчилж төлөвлө.",
    ),
    ("pistol", "their_strong"): (
        "Pistol-д болгоомжтой",
        "Тэдний pistol хүчтэй: kevlar, utility-гийн хуваарилалтаа нягтал; алдвал 2-р раундад "
        "force эсвэл бүтэн eco гэдгээ урьдчилж шийд.",
    ),
    ("pistol", "my_weak"): ("Бидний pistol сул", ""),
    ("full_v_full", "their_weak"): (
        "Full buy-ын тулааныг хүлээ",
        "Тэнцүү зэвсэгтэй раундад тэд сул: эрсдэлтэй force-оос зайлсхийж, эдийн засгаа хоёр "
        "талын full buy-д төвлөрүүл.",
    ),
    ("full_v_full", "my_strong"): (
        "Full buy-д бид давуу",
        "Хоёулаа full buy-тай раунд бидний давуу тал: эдийн засгаа хадгалж, full-ээр тулгар.",
    ),
    ("full_v_full", "their_strong"): (
        "Тэдний эдийн засгийг эвд",
        "Тэнцүү зэвсэгтэй раундад тэд хүчтэй: pistol, anti-eco, save hunt-аар тэдний full "
        "buy-ийн тоог цөөлөх нь чухал.",
    ),
    ("full_v_full", "my_weak"): ("Full buy раундад бид сул", ""),
    ("force", "their_weak"): (
        "Тэдний force-ийг тайван тос",
        "Тэдний force ихэвчлэн бүтэлгүйтдэг: force раундад ойрын тулаанаас зайлсхийж стандарт "
        "тогло — хожвол тэд дараагийн full buy-гүй үлдэнэ.",
    ),
    ("force", "my_strong"): (
        "Force-оо зориуд ашигла",
        "Манай force амжилттай: pistol алдсаны дараа эсвэл тэдний эдийн засаг сул үед "
        "force-оор эргүүлэх боломжтой.",
    ),
    ("force", "their_strong"): (
        "Тэдний force-ийг дутуу бүү үнэл",
        "Тэдний force аюултай: SMG, shotgun-аас зай барьж AWP-аа хамгаал; давуу байдалтай ч "
        "цэгт бүү бөөгнөр.",
    ),
    ("force", "my_weak"): ("Бидний force бүтэлгүйтдэг", ""),
    ("eco", "my_strong"): (
        "Eco раундад ч заналхийл",
        "Бид eco-д раунд хулгайлдаг: хамтдаа stack, rush хийж тэдний anti-eco-г шалга.",
    ),
    ("eco", "their_strong"): (
        "Тэдний eco-д болгоомжтой",
        "Тэд eco раундыг хулгайлдаг: anti-eco-д ойртож бүү тулалд, хосоороо, мэдээлэлтэй тогло.",
    ),
    ("full_v_light", "their_weak"): (
        "Force хийж эрсдэл гарга",
        "Тэд full buy-тай байхдаа eco, force-д олон раунд алддаг: pistol алдсаны дараа ч "
        "force-оор тулгарах нь ашигтай.",
    ),
    ("full_v_light", "my_weak"): ("Хөнгөн зэвсэгтэй өрсөлдөгчид бид алддаг", ""),
    ("post_plant", "their_weak"): (
        "Plant хийлгээд retake хий",
        "Тэд plant-ын дараа барьж чаддаггүй: цэгийг үхтлээ бүү хамгаал — хүнээ хадгалж, "
        "utility-тай хамтдаа retake хий.",
    ),
    ("post_plant", "my_strong"): (
        "Plant хийхийг зорь",
        "Манай post-plant хүчтэй: раундыг bomb тавих руу чиглүүлж, тавьсны дараа crossfire-оо "
        "барь.",
    ),
    ("post_plant", "their_strong"): (
        "Plant-ыг бүү өг",
        "Тэд plant-ын дараа маш сайн барьдаг: цэгийг эрт, хүчтэй хамгаалж plant-ыг зогсоо; "
        "retake хийх бол бүх utility-гаа хадгал.",
    ),
    ("post_plant", "my_weak"): ("Plant-ын дараа бид алддаг", ""),
    ("retake", "their_weak"): (
        "Bomb-оо тавь",
        "Тэдний retake сул: bomb тавих нь раундыг бараг шийднэ — хурдан plant хийгээд "
        "post-plant тогло.",
    ),
    ("retake", "my_strong"): (
        "Retake-д найд",
        "Манай retake хүчтэй: цэгт хэт олон хүн бүү алд, ухарч хүнээ хадгалаад хамтдаа retake хий.",
    ),
    ("retake", "their_strong"): (
        "Plant бол хожил биш",
        "Тэд retake хийж чаддаг: тавьсны дараа crossfire барьж, molotov, smoke-оо defuse "
        "саатуулахад хадгал.",
    ),
    ("retake", "my_weak"): (
        "Retake-д бид сул",
        "Retake-ээс илүү plant-ыг зогсоо: цэгийн хамгаалалтаа эрт нягтруулж, rotate-ээ хурдасга.",
    ),
    ("comeback", "my_strong"): (
        "Хоцорсон раундаа бүү орхи",
        "Бид хожих магадлал бага байхаас ч эргүүлдэг: хоцорсон үед save-ээс өмнө тоглох "
        "боломжийг тооцоол.",
    ),
    ("comeback", "their_strong"): (
        "Давуу байдалд ч сул бүү тавь",
        "Тэд алдсан мэт раундыг эргүүлдэг: хүний давуу байдалтай үед хамтдаа, trade-тай "
        "цэвэрлэ, цагаа ашигла.",
    ),
    ("entry", "my_strong"): (
        "Entry-ээ дэмж",
        "Манай entry раунд хожуулдаг: entry тоглогчдоо flash, smoke-оор тусалж, эхний алалтын "
        "дараа шууд дагаж ор.",
    ),
    ("entry", "their_strong"): (
        "Тэдний entry-г тос",
        "Тэдний entry раундыг шийддэг: орох замд нь molotov, HE эрт хаяж, эхний хүнийг "
        "crossfire-т ал.",
    ),
    ("big_frag", "my_strong"): (
        "Шийдвэрлэх frag-ууд бидэнд бий",
        "Манай тоглогчид раунд эргүүлэх frag авдаг: тэдэнд мэдээлэл, utility-гаар орон зай гарга.",
    ),
    ("big_frag", "their_strong"): (
        "Тэдний гол өнцгийг ганцаараа бүү шалга",
        "Тэдний тоглогчид раунд шийдэх frag авдаг: тэдний дуртай өнцгийг utility-гаар нээ, "
        "хосоороо peek хий.",
    ),
    ("multikill", "my_strong"): (
        "Олон алалтын боломж гарга",
        "Бид multi-kill авдаг: дайсныг нэг цэгт шахаж, давуу байрлалаас crossfire хий.",
    ),
    ("multikill", "their_strong"): (
        "Нэг дор олноор бүү ор",
        "Тэд multi-kill авдаг: нэг өнцгөөс дараалан бүү peek, зайгаа тараан нэг хаалгаар "
        "бөөнөөрөө бүү ор.",
    ),
    ("clutch", "my_strong"): (
        "Clutch-д итгэ",
        "Манай clutch хүчтэй: сүүлчийн хүн цагтай бол яаралгүй, багийн гишүүд мэдээллээр дэмжинэ.",
    ),
    ("clutch", "their_strong"): (
        "Сүүлчийн хүнийг хамтдаа ал",
        "Тэд clutch хожно: сүүлчийн тоглогчийг ганцаараа бүү хай — хосоороо, smoke, flash-тай "
        "цэвэрлэ.",
    ),
    ("plant", "my_strong"): (
        "Шахалт дор plant хийж чаддаг",
        "Бид хэцүү үед ч plant хийдэг: цэг авмагц тавиад post-plant байрлалаа сонго.",
    ),
    ("plant", "their_strong"): (
        "Тэдний plant-ыг тасал",
        "Тэд шахалт дор ч plant хийдэг: тавих цэг рүү molotov хадгалж, сүүлийн секундэд peek "
        "хийх хүнээ бэлд.",
    ),
    ("defuse", "my_strong"): (
        "Defuse-ийн шийдвэр сайн",
        "Бид шахалт дор defuse хийдэг: retake-д kit-тэй тоглогчийг хамгаалж, smoke-оо "
        "defuse-д хадгал.",
    ),
    ("defuse", "their_strong"): (
        "Defuse-ийг саатуул",
        "Тэд шахалт дор defuse хийдэг: bomb-ын орчимд molotov хадгалж, сүүлийн 10 секундэд хаа.",
    ),
    ("flash_kill", "my_strong"): (
        "Flash-тай ор",
        "Манай flash алалт бий болгодог: pop flash-ын дараа шууд peek хийх хосоо бэлд.",
    ),
    ("flash_kill", "their_strong"): (
        "Тэдний flash-аас эргэ",
        "Тэдний flash алалт бий болгодог: flash сонсогдмогц эргэж, өөр өнцгөөс барь.",
    ),
    ("nade_damage_kill", "my_strong"): (
        "HE, molotov-оор шахаж ал",
        "Манай гранатын хохирол алалтад хүргэдэг: HE, molotov-оо түгээмэл байрлал руу зориуд хая.",
    ),
    ("nade_damage_kill", "their_strong"): (
        "Түгээмэл байрлалд удаан бүү зогс",
        "Тэдний HE, molotov хохирол учруулаад алалтад хүргэдэг: стандарт байрлалаа сольж, HP-ээ "
        "хамгаал.",
    ),
    ("fire_delay", "my_strong"): (
        "Molotov-оор саатуул",
        "Манай molotov plant-ыг саатуулдаг: rotate ирэх хүртэл plant-ын цэг рүү molotov-оо хадгал.",
    ),
    ("fire_delay", "their_strong"): (
        "Plant-ын цэгээ урьдчилж сонго",
        "Тэд molotov-оор plant-ыг саатуулдаг: smoke-оор хамгаалсан, өөр plant-ын цэгтэй тогло; "
        "molotov-ыг smoke-оор унтраа.",
    ),
    ("died_in_advantage", "their_weak"): (
        "Дутсан ч тайван тогло",
        "Тэд хүний давуу байдалд яарч үхдэг: дутсан үед ч ухарч өнцөг барь — тэд өөрсдөө ирнэ.",
    ),
    ("advantage_lost", "their_weak"): (
        "Алдсан мэт раундад ч тэмц",
        "Тэд хожих магадлал өндөр байхдаа раундаа алддаг: хоцорсон үед save-ээс өмнө retake, "
        "clutch-ийн боломжийг тооцоол.",
    ),
    ("team_flashed_death", "their_weak"): (
        "Тэдний flash-ын дараа тулал",
        "Тэд өөрсдийн flash-д цайрч үхдэг: тэдний flash-ын дараах агшинд peek хий — эхэлж "
        "орсон нь харахгүй байж магадгүй.",
    ),
    ("team_flash", "their_weak"): (
        "Тэдний execute-ийг хүлээ",
        "Тэдний flash өөрсдийгөө цайруулдаг: execute-ийн эхэнд хүлээж, flash нь буусны дараа "
        "тулал.",
    ),
    ("lost_weapon_save", "their_weak"): (
        "Хожсон раундаа дуусга",
        "Тэд алдсан раунддаа буугаа хадгалдаггүй: раунд хожигдмогц үлдсэн тоглогчдыг хай — "
        "дараагийн раундад тэдний эдийн засаг сул болно.",
    ),
    ("awp_miss", "their_weak"): (
        "Тэдний AWP-ыг шахаж тогло",
        "Тэдний AWP алдсаныхаа дараа унадаг: AWP руу хоёроороо, double peek хий; анхны "
        "буудлагын дараа шууд дагаж ор.",
    ),
    ("moving_shots", "their_weak"): (
        "Тэднийг өөр дээрээ ирүүл",
        "Тэд гүйж буудаж алддаг: урт өнцөг барьж, тэднийг өөрсдөө ирэх хүртэл хүлээ.",
    ),
    ("unfinished", "their_weak"): (
        "Шархадсан ч дахин тулал",
        "Тэд шархдуулсан дайснаа дуусгадаггүй: HP цөөн ч байрлалаа сольж дахин тулал, "
        "мэдээллээ багийн гишүүддээ өг.",
    ),
    ("blind_unpunished", "their_weak"): (
        "Тэдний flash-ыг бүү хэт хүндэл",
        "Тэдний flash-ын араас peek ирдэггүй: цайрсан бол ухарч, сэргээд байрлалаа эргүүлэн барь.",
    ),
    ("no_gun_in_hand", "their_weak"): (
        "Эргэлтийн замд нь тос",
        "Тэд хутга, гранат барьсан үедээ тулалдаанд ордог: rotate-ийн замд нь гэнэтийн "
        "өнцгөөс тос.",
    ),
    ("unused_utility", "their_weak"): (
        "Эрт алалт хоёр дахин үнэтэй",
        "Тэд utility-гаа ашиглалгүй үхдэг: execute-ээс өмнө эрт алалт авбал тэдний гранат ч "
        "хамт алга болно.",
    ),
    ("bomb_lost", "their_weak"): (
        "Bomb зөөгчийг ан",
        "Тэдний bomb зөөгч ганцаардаж унадаг: bomb-той тоглогчийн замыг таньж, тэр зүг рүү "
        "агрессив мэдээлэл ав.",
    ),
    ("time_out", "their_weak"): (
        "Цагаар хож",
        "Тэд цагтаа багтаж чаддаггүй: utility-гаар саатуулж, ухарч хамгаал — цаг тэдний эсрэг "
        "ажилладаг.",
    ),
    ("kitless", "their_weak"): (
        "Хожуу plant хий",
        "Тэд kit-гүй retake хийдэг: хожуу plant хийвэл kit-гүй defuse-д цаг хүрэхгүй.",
    ),
    ("defuse_chance", "their_weak"): (
        "Plant-ын дараа шахалт үүсгэ",
        "Тэд defuse хийх боломжоо алддаг: bomb-ын орчимд дуу, utility-гаар шахалт үүсгэ.",
    ),
    ("crosshair", "their_weak"): (
        "Гэнэтийн өнцгөөс тулал",
        "Тэдний crosshair placement сул: стандарт бус өнцгөөс, хурдан peek-ээр тулал.",
    ),
    ("unscoped_awp", "their_weak"): (
        "AWP-ыг ойроос шах",
        "Тэдний AWP scope-гүй унадаг: ойрын зайнаас хурдан ор.",
    ),
    ("saw_no_shot", "their_weak"): (
        "Хурдан peek хий",
        "Тэд харсан ч буудаж амждаггүй: wide, хурдан peek-ээр түрүүлж бууд.",
    ),
    ("saw_first_lost", "their_weak"): (
        "Aim duel-ээс бүү зайлсхий",
        "Тэд түрүүлж харсан ч дуэлиа алддаг: тэдэнтэй нүүр тулсан дуэлийг хүлээн ав.",
    ),
}

# Хос мөр: (миний хэмжүүр, тэдний хэмжүүр, role) → (title, counter).
ADVICE_PAIR = {
    ("opening", "opening", "lever"): (
        "Нээлтийн тулааныг давуу тал болго",
        "Бид эхний тулаанд хүчтэй, тэд сул: эхний 30 секундэд агрессив мэдээлэл аваад хүний "
        "давуу байдлаа цэг рүү шууд хөрвүүл.",
    ),
    ("opening", "opening", "caution"): (
        "Эхний тулаанд тэд давуу",
        "Тэдний opening хүчтэй, бидний сул: эхний секундүүдэд peek-ээс зайлсхийж, "
        "utility-гаар мэдээлэл ав; хүнээ алдахгүйгээр раундыг удаашруул.",
    ),
    ("trade", "trade", "lever"): (
        "Хосоороо тоглоод тэднийг ганцаарчил",
        "Бид trade хийдэг, тэд хийдэггүй: хосоороо хөдөлж, тэдний тусгаарлагдсан тоглогчийг "
        "нэг-нэгээр нь ал.",
    ),
    ("trade", "trade", "caution"): (
        "Тэд trade хийдэг, бид хийдэггүй",
        "Тусдаа тоглох бүрт хүн алдана: багийн гишүүнээ trade хийх зайд байрлаж, тэр унахад шууд "
        "сольж ор.",
    ),
    ("entry", "trade", "lever"): (
        "Entry-гээр ганцаардсан хамгаалагчийг ал",
        "Манай entry хүчтэй, тэд trade хийдэггүй: entry-ийн араас хоёр дахь хүн шууд дагаж, "
        "цэгийг хурдан ав.",
    ),
    ("entry", "trade", "caution"): (
        "Тэдний entry-д бид trade хийдэггүй",
        "Цэгийн хамгаалалтаа хосоор тавь: эхний хүн унахад хоёр дахь нь trade-ийн өнцөгт "
        "бэлэн байх ёстой.",
    ),
    ("pistol", "pistol", "lever"): (
        "Pistol-оос эдийн засгийн давуу тал ав",
        "Бид pistol-д хүчтэй, тэд сул: pistol хожоод 2–3-р раундын anti-eco-гоо сахилгатай тогло.",
    ),
    ("pistol", "pistol", "caution"): (
        "Pistol-д тэд давуу",
        "Pistol тактикаа шинэчил: тэдний хүчтэй, бидний сул; алдвал 2-р раундын "
        "шийдвэрээ урьдчилж гарга.",
    ),
    ("full_v_full", "full_v_full", "lever"): (
        "Full buy-ын тулаанд давуу",
        "Тэнцүү зэвсэгтэй раундад бид хүчтэй, тэд сул: эдийн засгаа full buy-д төвлөрүүлж, "
        "эрсдэлтэй force-оос зайлсхий.",
    ),
    ("full_v_full", "full_v_full", "caution"): (
        "Full buy-д тэд давуу",
        "Тэнцүү зэвсэгтэй тулаан тэдэнд ашигтай: pistol, force, save hunt-аар тэдний "
        "эдийн засгийг эвд.",
    ),
    ("force", "full_v_light", "lever"): (
        "Force-оор эдийн засгийг нь эвд",
        "Манай force амжилттай, тэд full buy-тай байхдаа хөнгөн зэвсэгтэйд алддаг: мөнгө "
        "дутсан үед force-оор тулгар.",
    ),
    ("force", "full_v_light", "caution"): (
        "Тэдний force-д бид хэврэг",
        "Full buy-тай байхдаа тэдний force-д раунд алддаг: ойрын тулаанаас зайлсхийж, "
        "SMG/shotgun-аас зай барь.",
    ),
    ("eco", "full_v_light", "lever"): (
        "Eco-гоор ч заналхийл",
        "Бид eco-д раунд хулгайлдаг, тэд хөнгөн зэвсэгтэйд алддаг: eco-д хамтдаа stack хийж "
        "тэдний anti-eco-г шалга.",
    ),
    ("eco", "full_v_light", "caution"): (
        "Тэдний eco-д бид хэврэг",
        "Тэд eco хулгайлдаг, бид anti-eco-д алддаг: eco-той тэдэнд ойртож бүү тулалд, хосоороо "
        "тогло.",
    ),
    ("post_plant", "retake", "lever"): (
        "Plant хийгээд post-plant тогло",
        "Манай post-plant хүчтэй, тэдний retake сул: раундыг plant руу чиглүүл, тавьсны дараа "
        "crossfire-оо барь.",
    ),
    ("post_plant", "retake", "caution"): (
        "Plant-ыг бүү өг",
        "Тэдний post-plant хүчтэй, бидний retake сул: plant-ыг цэг дээр нь зогсоо, retake-д "
        "найдах хэрэггүй.",
    ),
    ("retake", "post_plant", "lever"): (
        "Plant хийлгээд retake хий",
        "Манай retake хүчтэй, тэдний post-plant сул: цэгт хүн бүү алд — ухарч хүнээ хадгалаад "
        "хамтдаа retake хий.",
    ),
    ("retake", "post_plant", "caution"): (
        "Plant хийсэн ч раунд дуусаагүй",
        "Тэдний retake хүчтэй, бидний post-plant сул: тавьсны дараах байрлал, crossfire-оо "
        "бэлдэж, utility-гаа defuse саатуулахад хадгал.",
    ),
    ("post_plant", "kitless", "lever"): (
        "Хожуу plant хийгээд барь",
        "Манай post-plant хүчтэй, тэд kit-гүй retake хийдэг: хожуу plant хийвэл defuse-д цаг "
        "хүрэхгүй.",
    ),
    ("post_plant", "kitless", "caution"): (
        "Kit-ээ заавал ав",
        "Тэдний post-plant хүчтэй, бид kit-гүй үлддэг: CT бүр kit авч, kit-тэй хүн эхэлж "
        "defuse хийнэ.",
    ),
    ("post_plant", "defuse_chance", "lever"): (
        "Plant-ын дараа шахалтаа үргэлжлүүл",
        "Манай post-plant хүчтэй, тэд defuse хийх боломжоо алддаг: bomb-ын орчмыг дуу, "
        "utility-гаар хяна.",
    ),
    ("post_plant", "defuse_chance", "caution"): (
        "Defuse-ийн цонхыг ашигла",
        "Тэдний post-plant хүчтэй, бид defuse хийх боломжоо алддаг: smoke-той, багийн гишүүдийн "
        "хамгаалалттай defuse-д суу.",
    ),
    ("fire_delay", "time_out", "lever"): (
        "Цагаар хож",
        "Манай molotov саатуулдаг, тэд цагтаа багтдаггүй: utility-гаа хэмнэж хэрэглээд plant-ыг "
        "сүүлийн секунд руу түлх.",
    ),
    ("fire_delay", "time_out", "caution"): (
        "Цагаа хяна",
        "Тэдний molotov саатуулдаг, бид цаг алддаг: 40 секунд үлдэхэд шийдвэрээ гаргаж, "
        "plant-ын цэгээ урьдчилж сонго.",
    ),
    ("clutch", "died_in_advantage", "lever"): (
        "Дутсан ч раундаа бүү орхи",
        "Бид clutch хожно, тэд давуу байдалд яарч үхдэг: дутсан үед ухарч өнцөг барь, тэд "
        "өөрсдөө ирнэ.",
    ),
    ("clutch", "died_in_advantage", "caution"): (
        "Давуу байдлаа хамтдаа хөрвүүл",
        "Тэд clutch хожно, бид давуу байдалд яарч үхдэг: хүнээр давуу үед хосоороо, "
        "utility-тай цэвэрлэ.",
    ),
    ("clutch", "advantage_lost", "lever"): (
        "Хожигдох мэт раундад ч тэмц",
        "Бид clutch хожно, тэд давуу байдлаа алддаг: хоцорсон үед ч save-ээс өмнө clutch-ийн "
        "боломжийг тооцоол.",
    ),
    ("clutch", "advantage_lost", "caution"): (
        "Давуу байдлаа бүү алд",
        "Тэд clutch хожно, бид давуу байдлаа алддаг: сүүлчийн хүнийг хамтдаа, smoke, flash-тай "
        "цэвэрлэ.",
    ),
    ("comeback", "died_in_advantage", "lever"): (
        "Хоцорсон раундаа бүү орхи",
        "Бид эргүүлж хождог, тэд давуу байдалд яарч үхдэг: дутсан үед тайван өнцөг барь.",
    ),
    ("comeback", "died_in_advantage", "caution"): (
        "Давуу байдалд бүү яар",
        "Тэд эргүүлж хождог, бид давуу байдалд яарч үхдэг: хүнээр давуу үед цагаа ашиглаж "
        "хамтдаа тогло.",
    ),
    ("comeback", "advantage_lost", "lever"): (
        "Алдсан мэт раундад ч тэмц",
        "Бид эргүүлж хождог, тэд давуу байдлаа алддаг: хоцорсон раундад save-ээс өмнө "
        "боломжоо тооцоол.",
    ),
    ("comeback", "advantage_lost", "caution"): (
        "Давуу байдлаа бүү алд",
        "Тэд эргүүлж хождог, бид давуу байдлаа алддаг: хүнээр давуу үед trade-тай, хамтдаа "
        "цэвэрлэ.",
    ),
}

ADVICE_LIMIT = {
    "reviews_waiting": "{team}-ийн {n}/{of} Match Map-ийн Review шинэчлэгдэж байгаа тул доорх "
    "Ашиглах, Анхаарах-д ороогүй.",
    "untagged": "{team}-ийн {n} Match Map-ийн раундад баг тодорхойгүй тул Review-ийн тоонд "
    "ороогүй.",
    "few_sightings": "Sightings ердөө {n}/{of} Match Map-д бий: харсан ч буудаагүй, crosshair "
    "зэрэг дүгнэлт бараг гараагүй.",
}


def _advice_value(x: dict) -> tuple[str, str]:
    """Нэг хэмжүүрийн утга ба Pool-ын дундаж үгээр."""
    if x["kind"] == "rate" and x["key"] != "comeback":
        return review_pct(x["value"]), review_pct(x["mean"])
    if x["kind"] == "player":
        return f"{review_swing(x['value'])}/раунд", review_swing(x["mean"])
    if x["key"] == "comeback":
        return f"{x['value'] * 24:.1f}/24 раунд", f"{x['mean'] * 24:.1f}"
    return f"{x['value']:.1f}/24 раунд", f"{x['mean']:.1f}"


def advice_fact(x: dict, whose: str, team: str, name) -> str:
    """«Манай T · Plant-ын дараах хожил 66% (Pool 82%), голлон X 4, ихэвчлэн B Site-д»."""
    who = "Манай" if whose == "mine" else team
    value, mean = _advice_value(x)
    if x["kind"] == "player":
        label = f"{x['player']} Swing"
    else:
        label = ADVICE_LABEL.get(x["key"]) or REVIEW_CODE.get(x["key"], x["key"])
    text = f"{who} {side(x['side'], short=True)} · {label} {value} (Pool {mean})"
    bits = []
    if x["kind"] == "player":
        codes = _ranked([(REVIEW_CODE.get(c, c), n) for c, n in x.get("codes") or []])
        if codes:
            bits.append(codes)
        if x.get("elsewhere"):
            bits.append("өмнөх багийнх нь тоо")
    else:
        players = _ranked([(name(s), n) for s, n in x.get("players") or [] if name(s)])
        if players:
            bits.append(f"голлон {players}")
    spots = [s for s, _n in x.get("spots") or []][:2]
    if spots:
        bits.append(f"ихэвчлэн {' ба '.join(spots)}-д")
    if x.get("everywhere"):
        value, mean = _advice_value({**x, **x["everywhere"]})
        bits.append(f"бүх Map-аар {value} (Pool {mean})")
    elif x.get("scope") == "all_maps":
        bits.append("бүх Map-аас")
    return text + (f" — {'; '.join(bits)}" if bits else "") + "."


def _player_text(x: dict, role: str) -> tuple[str, str]:
    who, sd = x["player"], side(x["side"], short=True)
    if role == "their_strong":
        return (
            f"{who}-г ганцаараа бүү тулгар",
            f"{who} тэдний {sd} талын раунд шийддэг тоглогч: түүний байрлал руу utility хаяж, "
            "хосоороо peek хий; эхний тулаанд түүнтэй бүү тулгар.",
        )
    if role == "their_weak":
        return (
            f"{who}-г онил",
            f"{who} {sd} талдаа багтаа раунд алдуулдаг: түүний барьдаг тал руу дуэл санал "
            "болгож, түүнээс эхлэн ал.",
        )
    if role == "my_strong":
        return (
            f"{who}-д тулгуурла",
            f"{who} манай {sd} талын хамгийн үнэ цэнтэй тоглогч: раундын гол үүргийг түүнд өгч "
            "utility-гаар дэмж.",
        )
    return (
        f"{who}-г дэмж",
        f"{who} {sd} талдаа багтаа раунд алдуулж байна: ганцааранг нь бүү үлдээ, trade хийх "
        "зайд хос тавьж үүргийг нь хөнгөл.",
    )


def _advice_text(x: dict, role: str) -> tuple[str, str]:
    if x["kind"] == "player":
        return _player_text(x, role)
    title, counter = ADVICE_TEXT.get((x["key"], role), ("", ""))
    if role == "my_weak":
        title = title or f"{REVIEW_CODE.get(x['key'], x['key'])} — бидний сул тал"
        counter = counter or SUMMARY_ADVICE.get(x["key"], "")
    return title or REVIEW_CODE.get(x["key"], x["key"]), counter


def advice(entry: dict, team: str, name) -> dict:
    """Нэг Lever эсвэл Caution: юу хийх, яагаад (тоо), яаж, нотолгоо."""
    role, mine, theirs = entry["role"], entry["mine"], entry["theirs"]
    if entry["pair"]:
        title, counter = ADVICE_PAIR.get(
            (mine["key"], theirs["key"], role),
            _advice_text(theirs, "their_weak" if role == "lever" else "their_strong"),
        )
    elif mine is not None:
        title, counter = _advice_text(mine, "my_strong" if role == "lever" else "my_weak")
    else:
        title, counter = _advice_text(theirs, "their_weak" if role == "lever" else "their_strong")
    facts, proofs = [], []
    for x, whose in ((mine, "mine"), (theirs, "theirs")):
        if x is None:
            continue
        facts.append(advice_fact(x, whose, team, name))
        proofs.append({"whose": whose, "label": "Манай" if whose == "mine" else team,
                       "evidence": x["evidence"]})  # fmt: skip
    best = min((p["evidence"]["strength"] for p in proofs), key=lambda s: _PB_STRENGTH[s])
    return {
        "role": role,
        "pair": entry["pair"],
        "title": title,
        "facts": facts,
        "counter": counter,
        "proofs": proofs,
        "strength": best,
        "weight": entry["weight"],
        "weight_label": (
            f"≈ {entry['weight']:.1f} раунд/хагас"
            if entry["weight"] >= 0.1
            else "< 0.1 раунд/хагас"
        ),
    }


def advice_limit(item: dict) -> str:
    text = ADVICE_LIMIT.get(item["kind"])
    if text is None:
        return caution_line(item)
    return text.format(**item)


def advice_action(entry: dict, map_label: str, team: str) -> dict:
    """«Юу хийх» жагсаалтад өргөсөн Lever эсвэл Caution: ``{what, why}``."""
    worded = advice(entry, team, lambda _sid: "")
    kind = "Ашиглах" if entry["role"] == "lever" else "Анхаарах"
    why = " ".join(worded["facts"]) + (f" {worded['counter']}" if worded["counter"] else "")
    return _act(f"{map_label} · {kind}: {worded['title']}", why)


# -- Forecast (docs/plans/03 FC-6) ------------------------------------------------
FORMAT = {"bo1": "Bo1", "bo3": "Bo3", "bo5": "Bo5"}


def round5(p: float) -> int:
    """A chance as a percent, to the nearest 5: the model is no finer than that."""
    return int(round(p * 20) * 5)


def forecast_scale(p: float) -> tuple[str, str]:
    """``(word, tone)`` for our chance of a series."""
    if p >= 0.65:
        return "давуу", "good"
    if p >= 0.55:
        return "бага зэрэг давуу", "good"
    if p > 0.45:
        return "тэнцүү", "warn"
    if p > 0.35:
        return "бага зэрэг дутуу", "warn"
    return "дутуу", "crit"


def forecast_often(p: float) -> str:
    return f"ийм 10 цувралаас ~{round(p * 10)}-д нь хожно"


def forecast_trust(band: dict | None) -> str:
    if not band:
        return ""
    return (
        f"Өмнө нь энэ хүрээнд ({round(band['lo'] * 100)}–{round(band['hi'] * 100)}%) "
        f"таамагласан {band['n']} цувралын {pct(band['won'] * 100, 0)} нь хожсон."
    )


FORECAST_LIMIT = {
    "unrated": (
        "{team}-ийн үр дүн Valve-ийн жагсаалтад алга: Rating байхгүй тул Forecast гарсангүй."
    ),
    "cold": "{team} ердөө {series} цуврал тоглосон: Rating тогтоогоогүй байж магадгүй.",
    "stale": "{team}-ийн Rating-ийг {last}-аас хойш ямар ч цуврал хөдөлгөөгүй.",
    "lineup": (
        "{team}-ийн сонгосон Lineup-д үр дүнгийн тав дахь гурав нь алга: Rating-ийг "
        "тоглогчдын өмнөх багуудаас тооцов."
    ),
    "maps_even": (
        "Map бүрийн ялгааг тооцоогүй: хадгалсан {n} Match Map дээр шалгахад Map-ын "
        "offset таамгийг сайжруулсангүй (log loss {with_offsets}, Rating дангаараа "
        "{rating_only}). Map-аа Map-ын хүснэгт ба Playbook-оор сонго."
    ),
}


def forecast_limit(item: dict) -> str:
    text = FORECAST_LIMIT.get(item["code"], item["code"])
    return text.format(**{k: ("" if v is None else v) for k, v in item.items()})


def forecast_line(fmt: str, p: float, mine: str, theirs: str) -> str:
    word, _tone = forecast_scale(p)
    return f"{FORMAT.get(fmt, fmt)}: {mine} {theirs}-ийг хожих магадлал ~{round5(p)}% ({word})."


# The host's one heavy permit (OPS-6): a parse waits for another to finish.
HEAVY_WAIT = "Өөр parse ({holder}) дуусахыг хүлээж байна: хоёр зэрэг явбал санах ой хүрэхгүй."


# Uploads (DATA-1)
UPLOAD_ASSEMBLE = "{name} файлыг хэсгүүдээс нь нийлүүлж байна."
UPLOAD_SAME_MAP = (
    "{name}: {map} энэ upload-д аль хэдийн байна. Нэг Map-ыг хоёр удаа тоглосон бол "
    "тусад нь upload хийнэ үү."
)
UPLOAD_WHO = (
    "{n} Map дээр аль тал нь манай баг болохыг тоглогчдоос нь таньж чадсангүй: "
    "Upload-ын хуудаснаас сонгоно уу."
)
UPLOAD_GONE = "{map}: хадгалсан tick дата алга, дахин upload хийнэ үү."
UPLOAD_SIDES_SET = "талуудыг сонгосноор дахин хадгаллаа."


# -- PL-7: what the evidence settles about a Player -----------------------------------
def _signed_pct(v: float) -> str:
    return f"{v * 100:+.1f}%"


def _kpi_number(kpi: str, value: float) -> str:
    if kpi.endswith("_pct"):
        return f"{value:.1f}%"
    if kpi.endswith(("_per_round", "_rate", "_share")) or kpi == "kd_ratio":
        return f"{value:.2f}"
    return f"{value:.1f}"


def card_lines(proven: list[dict], reviewed: dict | None) -> dict:
    """``{"strengths", "weaknesses", "tendencies", "swing"}``, each line worded with
    its sample. Only what passed its test is here (PL-3, PL-7)."""
    out: dict = {"strengths": [], "weaknesses": [], "tendencies": [], "swing": ""}
    for row in proven:
        side = SIDE_SHORT.get(row["side"], row["side"])
        text = (
            f"{side}: {row['label']} {_kpi_number(row['kpi'], row['shrunk'])} "
            f"(үүргийн жишиг {_kpi_number(row['kpi'], row['cohort_mean'])})"
        )
        (out["strengths"] if row["verdict"] == "above" else out["weaknesses"]).append(text)
    if not reviewed:
        return out
    sw = reviewed.get("swing")
    if sw:
        out["swing"] = (
            f"Swing/раунд {_signed_pct(sw['per_round'])} "
            f"({reviewed['maps']} мап, 80%: {_signed_pct(sw['low'])}…{_signed_pct(sw['high'])})"
        )
        if sw["clear"]:
            up = sw["per_round"] > 0
            (out["strengths"] if up else out["weaknesses"]).append(
                out["swing"] + (" — бусдаас дээгүүр" if up else " — бусдаас доогуур")
            )
    for key in ("weaknesses", "tendencies"):
        for line in reviewed.get(key) or []:
            out[key].append(
                f"{line['label']}: 24 раундад {line['per24']:g} "
                f"(бусад тоглогч {line['pool_per24']:g}, {line['count']} удаа)"
            )
    return out
