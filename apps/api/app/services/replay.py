"""One round, played back: where everybody stood, and what they did.

Everything else aggregates; this hands back a single round at a resolution fine
enough to watch, because some questions ("why did that retake fail") only have
an answer in the sequence.

Positions are not database rows (1.4 M a map): they live in the map's Tick
Data (:mod:`app.services.tickdata`). The rounds are cut from it once, at ingest,
and stored as gzip JSON in ``replay_rounds``; a page view is one row read.

Five decisions worth knowing before changing anything here (from cstat, where
each was measured):

* **The frame grid is 8 Hz, not the tickrate.** The client interpolates between
  frames, so 8 Hz is already smoother than it can draw, and it keeps a round's
  payload near 200 KB instead of 2 MB.
* **A whole map is built in one pass.** The round is already a column, so the
  grid is computed for every round at once and stored as one row per round.
* **Only ``*Projectile`` grenade rows are flight.** The rest of the grenades
  table is inventory, one row per tick, and even projectiles keep reporting
  after they land, so a flight is cut where it stops moving.
* **A corpse is not a player.** The tick stream holds the body at ``health = 0``
  for the rest of the round, so aliveness is read off ``hp``.
* **On a two-floor map, everything carries the floor it is on**, from ``Z`` and
  nothing else, as an index into the payload's ``levels``.
* **The Loadout travels as changes**, like the callout: what a player holds,
  carries, wears and has left changes a few dozen times a round, against 8
  frames a second. A bundle parsed before it was read has none, and the page
  falls back to the last weapon fired for what is in hand.

Ported from cstat's ``hltv/services/replay.py``; the payload is cstat's
(``REPLAY_SCHEMA`` 4) plus the Loadout (5), so the page's player is a port of
cstat's script. The
callout labels cstat computed while drawing its map plate come from the Tick
Data's ``geometry``.
"""

from __future__ import annotations

import gzip
import json
import logging
import math

import polars as pl
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.models import GrenadeThrow, MapRoster, MatchMap, ReplayRound, Round
from app.services import radar
from app.services.analysis_store import weapon_family

logger = logging.getLogger(__name__)

REPLAY_HZ = 8
# Bumped when the payload's shape changes: every stored round is rebuilt from
# the Tick Data (see tickdata.derived_version).
REPLAY_SCHEMA = 8  # 6: who saw whom (VIZ-4); 7: the Round search's tokens; 8: footsteps (VIZ-12)
# Sightings bridged across gaps this short are one stretch of seeing.
SIGHT_GAP = 0.15  # seconds

# awpy names grenade entities by their engine class. The ones that end in
# Projectile are the thrown object in flight; the rest is inventory (H3).
_PROJECTILE = "Projectile"
_NADE_KIND = {
    "CSmokeGrenadeProjectile": "smoke",
    "CFlashbangProjectile": "flash",
    "CHEGrenadeProjectile": "he",
    "CMolotovProjectile": "fire",
    "CIncendiaryGrenadeProjectile": "fire",
    "CDecoyProjectile": "decoy",
}

# Anything moving less than this between two frames has landed.
_STOPPED_UNITS = 12.0

# Radii in world units, measured off the game's own values.
SMOKE_RADIUS = 144.0
FIRE_RADIUS = 120.0
# Flash/HE detonations are a moment, so these are display durations, long enough
# to catch while scrubbing at normal speed.
FLASH_POP_SECONDS = 2.2
FLASH_POP_RADIUS = 210.0
HE_POP_SECONDS = 0.9
HE_POP_RADIUS = 110.0

# One colour per player, five per side: blues for CT, ambers and reds for T.
CT_COLOURS = ["#5b9bd8", "#7fc7e8", "#4f7fd8", "#9db8ea", "#3fb7c4"]
T_COLOURS = ["#d39a55", "#e8b96a", "#cf6a56", "#e0854a", "#c9a227"]

_LEVEL_INDEX = {radar.UPPER: 0, radar.LOWER: 1}

# demoparser names Loadout items as the game's HUD does; these are the shorter
# names the page shows (the rest are short already: AK-47, M4A1-S, USP-S, AWP).
_ITEM_LABELS = {
    "Desert Eagle": "Deagle", "Glock-18": "Glock", "Dual Berettas": "Duals",
    "CZ75-Auto": "CZ", "R8 Revolver": "R8", "Galil AR": "Galil", "SSG 08": "Scout",
    "SG 553": "SG", "PP-Bizon": "Bizon", "UMP-45": "UMP", "Zeus x27": "zeus",
    "Flashbang": "flash", "Smoke Grenade": "smoke", "High Explosive Grenade": "HE",
    "Molotov": "molotov", "Incendiary Grenade": "incendiary", "Decoy Grenade": "decoy",
    "C4 Explosive": "C4",
}  # fmt: skip
_PISTOLS = {"Glock", "USP-S", "P2000", "P250", "Five-SeveN", "Tec-9", "CZ", "Deagle", "Duals", "R8"}
_GRENADES = ["flash", "smoke", "HE", "molotov", "incendiary", "decoy"]
# Knife skins each have their own name (Karambit, Butterfly Knife, knife_t...).
_KNIFE_WORDS = ("knife", "bayonet", "karambit", "dagger")


def _f(value) -> float | None:
    """A finite float, or None. Demos carry NaNs and one poisons a whole axis."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _i(value) -> int | None:
    out = _f(value)
    return None if out is None else int(out)


def _yaw_int(value) -> int | None:
    """Facing direction, rounded to a degree and wrapped into [0, 360)."""
    out = _f(value)
    return None if out is None else round(out) % 360


def _event_level(split: float | None, z) -> int | None:
    """Which floor an event happened on; None (shown on every floor) when unknown."""
    if split is None:
        return None
    value = _f(z)
    if value is None:
        return None
    return _LEVEL_INDEX[radar.level_at(split, value)]


def _weapon(name) -> str:
    """One name per gun, whichever feed named it (``weapon_`` prefix, knife skins, USP/P2000)."""
    key = (name or "").strip().lower()
    if key.startswith("weapon_"):
        key = key[len("weapon_") :]
    if key.startswith("knife"):
        key = "knife"
    return weapon_family(key)


def _item(name) -> str:
    name = (name or "").strip()
    if any(word in name.lower() for word in _KNIFE_WORDS):
        return "knife"
    return _ITEM_LABELS.get(name, name)


def _item_order(label: str) -> tuple[int, int]:
    """Gun, pistol, zeus, grenades in buy-menu order, then the bomb."""
    if label in _GRENADES:
        return (3, _GRENADES.index(label))
    if label == "C4":
        return (4, 0)
    if label == "zeus":
        return (2, 0)
    return (1 if label in _PISTOLS else 0, 0)


def _carried(inventory) -> list[str]:
    """The Loadout's items, knife left out (everyone has one), one entry per grenade."""
    labels = [_item(name) for name in inventory or [] if name]
    return sorted((x for x in labels if x != "knife"), key=_item_order)


def is_playable(match_map: MatchMap) -> bool:
    """A round can only be replayed from stored Tick Data."""
    return match_map.tick_dataset is not None


def round_payload(db: Session, match_map: MatchMap, number: int) -> bytes | None:
    """One round as stored: gzip JSON, ready to send with ``Content-Encoding: gzip``."""
    from app.services import tickdata

    if tickdata.ensure(db, match_map) is None:
        return None
    return db.scalar(
        select(ReplayRound.payload).where(
            ReplayRound.match_map_id == match_map.id, ReplayRound.number == number
        )
    )


def round_data(db: Session, match_map: MatchMap, number: int) -> dict | None:
    """One round's replay payload, decoded."""
    payload = round_payload(db, match_map, number)
    return json.loads(gzip.decompress(payload)) if payload else None


def scene(db: Session, match_map: MatchMap) -> dict | None:
    """The floor plan and callouts a round is drawn over, the same for every round.

    On a two-floor map it carries one image and one set of callouts per floor,
    all on the same rectangle, so switching floors costs an image swap. ``levels``
    is empty everywhere else (and on a two-floor map whose images aren't shipped).
    """
    from app.services import tickdata

    map_name = match_map.game_map.name if match_map.game_map else ""
    background = radar.plate(map_name)
    if background is None:
        return None
    dataset = tickdata.ensure(db, match_map)
    if dataset is None:
        return None
    geometry = dataset.geometry or {}
    floors = [
        {
            "key": level["key"],
            "url": radar.image_url(level["image"]),
            "labels": (geometry.get("level_labels") or {}).get(level["key"], []),
        }
        for level in radar.levels(map_name)
    ]
    if not all(floor["url"] for floor in floors):
        floors = []
    return {
        "plate": background,
        "labels": geometry.get("labels") or [],
        "levels": floors,
        "spots": _spot_labels(map_name, bool(floors)),
    }


def _spot_labels(map_name: str, floors: bool) -> list[dict]:
    """The Map's Spots for the callouts toggle, each on its floor when it has one."""
    from app.services import spots

    split = radar.split_altitude(map_name) if floors else None
    out = []
    for spot in spots.scene(map_name):
        level = None
        if split is not None and spot["z"]:
            lo, hi = spot["z"]
            if hi <= split:
                level = _LEVEL_INDEX[radar.LOWER]
            elif lo >= split:
                level = _LEVEL_INDEX[radar.UPPER]
        out.append({"name": spot["name"], "x": spot["x"], "y": spot["y"], "level": level})
    return out


def rounds_index(db: Session, match_map: MatchMap) -> list[dict]:
    """``[{round, seconds, players}]`` for the round strip, from the stored build."""
    from app.services import tickdata

    dataset = tickdata.ensure(db, match_map)
    return list((dataset.replay or {}).get("rounds") or []) if dataset else []


def build(db: Session, match_map: MatchMap, bundle) -> dict | None:
    """Cut every round from the Tick Data in one pass and store them.

    Returns the build's meta (``hz`` and the round index). Runs inside the
    caller's transaction: the ingest, or a rebuild from the stored bundle.
    """
    frames = bundle.tables
    ticks, rounds = frames.get("ticks"), frames.get("rounds")
    if ticks is None or rounds is None or ticks.is_empty() or rounds.is_empty():
        return None

    tickrate = match_map.tickrate or 64
    step = max(1, int(round(tickrate / REPLAY_HZ)))

    # The window is freeze-end to official end: the buy phase is twenty seconds
    # of standing in spawn, and the post-round is where the last kill still shows.
    spans, frames_by_round = {}, {}
    for row in rounds.to_dicts():
        number = _i(row.get("round_num"))
        start = _i(row.get("freeze_end")) or _i(row.get("start"))
        end = _i(row.get("official_end")) or _i(row.get("end"))
        if number is None or start is None or end is None or end <= start:
            continue
        spans[number] = (start, end)
        frames_by_round[number] = min(int((end - start) / step) + 1, 4000)
    if not spans:
        return None

    roster = db.scalars(
        select(MapRoster)
        .options(joinedload(MapRoster.player), joinedload(MapRoster.team))
        .where(MapRoster.match_map_id == match_map.id)
    )
    teams = {
        r.player.steamid: {
            "team": r.team.name if r.team else "",
            "name": r.display_name or r.player.name,
        }
        for r in roster
        if r.player.steamid
    }

    map_name = match_map.game_map.name if match_map.game_map else ""
    split = radar.split_altitude(map_name)
    level_keys = [level["key"] for level in radar.levels(map_name)]

    tracks = _player_tracks(pl, ticks, spans, frames_by_round, step, split)
    nades = _nade_flights(pl, frames.get("grenades"), spans, step, tickrate, split)
    effects = _effects(frames.get("smokes"), frames.get("infernos"), spans, tickrate, split)
    for number, pops in _detonations(db, match_map, spans, tickrate, split).items():
        effects.setdefault(number, []).extend(pops)
    events = _events(frames, spans, tickrate, split)
    loadouts = _loadouts(frames.get("loadout"), spans, step, frames_by_round)
    sights = _sights(frames.get("sightings"), spans, tickrate)
    steps = _steps(frames.get("footsteps"), spans, tickrate, split)
    sighted = frames.get("sightings") is not None and not frames["sightings"].is_empty()
    round_rows = {
        r.number: r
        for r in db.scalars(
            select(Round)
            .options(joinedload(Round.winner_team))
            .where(Round.match_map_id == match_map.id)
        )
    }

    db.execute(delete(ReplayRound).where(ReplayRound.match_map_id == match_map.id))
    index = []
    for number, (start, end) in sorted(spans.items()):
        payload = _round_payload(
            match_map, round_rows.get(number), number, start, end, tickrate, step,
            frames_by_round[number], tracks.get(number, {}), teams, nades.get(number, []),
            effects.get(number, []), events.get(number, []), level_keys,
            loadouts.get(number), sights.get(number, []) if sighted else None,
            steps.get(number, []),
        )  # fmt: skip
        db.add(
            ReplayRound(
                match_map_id=match_map.id,
                number=number,
                payload=gzip.compress(json.dumps(payload, separators=(",", ":")).encode(), 6),
                tokens=gzip.compress(
                    json.dumps(tokens(payload), separators=(",", ":")).encode(), 6
                ),
            )
        )
        index.append(
            {"round": number, "seconds": payload["seconds"], "players": len(payload["players"])}
        )

    db.flush()
    return {"hz": REPLAY_HZ, "rounds": index}


def tokens(payload: dict) -> dict:
    """VIZ-7: each second of the Round, how many of each Side's living Players
    stood in each Callout: ``{"places": [...], "ct": [[s, place, n], ...], "t": ...}``
    (the method of ggViz, Xenopoulos et al. 2022: a state as counts per place)."""
    hz = payload["hz"]
    places = payload["places"]
    out: dict = {"places": places, "ct": [], "t": []}
    seconds = int(payload["seconds"])
    for s in range(0, seconds + 1):
        f = s * hz
        counts: dict[tuple, int] = {}
        for p in payload["players"]:
            side = p["side"]
            if side not in ("ct", "t") or f >= len(p["hp"]) or not p["hp"][f]:
                continue
            here = None
            for frame, idx in p["place"]:
                if frame > f:
                    break
                here = idx
            if here is not None:
                counts[(side, here)] = counts.get((side, here), 0) + 1
        for (side, idx), n in counts.items():
            out[side].append([s, idx, n])
    return out


def _player_tracks(pl, ticks, spans, frames_by_round, step, split: float | None = None) -> dict:
    """``{round: {steamid: {...arrays}}}`` -- every player's path, in one pass.

    On a map with a floor split each track also carries where it changed floor,
    with :data:`radar.HYSTERESIS` keeping a man on Nuke's ramp from flickering.
    """
    live = ticks.filter(
        pl.col("X").is_not_null()
        & pl.col("Y").is_not_null()
        & pl.col("X").is_finite()
        & pl.col("Y").is_finite()
        & pl.col("round_num").is_in(list(spans))
    )
    if live.is_empty():
        return {}

    starts = {number: start for number, (start, _) in spans.items()}
    live = (
        live.with_columns(
            pl.col("round_num").replace_strict(starts, default=None).alias("_start"),
            pl.col("round_num").replace_strict(frames_by_round, default=0).alias("_n"),
        )
        .filter(pl.col("tick") >= pl.col("_start"))
        .with_columns(((pl.col("tick") - pl.col("_start")) // step).cast(pl.Int32).alias("_f"))
        .filter(pl.col("_f") < pl.col("_n"))
    )
    if live.is_empty():
        return {}

    # Altitude only travels when the map has two floors; flash_duration and yaw
    # only exist on a bundle parsed since each was requested (a graceful miss).
    wants_z = split is not None and "Z" in live.columns
    wants_blind = "flash_duration" in live.columns
    wants_yaw = "yaw" in live.columns
    extra = (
        ([pl.col("Z").first()] if wants_z else [])
        + ([pl.col("flash_duration").first()] if wants_blind else [])
        + ([pl.col("yaw").first()] if wants_yaw else [])
    )
    grid = (
        live.sort("tick")
        .group_by(["round_num", "steamid", "_f"])
        .agg(
            pl.col("X").first(),
            pl.col("Y").first(),
            pl.col("health").first(),
            pl.col("place").first(),
            pl.col("side").first(),
            pl.col("name").first(),
            *extra,
        )  # fmt: skip
        .sort(["round_num", "steamid", "_f"])
        .group_by(["round_num", "steamid"], maintain_order=True)
        .agg(
            pl.col("_f"),
            pl.col("X"),
            pl.col("Y"),
            pl.col("health"),
            pl.col("place"),
            pl.col("side").first(),
            pl.col("name").first(),
            *([pl.col("Z")] if wants_z else []),
            *([pl.col("flash_duration")] if wants_blind else []),
            *([pl.col("yaw")] if wants_yaw else []),
        )  # fmt: skip
    )

    out: dict = {}
    for row in grid.to_dicts():
        number = _i(row["round_num"])
        steamid = row["steamid"]
        if number is None or steamid is None:
            continue
        n = frames_by_round.get(number, 0)
        xs: list = [None] * n
        ys: list = [None] * n
        hp: list = [0] * n
        places: list = [None] * n
        dirs: list = [None] * n
        levels: list = []
        floor = None
        blind: list = []
        prev_blind = 0.0
        for i, frame in enumerate(row["_f"]):
            at = int(frame)
            if not 0 <= at < n:
                continue
            if wants_z:
                # A frame with no usable position is still a frame on some floor.
                now = radar.level_at(split, row["Z"][i], floor)
                if now != floor:
                    levels.append([at, _LEVEL_INDEX[now]])
                    floor = now
            if wants_yaw:
                dirs[at] = _yaw_int(row["yaw"][i])
            if wants_blind:
                # flash_duration is held at a fixed value for the whole blind
                # window, so a rising edge is the onset and the value its length.
                bd = _f(row["flash_duration"][i]) or 0.0
                if bd > 0 and bd > prev_blind + 0.01:
                    blind.append([at, round(bd, 2)])
                prev_blind = bd
            x, y = _f(row["X"][i]), _f(row["Y"][i])
            if x is None or y is None:
                continue
            xs[at], ys[at] = int(x), int(y)
            hp[at] = max(0, min(100, _i(row["health"][i]) or 0))
            places[at] = row["place"][i] or None
        out.setdefault(number, {})[str(steamid)] = {
            "x": xs, "y": ys, "hp": hp, "place": places, "lvl": levels, "blind": blind,
            "dir": dirs, "side": (row["side"] or "").lower(), "name": row["name"] or "",
        }  # fmt: skip
    return out


def _loadouts(loadout, spans, step, frames_by_round) -> dict:
    """``{round: {steamid: {"held", "inv", "gear"}}}`` -- each a list of changes.

    ``held`` is ``[frame, item]`` (``""`` for nothing in hand), ``inv`` is
    ``[frame, [item, ...]]`` and ``gear`` is ``[frame, armor, helmet, kit, money]``.
    """
    if loadout is None or loadout.is_empty():
        return {}
    out: dict = {}
    last: dict = {}
    for row in loadout.sort(["round_num", "steamid", "tick"]).iter_rows(named=True):
        number, steamid, tick = _i(row["round_num"]), row["steamid"], _i(row["tick"])
        if number not in spans or steamid is None or tick is None:
            continue
        frame = (tick - spans[number][0]) // step
        if not 0 <= frame < frames_by_round[number]:
            continue
        sid = str(steamid)
        now = {
            "held": _item(row["held"]) if row["held"] else "",
            "inv": _carried(row["inventory"]),
            "gear": [_i(row["armor"]) or 0, int(bool(row["helmet"])), int(bool(row["defuser"])),
                     _i(row["balance"]) or 0],
        }  # fmt: skip
        track = out.setdefault(number, {}).setdefault(sid, {"held": [], "inv": [], "gear": []})
        seen = last.setdefault((number, sid), {})
        for key, value in now.items():
            if seen.get(key) != value:
                track[key].append([frame, *value] if key == "gear" else [frame, value])
                seen[key] = value
    return out


def _nade_flights(pl, grenades, spans, step, tickrate, split: float | None = None) -> dict:
    """``{round: [flight, ...]}`` -- the thrown grenades, in the air, cut where they land."""
    if grenades is None or grenades.is_empty():
        return {}
    flying = grenades.filter(
        pl.col("grenade_type").str.ends_with(_PROJECTILE)
        & pl.col("round_num").is_in(list(spans))
        & pl.col("X").is_not_null()
        & pl.col("Y").is_not_null()
        & pl.col("X").is_finite()
        & pl.col("Y").is_finite()
    )
    if flying.is_empty():
        return {}

    starts = {number: start for number, (start, _) in spans.items()}
    wants_z = split is not None and "Z" in flying.columns
    flying = (
        flying.with_columns(
            pl.col("round_num").replace_strict(starts, default=None).alias("_start")
        )
        .filter(pl.col("tick") >= pl.col("_start"))
        .with_columns(((pl.col("tick") - pl.col("_start")) // step).cast(pl.Int32).alias("_f"))
        .sort("tick")
        .group_by(["round_num", "entity_id", "grenade_type"])
        .agg(
            pl.col("_f"),
            pl.col("X"),
            pl.col("Y"),
            pl.col("tick"),
            pl.col("thrower_steamid").first(),
            pl.col("thrower").first(),
            *([pl.col("Z")] if wants_z else []),
        )  # fmt: skip
    )

    out: dict = {}
    for row in flying.to_dicts():
        number = _i(row["round_num"])
        if number is None:
            continue
        kind = _NADE_KIND.get(row["grenade_type"], "nade")
        start = starts[number]
        path, seen_frame = [], None
        for i, frame in enumerate(row["_f"]):
            frame = int(frame)
            if frame == seen_frame:
                continue
            x, y = _f(row["X"][i]), _f(row["Y"][i])
            if x is None or y is None:
                continue
            if path and math.dist((x, y), (path[-1][1], path[-1][2])) < _STOPPED_UNITS:
                break  # it has landed; the rest of the entity's life is a cloud
            seen_frame = frame
            # A floor per point: a smoke thrown from Ramp into Vents changes floor.
            path.append((
                round((int(row["tick"][i]) - start) / tickrate, 2), int(x), int(y),
                _event_level(split, row["Z"][i]) if wants_z else None,
            ))  # fmt: skip
        if len(path) < 2:
            continue
        flight = {
            "kind": kind,
            "by": str(row["thrower_steamid"]) if row["thrower_steamid"] else "",
            "who": row["thrower"] or "",
            "t0": path[0][0],
            "t1": path[-1][0],
            "x": [p[1] for p in path],
            "y": [p[2] for p in path],
        }
        if wants_z:
            flight["lvl"] = [p[3] for p in path]
        out.setdefault(number, []).append(flight)
    # group_by hands groups back in no fixed order; a stored payload should not
    # depend on the hash seed of the run that built it.
    for flights in out.values():
        flights.sort(key=lambda f: (f["t0"], f["by"], f["kind"], f["x"][0], f["y"][0]))
    return out


def _effects(smokes, infernos, spans, tickrate, split: float | None = None) -> dict:
    """The clouds: a smoke and a fire are areas that live for a while."""
    out: dict = {}
    for frame, kind, radius in ((smokes, "smoke", SMOKE_RADIUS), (infernos, "fire", FIRE_RADIUS)):
        if frame is None or frame.is_empty():
            continue
        for row in frame.to_dicts():
            number = _i(row.get("round_num"))
            if number not in spans:
                continue
            x, y = _f(row.get("X")), _f(row.get("Y"))
            start_tick, end_tick = _i(row.get("start_tick")), _i(row.get("end_tick"))
            if x is None or y is None or start_tick is None:
                continue
            start = spans[number][0]
            t0 = round((start_tick - start) / tickrate, 2)
            t1 = round(((end_tick if end_tick is not None else start_tick) - start) / tickrate, 2)
            out.setdefault(number, []).append({
                "kind": kind, "x": int(x), "y": int(y), "r": radius,
                "t0": t0, "t1": max(t1, t0 + 0.5),
                "by": str(row.get("thrower_steamid") or ""),
                "side": (row.get("thrower_side") or "").lower(),
                "lvl": _event_level(split, row.get("Z")),
            })  # fmt: skip
    return out


def _detonations(db: Session, match_map: MatchMap, spans, tickrate, split=None) -> dict:
    """Flash/HE pops from ``GrenadeThrow``: the exact detonation tick, which the
    projectile's own trajectory only approximates. The one database read here."""
    from app.models import Player

    out: dict = {}
    rows = db.execute(
        select(
            Round.number, GrenadeThrow.type, GrenadeThrow.throw_tick, GrenadeThrow.x,
            GrenadeThrow.y, GrenadeThrow.z, GrenadeThrow.thrower_side, Player.steamid,
        )
        .join(Round, Round.id == GrenadeThrow.round_id)
        .outerjoin(Player, Player.id == GrenadeThrow.thrower_id)
        .where(
            Round.match_map_id == match_map.id,
            GrenadeThrow.type.in_(("flash", "he")),
            Round.number.in_(list(spans)),
        )
    )  # fmt: skip
    for number, kind, tick, gx, gy, gz, side, steamid in rows:
        x, y = _f(gx), _f(gy)
        if number not in spans or tick is None or x is None or y is None:
            continue
        t0 = round((tick - spans[number][0]) / tickrate, 2)
        seconds, radius = (
            (FLASH_POP_SECONDS, FLASH_POP_RADIUS) if kind == "flash"
            else (HE_POP_SECONDS, HE_POP_RADIUS)
        )  # fmt: skip
        out.setdefault(number, []).append({
            "kind": kind, "x": int(x), "y": int(y), "r": radius, "t0": t0, "t1": t0 + seconds,
            "by": str(steamid or ""), "side": (side or "").lower(),
            "lvl": _event_level(split, gz),
        })  # fmt: skip
    return out


def _events(frames, spans, tickrate, split: float | None = None) -> dict:
    """Kills, damages, shots and the bomb, on the round's own clock.

    A kill and a damage carry two floors, ``lvl`` for whoever did it and
    ``vlvl`` for whoever it happened to: a shot across floors is real, and rare.
    """
    out: dict = {}

    def at(number, tick):
        return round((tick - spans[number][0]) / tickrate, 2)

    kills = frames.get("kills")
    if kills is not None and not kills.is_empty():
        for row in kills.to_dicts():
            number, tick = _i(row.get("round_num")), _i(row.get("tick"))
            if number not in spans or tick is None:
                continue
            out.setdefault(number, []).append({
                "t": at(number, tick), "kind": "kill",
                "by": str(row.get("attacker_steamid") or ""),
                "at": str(row.get("victim_steamid") or ""),
                "who": row.get("attacker_name") or "", "whom": row.get("victim_name") or "",
                "weapon": _weapon(row.get("weapon")),
                "hs": bool(row.get("headshot")), "blind": bool(row.get("attackerblind")),
                "smoke": bool(row.get("thrusmoke")), "wall": bool(row.get("penetrated")),
                "assist": row.get("assister_name") or "",
                "x": _i(row.get("attacker_X")), "y": _i(row.get("attacker_Y")),
                "vx": _i(row.get("victim_X")), "vy": _i(row.get("victim_Y")),
                "side": (row.get("attacker_side") or "").lower(),
                "place": row.get("victim_place") or "",
                "lvl": _event_level(split, row.get("attacker_Z")),
                "vlvl": _event_level(split, row.get("victim_Z")),
            })  # fmt: skip

    damages = frames.get("damages")
    if damages is not None and not damages.is_empty():
        for row in damages.to_dicts():
            number, tick = _i(row.get("round_num")), _i(row.get("tick"))
            if number not in spans or tick is None:
                continue
            # dmg_health overflows the victim; dmg_health_real is what landed (H6).
            real = _i(row.get("dmg_health_real"))
            out.setdefault(number, []).append({
                "t": at(number, tick), "kind": "hurt",
                "by": str(row.get("attacker_steamid") or ""),
                "at": str(row.get("victim_steamid") or ""),
                "who": row.get("attacker_name") or "", "whom": row.get("victim_name") or "",
                "weapon": _weapon(row.get("weapon")),
                "dmg": real if real is not None else (_i(row.get("dmg_health")) or 0),
                "left": _i(row.get("health")) or 0,
                "hit": row.get("hitgroup") or "",
                "x": _i(row.get("attacker_X")), "y": _i(row.get("attacker_Y")),
                "vx": _i(row.get("victim_X")), "vy": _i(row.get("victim_Y")),
                "side": (row.get("attacker_side") or "").lower(),
                "lvl": _event_level(split, row.get("attacker_Z")),
                "vlvl": _event_level(split, row.get("victim_Z")),
            })  # fmt: skip

    shots = frames.get("shots")
    if shots is not None and not shots.is_empty():
        for row in shots.to_dicts():
            number, tick = _i(row.get("round_num")), _i(row.get("tick"))
            if number not in spans or tick is None:
                continue
            out.setdefault(number, []).append({
                "t": at(number, tick), "kind": "shot",
                "by": str(row.get("player_steamid") or ""),
                "weapon": _weapon(row.get("weapon")),
                "x": _i(row.get("player_X")), "y": _i(row.get("player_Y")),
                "side": (row.get("player_side") or "").lower(),
                "lvl": _event_level(split, row.get("player_Z")),
            })  # fmt: skip

    bomb = frames.get("bomb")
    if bomb is not None and not bomb.is_empty():
        for row in bomb.to_dicts():
            number, tick = _i(row.get("round_num")), _i(row.get("tick"))
            if number not in spans or tick is None:
                continue
            # Picking the bomb up or dropping it is not a moment in the round.
            if str(row.get("event") or "") not in ("plant", "defuse", "detonate"):
                continue
            out.setdefault(number, []).append({
                "t": at(number, tick), "kind": "bomb", "event": str(row.get("event") or ""),
                "who": row.get("name") or "", "by": str(row.get("steamid") or ""),
                "site": str(row.get("bombsite") or ""),
                "x": _i(row.get("X")), "y": _i(row.get("Y")),
                "lvl": _event_level(split, row.get("Z")),
            })  # fmt: skip

    for number in out:
        out[number].sort(key=lambda e: (e["t"], e["kind"]))
    return out


def _sights(frame, spans: dict, tickrate: int) -> dict[int, list]:
    """Round -> ``[[spotter, seen, t0, t1], ...]``: each stretch of one Player
    having an enemy in sight, in seconds after freeze end (VIZ-4). None of it on
    Tick Data without Sightings (docs/adr/0006)."""
    out: dict[int, list] = {}
    if frame is None or frame.is_empty():
        return out
    gap = int(SIGHT_GAP * tickrate)
    rows = frame.select("round_num", "tick", "steamid", "spotter").sort(
        ["round_num", "spotter", "steamid", "tick"]
    )
    for (number, spotter, seen), part in rows.group_by(
        ["round_num", "spotter", "steamid"], maintain_order=True
    ):
        number = _i(number)
        if number not in spans:
            continue
        start = spans[number][0]
        ticks = part["tick"].to_list()
        a = prev = ticks[0]
        stretches = []
        for t in ticks[1:]:
            if t - prev > gap:
                stretches.append((a, prev))
                a = t
            prev = t
        stretches.append((a, prev))
        for a, b in stretches:
            if b < start:
                continue
            out.setdefault(number, []).append(
                [str(spotter), str(seen), round((a - start) / tickrate, 2),
                 round((b - start) / tickrate + 1 / 32, 2)]
            )  # fmt: skip
    return out


def _steps(frame, spans: dict, tickrate: int, split) -> dict[int, list]:
    """Round -> ``[[steamid, t, x, y, floor], ...]``: each footstep loud enough to
    be heard (the demo's footstep events), in seconds after freeze end (VIZ-12)."""
    out: dict[int, list] = {}
    if frame is None or frame.is_empty():
        return out
    needed = {"round_num", "tick", "player_steamid", "player_X", "player_Y", "player_Z"}
    if not needed <= set(frame.columns):
        return out
    for row in frame.select(sorted(needed)).iter_rows(named=True):
        number = _i(row["round_num"])
        if number not in spans:
            continue
        start = spans[number][0]
        if row["tick"] < start:
            continue  # the freeze time: nobody is going anywhere yet
        x, y = _f(row["player_X"]), _f(row["player_Y"])
        if x is None or y is None:
            continue
        out.setdefault(number, []).append([
            str(row["player_steamid"]), round((row["tick"] - start) / tickrate, 2),
            round(x, 1), round(y, 1), _event_level(split, row["player_Z"]),
        ])  # fmt: skip
    return out


def _round_payload(
    match_map, round_row, number, start, end, tickrate, step, n_frames, tracks, teams, nades,
    effects, events, level_keys=(), loadouts=None, sights=None, steps=None,
) -> dict:  # fmt: skip
    """Assemble one round, and decide who is on screen.

    Players come from the tick stream (everyone actually in the server for this
    round, stand-ins included); the roster supplies the club name.
    """
    places: list[str] = []
    place_index: dict[str, int] = {}
    players = []
    by_side: dict[str, int] = {"ct": 0, "t": 0}
    for steamid, track in sorted(tracks.items(), key=lambda kv: kv[1]["side"] or "z"):
        side = track["side"] if track["side"] in ("ct", "t") else ""
        known = teams.get(int(steamid)) if steamid.isdigit() else None
        palette = CT_COLOURS if side == "ct" else T_COLOURS
        colour = palette[by_side.get(side, 0) % len(palette)]
        by_side[side] = by_side.get(side, 0) + 1

        # The callout changes a handful of times a round, so it travels as changes.
        changes = []
        seen = None
        for frame, place in enumerate(track["place"]):
            if place and place != seen:
                if place not in place_index:
                    place_index[place] = len(places)
                    places.append(place)
                changes.append([frame, place_index[place]])
                seen = place

        players.append({
            "sid": steamid,
            "name": (known or {}).get("name") or track["name"] or steamid,
            "team": (known or {}).get("team") or "",
            "side": side, "colour": colour,
            "x": track["x"], "y": track["y"], "hp": track["hp"],
            "dir": track.get("dir") or [None] * len(track["x"]),
            "place": changes,
            "lvl": track.get("lvl") or [],
            "blind": track.get("blind") or [],
            "weapons": [],
            # Absent when the bundle has no Loadout (parsed before it was read).
            **((loadouts or {}).get(steamid) or {}),
        })  # fmt: skip

    # Without a Loadout, the last thing a player fired is the best answer for
    # what is in their hands now.
    by_player: dict[str, list] = {}
    for event in events:
        if event["kind"] not in ("shot", "kill"):
            continue
        weapon = event.get("weapon") or ""
        who = event.get("by") or ""
        if not weapon or not who:
            continue
        seen = by_player.setdefault(who, [])
        if not seen or seen[-1][1] != weapon:
            seen.append([event["t"], weapon])
    for player in players:
        player["weapons"] = by_player.get(player["sid"], [])

    plant = next((e for e in events if e["kind"] == "bomb" and e["event"] == "plant"), None)
    return {
        "schema": REPLAY_SCHEMA,
        "round": number,
        "hz": REPLAY_HZ,
        "step": step,
        "tickrate": tickrate,
        "frames": n_frames,
        "seconds": round((end - start) / tickrate, 2),
        "map": match_map.game_map.name if match_map.game_map else "",
        "winner_side": getattr(round_row, "winner_side", "") or "",
        "winner": round_row.winner_team.name if round_row and round_row.winner_team else "",
        "reason": getattr(round_row, "end_reason", "") or "",
        "site": getattr(round_row, "bomb_site", "") or "",
        "plant_t": plant["t"] if plant else None,
        # Empty on a single-level map, which tells the page not to offer floors.
        "levels": list(level_keys),
        # Whether players carry held/inv/gear: false on Tick Data read before them.
        "loadout": bool(loadouts),
        "places": places,
        "players": players,
        "events": events,
        "nades": nades,
        "effects": effects,
        # Who had which enemy in sight, when; None without Sightings (VIZ-4).
        "sights": sights,
        # Footsteps others could hear: [steamid, t, x, y, floor] (VIZ-12).
        "steps": steps or [],
    }
