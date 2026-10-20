"""A Match Map's Tick Data in MySQL, and what the pages need cut from it.

The parse writes awpy's zipped parquet dump; this module stores it as
``TickDataset.bundle`` (see docs/adr/0002-tick-data-in-mysql.md) and cuts three
things from it at ingest, so no page view ever opens parquet:

* ``geometry`` -- the map's callout labels (whole map and per floor), how each
  callout's ticks divide between floors, and how much of the map each floor
  holds. Heatmaps, the movement grid and the replay label their maps with it.
* ``walks`` -- every player's walk along each route on this map, simplified and
  with its comparison shape, so the movement scene can show the round somebody
  actually walked (:func:`app.services.movement.tracks`).
* the Replay -- one ``ReplayRound`` row per round (:func:`app.services.replay.build`).

The Review (:mod:`app.services.review`) is cut in the same pass but versions
itself, so changing a detector rebuilds Reviews and nothing else.

All three carry :data:`DERIVED_VERSION`; when it moves, :func:`ensure` rebuilds
them from the stored bundle instead of from a Demo nobody kept.

The bundle also holds the flashbang and HE detonations and the economy, which
awpy's dump leaves out and the ingest needs, so a stale Match Map can be parsed
again from the bundle alone (:func:`parsed_map`). A bundle written before the
economy was can't be: its map needs its Demo again (docs/adr/0003, :func:`reparseable`).

The Loadout (:data:`LOADOUT_TABLE`) is the same: Tick Data written before it
can't give it back, so its map needs its Demo again too (docs/adr/0005).

Sightings and aim (:data:`SIGHT_TABLES`, schema 13) are not: Tick Data without
them still re-parses, and its Review leaves out what needs them (docs/adr/0006,
:func:`has_sightings`).
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import math
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GrenadeThrow, MapRoster, MatchMap, Player, Round, TickDataset
from app.services import radar

logger = logging.getLogger(__name__)

# The tables awpy's compress() does not write, added to the bundle. The
# detonations can be refilled from grenade_throws (with_detonations); the
# economy and the Loadout only come from a Demo.
DETONATION_TABLES = ("flashes", "he_grenades")
ECONOMY_TABLE = "economy"
LOADOUT_TABLE = "loadout"
# A re-parse needs these; Sightings and aim it can do without (docs/adr/0006).
REQUIRED_TABLES = (*DETONATION_TABLES, ECONOMY_TABLE, LOADOUT_TABLE)
SIGHT_TABLES = ("sightings", "aim")
EXTRA_TABLES = (*REQUIRED_TABLES, *SIGHT_TABLES)

# Callout labels: the busiest places, at their median, from a fixed sample.
GEOMETRY_SAMPLE = 220_000
LABEL_MIN_SHARE = 0.004
MAX_LABELS = 12

# Walks are sampled every TRACK_TICK_STEP ticks (16 Hz at 64 tick) and simplified
# with Ramer-Douglas-Peucker at TRACK_EPSILON world units -- a player is 32 units
# wide, so the line stays inside his own footprint and never corners a wall.
TRACK_TICK_STEP = 4
TRACK_EPSILON = 8.0
# Comparison resolution when choosing which walk of a route to show.
TRACK_MEDOID_POINTS = 24
# A route is its first ROUTE_STEPS callouts, consecutive repeats collapsed --
# the same rule the ingest groups PlayerMapRoute rows by.
ROUTE_STEPS = 5

GEOMETRY_SCHEMA = 1
WALKS_SCHEMA = 1

# The Callout of a point no player's tick stood on (where a grenade landed): the
# busiest Callout of the nearest CALLOUT_CELL-unit cell players were seen in,
# within CALLOUT_REACH. Height counts double, so a floor above or below is far.
CALLOUT_CELL = 64.0
CALLOUT_REACH = 400.0
CALLOUT_SAMPLE = 200_000
_CALLOUT_BLOCK = 512.0  # > CALLOUT_REACH, so a block and its 8 neighbours cover it


def derived_version() -> str:
    from app.services import replay

    return f"{replay.REPLAY_SCHEMA}.{WALKS_SCHEMA}.{GEOMETRY_SCHEMA}"


@dataclass
class Bundle:
    """The bundle read back into frames."""

    tables: dict[str, pl.DataFrame] = field(default_factory=dict)
    header: dict = field(default_factory=dict)

    def get(self, name: str) -> pl.DataFrame | None:
        return self.tables.get(name)


# ------------------------------------------------------------- the bundle ---
def pack(parsed, scratch: Path) -> bytes | None:
    """The bytes to store for a freshly parsed map: awpy's dump plus
    :data:`EXTRA_TABLES`. The zip is written in ``scratch`` and removed again.

    A Sightings or aim table demoparser could not read is left out rather than
    written empty, so :func:`has_sightings` never claims what isn't there."""
    path = parsed.write_parquet(scratch)
    if path is None:
        return None
    try:
        with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as bundle:
            for name in EXTRA_TABLES:
                frame = getattr(parsed, name, None)
                if name in SIGHT_TABLES and (frame is None or frame.is_empty()):
                    continue
                _write_table(bundle, name, frame if frame is not None else pl.DataFrame())
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def _write_table(bundle: zipfile.ZipFile, name: str, frame: pl.DataFrame) -> None:
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    bundle.writestr(f"{name}.parquet", buffer.getvalue())


# ------------------------------------------------------------ Demo parts ---
# Every column of the bundle's tables that holds a tick.
TICK_COLUMNS = ("tick", "start", "freeze_end", "end", "official_end", "bomb_plant",
                "start_tick", "end_tick")  # fmt: skip
# Dead time between one Demo part's last tick and the next one's first.
PART_GAP_TICKS = 64 * 60


@dataclass
class Parse:
    """One Match Map read from its Demo, or from its Demo parts merged."""

    parsed: object
    bundle: bytes | None
    # Round numbers before the last one that no part holds.
    missing: list[int] = field(default_factory=list)
    # (file name, error) for each part that could not be read.
    failed: list[tuple[str, str]] = field(default_factory=list)
    # What the parse's sanity check flagged without rejecting it.
    warnings: list[str] = field(default_factory=list)


def parse_parts(
    paths: list[Path],
    scratch: Path,
    *,
    parts: bool | None = None,
    on_step: Callable[[str], None] | None = None,
) -> Parse:
    """Parse one Match Map: its Demo, or every Demo part in order, merged
    (CONTEXT.md, docs/adr/0009). ``parts`` (more than one path, unless said)
    numbers even a lone part's Rounds as played. A part that won't parse is left
    out and reported; only when none parses is it an error. ``on_step("pack")``
    is called before each bundle is written.

    Each part is packed and let go before the next is read, so a merge holds
    the parts' bundles, never two parses."""
    from app.services import demo_parser

    step = on_step or (lambda _key: None)
    warnings: list[str] = []

    def checked(path: Path):
        """The parse, refused when its frames can't be trusted (``demo_parser.quality``)."""
        parsed = demo_parser.parse_map(path)
        errors, flagged = demo_parser.quality(parsed)
        if errors:
            raise demo_parser.DemoParseError("the parse looks broken: " + "; ".join(errors))
        warnings.extend(flagged)
        return parsed

    if not (len(paths) > 1 if parts is None else parts):
        parsed = checked(paths[0])
        step("pack")
        return Parse(parsed, pack(parsed, scratch), warnings=warnings)
    parts, failed, awpy_version = [], [], ""
    for path in paths:
        try:
            parsed = checked(path)
            numbers = demo_parser.round_numbers(parsed)
            step("pack")
            blob = pack(parsed, scratch)
            awpy_version = awpy_version or parsed.awpy_version
            del parsed
        except demo_parser.DemoParseError as exc:
            failed.append((path.name, str(exc)))
            continue
        if blob is None:
            failed.append((path.name, "no tick data was written"))
            continue
        parts.append((blob, numbers))
    if not parts:
        raise demo_parser.DemoParseError(
            "no Demo part could be parsed: " + "; ".join(f"{n}: {e}" for n, e in failed)
        )
    blob, missing = merge(parts)
    parsed = parsed_map(blob, paths[0].name, awpy_version)
    return Parse(parsed, blob, missing, failed, warnings)


def merge(parts: list[tuple[bytes, pl.DataFrame]]) -> tuple[bytes, list[int]]:
    """Demo parts' bundles as one Match Map's bundle, and the Rounds none held.

    ``parts`` are ``(bundle, round_numbers)`` in order, ``round_numbers`` as
    :func:`app.services.demo_parser.round_numbers` gives them. Every Round takes
    its number as played, and the last part holding a Round plays it: a backup
    restored over Rounds already played means they were played again. Each part's
    ticks follow the one before's, :data:`PART_GAP_TICKS` apart. A Sightings or aim
    table counts only when every part has it, so :func:`has_sightings` never claims
    what a part lacked."""
    owner: dict[int, tuple[int, int]] = {}
    for i, (_blob, numbers) in enumerate(parts):
        for round_num, number in numbers.iter_rows():
            owner[int(number)] = (i, int(round_num))
    kept: dict[int, list[tuple[int, int]]] = {}
    for number, (i, round_num) in owner.items():
        kept.setdefault(i, []).append((round_num, number))

    tables: dict[str, list[pl.DataFrame]] = {}
    present: dict[str, int] = {}
    header: dict = {}
    offset = 0
    for i, (blob, _numbers) in enumerate(parts):
        bundle = read(blob)
        header = header or bundle.header
        keep = pl.DataFrame(
            kept.get(i, []), schema={"round_num": pl.Int64, "_number": pl.Int64}, orient="row"
        )
        last = 0
        for name, frame in bundle.tables.items():
            present[name] = present.get(name, 0) + 1
            last = max(last, _last_tick(frame))
            if "round_num" in frame.columns:
                kind = frame.schema["round_num"]
                frame = (
                    frame.with_columns(pl.col("round_num").cast(pl.Int64))
                    .join(keep, on="round_num", maintain_order="left")
                    .with_columns(pl.col("_number").cast(kind).alias("round_num"))
                    .drop("_number")
                )
            shifted = [c for c in TICK_COLUMNS if c in frame.columns]
            frame = frame.with_columns((pl.col(c) + offset).cast(frame.schema[c]) for c in shifted)
            tables.setdefault(name, []).append(frame)
        offset += last + PART_GAP_TICKS

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for name, frames in tables.items():
            if name in SIGHT_TABLES and present[name] < len(parts):
                continue
            _write_table(out, name, pl.concat(frames, how="diagonal_relaxed"))
        out.writestr("header.json", json.dumps(header))
    numbers = sorted(owner)
    missing = [n for n in range(1, numbers[-1]) if n not in owner] if numbers else []
    return buffer.getvalue(), missing


def _last_tick(frame: pl.DataFrame) -> int:
    values = [frame[c].max() for c in TICK_COLUMNS if c in frame.columns and frame.height]
    return max((int(v) for v in values if v is not None), default=0)


def read(blob: bytes) -> Bundle:
    out = Bundle()
    with zipfile.ZipFile(io.BytesIO(blob)) as bundle:
        for name in bundle.namelist():
            if name.endswith(".parquet"):
                out.tables[name.removesuffix(".parquet")] = pl.read_parquet(
                    io.BytesIO(bundle.read(name))
                )
            elif name == "header.json":
                out.header = json.loads(bundle.read(name) or b"{}")
    return out


def store(db: Session, match_map: MatchMap, blob: bytes, *, awpy_version: str = "") -> TickDataset:
    """Keep ``blob`` as this map's Tick Data and cut everything from it.

    Called inside the ingest's transaction, after the rows the Replay reads
    (rounds, roster, grenades) are flushed.
    """
    bundle = read(blob)
    dataset = TickDataset(
        match_map_id=match_map.id,
        bundle=blob,
        size_bytes=len(blob),
        tables=sorted(bundle.tables),
        awpy_version=awpy_version,
    )
    db.add(dataset)
    db.flush()
    derive(db, match_map, dataset, bundle)
    return dataset


def derive(db: Session, match_map: MatchMap, dataset: TickDataset, bundle: Bundle) -> None:
    from app.services import replay, review

    map_name = match_map.game_map.name if match_map.game_map else ""
    ticks = bundle.get("ticks")
    dataset.geometry = geometry(ticks, map_name) if ticks is not None else {}
    dataset.walks = gzip.compress(
        json.dumps(walks(db, match_map, bundle), separators=(",", ":")).encode(), 6
    )
    dataset.replay = replay.build(db, match_map, bundle) or {}
    dataset.derived_version = derived_version()
    db.flush()
    # The Review reads the same bundle; it keeps its own version (review.ensure).
    review.rebuild(db, match_map, bundle)


def ensure(db: Session, match_map: MatchMap) -> TickDataset | None:
    """This map's Tick Data with everything cut from it current, or None."""
    dataset = db.scalar(select(TickDataset).where(TickDataset.match_map_id == match_map.id))
    if dataset is None:
        return None
    if dataset.derived_version != derived_version():
        rebuild(db, match_map, dataset)
        db.commit()
    return dataset


def rebuild(db: Session, match_map: MatchMap, dataset: TickDataset) -> None:
    logger.info("rebuilding what is cut from the tick data of map %s", match_map.id)
    derive(db, match_map, dataset, read(dataset.bundle))


# ------------------------------------------------------------- re-parsing ---
def reparseable(dataset: TickDataset | None) -> bool:
    """Whether a stale map can be parsed again from this Tick Data, rather than
    only from its Demo downloaded again."""
    return dataset is not None and all(name in (dataset.tables or []) for name in REQUIRED_TABLES)


def has_sightings(dataset: TickDataset | None) -> bool:
    """Whether this Tick Data carries Sightings and aim (schema 13, read from a Demo)."""
    return dataset is not None and all(name in (dataset.tables or []) for name in SIGHT_TABLES)


def parsed_map(blob: bytes, label: str, awpy_version: str = ""):
    """The ingest's ``ParsedMap``, rebuilt from a stored bundle instead of a Demo.

    The bundle's tables are the very frames the original parse handed the
    ingest (awpy writes them as they are), so re-ingesting this produces the
    same rows a parse of the Demo would.
    """
    from awpy.demo import Demo as AwpyDemo

    from app.services import demo_parser

    bundle = read(blob)
    rounds, ticks = bundle.get("rounds"), bundle.get("ticks")
    if rounds is None or ticks is None or rounds.is_empty():
        raise demo_parser.DemoParseError(f"{label}: the stored tick data has no rounds or ticks")
    if any(name not in bundle.tables for name in DETONATION_TABLES):
        raise demo_parser.DemoParseError(
            f"{label}: the stored tick data lacks flash/HE detonations"
        )
    if ECONOMY_TABLE not in bundle.tables:
        raise demo_parser.DemoParseError(
            f"{label}: the stored tick data has no economy; the Demo must be downloaded again"
        )
    if LOADOUT_TABLE not in bundle.tables:
        raise demo_parser.DemoParseError(
            f"{label}: the stored tick data has no loadout; the Demo must be downloaded again"
        )
    roster, round_sides, player_sides = demo_parser.sides_from_ticks(ticks)

    def table(name: str) -> pl.DataFrame:
        frame = bundle.get(name)
        return frame if frame is not None else pl.DataFrame()

    return demo_parser.ParsedMap(
        path=Path(label),
        map_name=str(bundle.header.get("map_name") or "").strip(),
        tickrate=demo_parser.derive_tickrate(rounds),
        awpy_version=awpy_version,
        rounds=rounds,
        kills=table("kills"),
        damages=table("damages"),
        bomb=table("bomb"),
        smokes=table("smokes"),
        infernos=table("infernos"),
        flashes=table("flashes"),
        he_grenades=table("he_grenades"),
        economy=table(ECONOMY_TABLE),
        loadout=table(LOADOUT_TABLE),
        ticks=ticks,
        roster=roster,
        round_sides=round_sides,
        player_sides=player_sides,
        # awpy's own derivation, run on the same two frames it used the first time.
        round_totals=AwpyDemo.player_round_totals.func(SimpleNamespace(ticks=ticks, rounds=rounds)),
        sightings=table("sightings"),
        aim=table("aim"),
    )


def with_detonations(db: Session, match_map: MatchMap, blob: bytes) -> bytes:
    """``blob`` with flash/HE detonation tables, refilled from ``grenade_throws``.

    For bundles written before the bundle carried them: the ingest stored every
    detonation it read, so the rows hold what the tables held.
    """
    with zipfile.ZipFile(io.BytesIO(blob)) as bundle:
        if all(f"{name}.parquet" in bundle.namelist() for name in DETONATION_TABLES):
            return blob
    rows = db.execute(
        select(
            Round.number, GrenadeThrow.type, GrenadeThrow.entity_id, GrenadeThrow.throw_tick,
            Player.steamid, GrenadeThrow.thrower_side, GrenadeThrow.thrower_x,
            GrenadeThrow.thrower_y, GrenadeThrow.thrower_z, GrenadeThrow.x, GrenadeThrow.y,
            GrenadeThrow.z, GrenadeThrow.thrower_place,
        )
        .join(Round, Round.id == GrenadeThrow.round_id)
        .outerjoin(Player, Player.id == GrenadeThrow.thrower_id)
        .where(Round.match_map_id == match_map.id, GrenadeThrow.type.in_(("flash", "he")))
        .order_by(Round.number, GrenadeThrow.throw_tick)
    ).all()  # fmt: skip
    schema = {
        "round_num": pl.Int64, "entity_id": pl.Int64, "tick": pl.Int64,
        "thrower_steamid": pl.UInt64, "thrower_side": pl.String, "thrower_X": pl.Float64,
        "thrower_Y": pl.Float64, "thrower_Z": pl.Float64, "X": pl.Float64, "Y": pl.Float64,
        "Z": pl.Float64, "thrower_place": pl.String,
    }  # fmt: skip
    out = io.BytesIO(blob)
    with zipfile.ZipFile(out, "a", zipfile.ZIP_DEFLATED) as bundle:
        for name, kind in (("flashes", "flash"), ("he_grenades", "he")):
            picked = [r for r in rows if r.type == kind]
            frame = pl.DataFrame(
                {
                    "round_num": [r.number for r in picked],
                    "entity_id": [r.entity_id for r in picked],
                    "tick": [r.throw_tick for r in picked],
                    "thrower_steamid": [r.steamid for r in picked],
                    "thrower_side": [r.thrower_side or None for r in picked],
                    "thrower_X": [r.thrower_x for r in picked],
                    "thrower_Y": [r.thrower_y for r in picked],
                    "thrower_Z": [r.thrower_z for r in picked],
                    "X": [r.x for r in picked],
                    "Y": [r.y for r in picked],
                    "Z": [r.z for r in picked],
                    "thrower_place": [r.thrower_place or None for r in picked],
                },
                schema=schema,
            )
            _write_table(bundle, name, frame)
    return out.getvalue()


# --------------------------------------------------------------- geometry ---
def geometry(ticks: pl.DataFrame, map_name: str) -> dict:
    """Callout labels for the whole map and per floor, plus the floor splits.

    ``place_levels`` is ``{callout: {floor: share of its ticks}}`` -- what says a
    *room* is upstairs, downstairs or both (Nuke's Ramp is 27% lower).
    ``level_share`` is how much of the map's activity each floor holds.
    """
    if ticks is None or ticks.is_empty() or "X" not in ticks.columns:
        return {"labels": [], "level_labels": {}, "place_levels": {}, "level_share": {}}
    frame = ticks.filter(
        pl.col("X").is_not_null()
        & pl.col("Y").is_not_null()
        & pl.col("X").is_finite()
        & pl.col("Y").is_finite()
    )
    if frame.height > GEOMETRY_SAMPLE:
        frame = frame.sample(n=GEOMETRY_SAMPLE, seed=1)
    out: dict = {
        "labels": _place_labels(frame),
        "level_labels": {},
        "place_levels": {},
        "level_share": {},
    }
    split = radar.split_altitude(map_name)
    if split is None or "Z" not in frame.columns or frame.is_empty():
        return out
    for level in (radar.UPPER, radar.LOWER):
        on = (pl.col("Z") < split) if level == radar.LOWER else (pl.col("Z") >= split)
        floor = frame.filter(pl.col("Z").is_finite() & on)
        out["level_share"][level] = floor.height / frame.height
        if not floor.is_empty():
            out["level_labels"][level] = _place_labels(floor)
    out["place_levels"] = _place_levels(frame, split)
    return out


def callout_cells(ticks: pl.DataFrame | None) -> pl.DataFrame:
    """Every cell players stood in: its busiest Callout and where in it they stood."""
    if ticks is None or ticks.is_empty() or "place" not in ticks.columns:
        return pl.DataFrame()
    frame = ticks.filter(
        pl.col("place").is_not_null()
        & (pl.col("place") != "")
        & pl.col("X").is_finite()
        & pl.col("Y").is_finite()
        & pl.col("Z").is_finite()
    )
    if frame.height > CALLOUT_SAMPLE:
        frame = frame.sample(n=CALLOUT_SAMPLE, seed=1)
    return (
        frame.with_columns(
            (pl.col(axis) / CALLOUT_CELL).floor().cast(pl.Int64).alias(f"c{axis}")
            for axis in ("X", "Y", "Z")
        )
        .group_by("cX", "cY", "cZ")
        .agg(
            pl.col("place").mode().first(),
            pl.col("X").mean().alias("px"),
            pl.col("Y").mean().alias("py"),
            pl.col("Z").mean().alias("pz"),
        )
        .with_columns(
            (pl.col("px") / _CALLOUT_BLOCK).floor().cast(pl.Int64).alias("bx"),
            (pl.col("py") / _CALLOUT_BLOCK).floor().cast(pl.Int64).alias("by"),
        )
        .select("bx", "by", "px", "py", "pz", "place")
    )


def callouts_at(cells: pl.DataFrame, points: list[tuple]) -> list[str]:
    """The Callout of each ``(x, y, z)`` from :func:`callout_cells`, ``""`` if none is near."""
    found: dict[int, str] = {}
    known = [(i, p) for i, p in enumerate(points) if None not in p and all(map(math.isfinite, p))]
    if not cells.is_empty() and known:
        frame = pl.DataFrame(
            {
                "i": [i for i, _p in known],
                "x": [float(p[0]) for _i, p in known],
                "y": [float(p[1]) for _i, p in known],
                "z": [float(p[2]) for _i, p in known],
            }
        )
        around = frame.with_columns(
            (pl.col("x") / _CALLOUT_BLOCK).floor().cast(pl.Int64).alias("bx0"),
            (pl.col("y") / _CALLOUT_BLOCK).floor().cast(pl.Int64).alias("by0"),
        ).join(pl.DataFrame({"dx": [-1, 0, 1]}), how="cross").join(
            pl.DataFrame({"dy": [-1, 0, 1]}), how="cross"
        ).with_columns(
            (pl.col("bx0") + pl.col("dx")).alias("bx"), (pl.col("by0") + pl.col("dy")).alias("by")
        )  # fmt: skip
        nearest = (
            around.join(cells, on=["bx", "by"])
            .with_columns(
                (
                    (pl.col("px") - pl.col("x")) ** 2
                    + (pl.col("py") - pl.col("y")) ** 2
                    + ((pl.col("pz") - pl.col("z")) * 2) ** 2
                ).alias("d2")
            )
            .filter(pl.col("d2") <= CALLOUT_REACH**2)
            .sort("d2")
            .group_by("i")
            .first()
        )
        found = dict(zip(nearest["i"].to_list(), nearest["place"].to_list(), strict=True))
    return [found.get(i, "") for i in range(len(points))]


def _place_labels(frame: pl.DataFrame) -> list[dict]:
    if "place" not in frame.columns or frame.is_empty():
        return []
    whole = frame.height
    grouped = (
        frame.filter(pl.col("place").is_not_null() & (pl.col("place") != ""))
        .group_by("place")
        .agg(pl.len().alias("n"), pl.col("X").median().alias("x"), pl.col("Y").median().alias("y"))
        .sort(["n", "place"], descending=[True, False])
    )
    return [
        {"name": row["place"], "x": round(float(row["x"]), 1), "y": round(float(row["y"]), 1)}
        for row in grouped.head(MAX_LABELS).to_dicts()
        if row["n"] / whole >= LABEL_MIN_SHARE
        and row["x"] is not None
        and row["y"] is not None
        and math.isfinite(row["x"])
        and math.isfinite(row["y"])
    ]


def _place_levels(frame: pl.DataFrame, split: float) -> dict[str, dict[str, float]]:
    if "place" not in frame.columns:
        return {}
    rows = (
        frame.filter(
            pl.col("place").is_not_null() & (pl.col("place") != "") & pl.col("Z").is_finite()
        )
        .with_columns(
            pl.when(pl.col("Z") < split)
            .then(pl.lit(radar.LOWER))
            .otherwise(pl.lit(radar.UPPER))
            .alias("_floor")
        )
        .group_by(["place", "_floor"])
        .len()
        .to_dicts()
    )
    totals: dict[str, int] = {}
    for row in rows:
        totals[row["place"]] = totals.get(row["place"], 0) + int(row["len"])
    out: dict[str, dict[str, float]] = {}
    for row in rows:
        out.setdefault(row["place"], {})[row["_floor"]] = int(row["len"]) / (
            totals.get(row["place"]) or 1
        )
    return out


# ------------------------------------------------------------------ walks ---
def walks(db: Session, match_map: MatchMap, bundle: Bundle) -> dict[str, list]:
    """``{"player_id|side|route_key": [walk, ...]}`` -- every walk on this map.

    Grouped exactly as the ingest groups routes (same freeze cut, same collapse
    to ROUTE_STEPS), so a route's row and its walks always name the same path.
    A walk keeps the comparison shape the medoid is chosen on and the simplified
    line that is drawn, each point with its callout and, on a two-floor map, its
    floor. Corpses are dropped: the tick stream holds a body at ``health = 0``
    for the rest of the round, which is not movement.
    """
    ticks, rounds = bundle.get("ticks"), bundle.get("rounds")
    if ticks is None or rounds is None or ticks.is_empty() or "place" not in ticks.columns:
        return {}
    steamids = {
        int(steamid): player_id
        for steamid, player_id in db.execute(
            select(Player.steamid, MapRoster.player_id)
            .join(Player, Player.id == MapRoster.player_id)
            .where(MapRoster.match_map_id == match_map.id)
        )
        if steamid
    }
    if not steamids:
        return {}
    map_name = match_map.game_map.name if match_map.game_map else ""
    split = radar.split_altitude(map_name)

    freeze = {int(r["round_num"]): int(r["freeze_end"] or 0) for r in rounds.to_dicts()}
    live = (
        ticks.filter(
            pl.col("place").is_not_null()
            & (pl.col("place") != "")
            & pl.col("X").is_not_null()
            & pl.col("Y").is_not_null()
            & pl.col("X").is_finite()
            & pl.col("Y").is_finite()
            & pl.col("steamid").is_in(list(steamids))
            & (pl.col("health") > 0)
        )
        .with_columns(pl.col("round_num").replace_strict(freeze, default=0).alias("_freeze"))
        .filter(pl.col("tick") >= pl.col("_freeze"))
        .sort("tick")
    )
    if live.is_empty():
        return {}
    wants_z = split is not None and "Z" in live.columns
    grouped = live.group_by(["round_num", "steamid"], maintain_order=True).agg(
        pl.col("place").alias("places"),
        pl.col("X").alias("xs"),
        pl.col("Y").alias("ys"),
        pl.col("side").first().alias("side"),
        *([pl.col("Z").alias("zs")] if wants_z else []),
    )

    out: dict[str, list] = {}
    for row in grouped.sort(["round_num", "steamid"]).to_dicts():
        player_id = steamids.get(int(row["steamid"]))
        if player_id is None:
            continue
        places = row["places"]
        collapsed = collapse(places, ROUTE_STEPS)
        if len(collapsed) < 2:
            continue
        # The walk ends where a further callout would begin.
        cut, seen, distinct = len(places), None, 0
        for i, place in enumerate(places):
            if place != seen:
                distinct += 1
                seen = place
                if distinct > ROUTE_STEPS:
                    cut = i
                    break
        xs, ys = row["xs"][:cut], row["ys"][:cut]
        zs = row["zs"][:cut] if wants_z else None
        # The floor is carried through the sample: radar.level_at reads the point
        # before this one, which after sampling is the one the line joins.
        walk, floor = [], None
        for i in range(0, len(xs), TRACK_TICK_STEP):
            if wants_z:
                floor = radar.level_at(split, zs[i], floor)
            walk.append((float(xs[i]), float(ys[i]), places[i], floor))
        if len(walk) < 2:
            continue
        simplified = rdp(walk, TRACK_EPSILON)
        entry = {
            "shape": [[p[0], p[1]] for p in resample(walk, TRACK_MEDOID_POINTS)],
            "points": [[round(p[0], 1), round(p[1], 1)] for p in simplified],
            "places": [p[2] for p in simplified],
        }
        if wants_z:
            entry["lvl"] = [p[3] for p in simplified]
        side = (row.get("side") or "").lower()
        side = side if side in ("ct", "t") else ""
        out.setdefault(f"{player_id}|{side}|{'>'.join(collapsed)}", []).append(entry)
    return out


def load_walks(datasets) -> dict[str, list]:
    """Merge the walks of several maps' Tick Data, in the order given."""
    out: dict[str, list] = {}
    for dataset in datasets:
        if not dataset.walks:
            continue
        for key, found in json.loads(gzip.decompress(dataset.walks)).items():
            out.setdefault(key, []).extend(found)
    return out


def collapse(places, limit: int) -> list:
    """Consecutive repeats are standing still, not moving."""
    out: list = []
    for place in places:
        if not out or out[-1] != place:
            out.append(place)
        if len(out) >= limit:
            break
    return out


def rdp(points: list[tuple], epsilon: float) -> list[tuple]:
    """Ramer-Douglas-Peucker: drop points already on the line, keep the corners."""
    if len(points) < 3:
        return list(points)
    stack = [(0, len(points) - 1)]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    while stack:
        first, last = stack.pop()
        ax, ay = points[first][0], points[first][1]
        bx, by = points[last][0], points[last][1]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy)
        worst, at = -1.0, -1
        for i in range(first + 1, last):
            px, py = points[i][0], points[i][1]
            dist = (
                math.hypot(px - ax, py - ay)
                if norm == 0
                else abs(dy * px - dx * py + bx * ay - by * ax) / norm
            )
            if dist > worst:
                worst, at = dist, i
        if worst > epsilon and at > 0:
            keep[at] = True
            stack.append((first, at))
            stack.append((at, last))
    return [pt for pt, k in zip(points, keep, strict=True) if k]


def resample(points, n: int) -> list[tuple]:
    """``n`` points evenly along the index, for comparing two walks of one route."""
    if not points:
        return []
    if len(points) == 1:
        return [(points[0][0], points[0][1])] * n
    out = []
    for i in range(n):
        at = i * (len(points) - 1) / (n - 1)
        low = int(at)
        high = min(low + 1, len(points) - 1)
        frac = at - low
        out.append(
            (
                points[low][0] + (points[high][0] - points[low][0]) * frac,
                points[low][1] + (points[high][1] - points[low][1]) * frac,
            )
        )
    return out


def medoid(shapes: list[list]) -> int:
    """Index of the most typical walk -- one somebody walked, never an average,
    which is what would put a path through the box two walks passed either side of."""
    if len(shapes) == 1:
        return 0
    best, best_cost = 0, None
    for i, a in enumerate(shapes):
        cost = sum(
            sum(math.dist(p, q) for p, q in zip(a, b, strict=True))
            for j, b in enumerate(shapes)
            if i != j
        )
        if best_cost is None or cost < best_cost:
            best, best_cost = i, cost
    return best
