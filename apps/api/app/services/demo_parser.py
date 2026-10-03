"""Reading a .dem with awpy, and deriving the few things awpy gets wrong.

Mirrors the split the scrapers use: this module touches awpy and polars and never
the ORM, so a demo can be parsed and inspected without a database. Writing the
result is :mod:`app.services.analysis_store`'s job.

The derivations here are not conveniences -- each fixes something measured in
``plans/ANALYZE.md``:

* the tickrate awpy reports is its own constructor default, and was 2x wrong for
  every demo tested (H10);
* ``team_clan_name`` only exists if it is explicitly requested, and without it a
  demo cannot be attached to a team at all (H1);
* which team held CT changes at half, so a round winner of ``ct`` is not a team
  until it is resolved per round (H1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)

# Requesting team_clan_name is what makes team attribution possible at all (H1);
# awpy then also adds *_team_clan_name to every event table. flash_duration is a
# per-tick player prop, not one of awpy's defaults, so without asking for it here
# the replay page has no way to know who is blind or for how long -- it is a
# fixed value assigned at the moment a flash lands and held until the effect
# ends (verified against a real demo: 0.7364s constant across ~65 ticks, then a
# hard drop to 0.0), not a live countdown, so an onset tick plus that value is
# the whole blind window. yaw is where a player is looking, in the same
# horizontal-plane degrees awpy's own plotting code uses (0 = facing +X,
# increasing counter-clockwise; see awpy.plot.plot's direction handling) -- the
# replay's facing marker is built from it. Pitch is not requested: the replay is
# a top-down view, and a look-angle marker only ever needs the horizontal one.
PLAYER_PROPS = ["team_clan_name", "flash_duration", "yaw"]

# What every player carried and had left as each round went live, read once per
# round at freeze_end straight from demoparser rather than as PLAYER_PROPS, which
# would carry them on every one of ~1.5M ticks (docs/adr/0003). Measured on real
# demos: the team totals 8 s later differ by under $500, so freeze_end is buying done.
ECONOMY_PROPS = [
    "balance",
    "current_equip_value",
    "armor_value",
    "has_helmet",
    "has_defuser",
    "inventory",
]

# Competitive CS2 freeze time, the ruler used to measure the real tickrate.
FREEZE_SECONDS = 20
# Anything longer than this is a half-time or a tactical pause, not a buy.
_MAX_NORMAL_FREEZE_TICKS = 3000

DEFAULT_TICKRATE = 64
# A trade is a revenge kill inside this many seconds of the death.
TRADE_SECONDS = 5


class DemoParseError(RuntimeError):
    """The demo could not be parsed or was missing something essential."""


@dataclass
class ParsedMap:
    """Everything one map yields, before any of it touches the database."""

    path: Path
    map_name: str
    tickrate: int
    awpy_version: str

    rounds: pl.DataFrame
    kills: pl.DataFrame
    damages: pl.DataFrame
    bomb: pl.DataFrame
    smokes: pl.DataFrame
    infernos: pl.DataFrame
    flashes: pl.DataFrame  # flashbang_detonate, one row per pop -- no start/end pair
    he_grenades: pl.DataFrame  # hegrenade_detonate, same shape as flashes
    economy: pl.DataFrame  # round_num, steamid and ECONOMY_PROPS at freeze_end

    ticks: pl.DataFrame  # every player position, for routes and map shape
    roster: pl.DataFrame  # steamid, name, clan_name
    round_sides: pl.DataFrame  # round_num, ct_clan, t_clan
    player_sides: pl.DataFrame  # round_num, steamid, side
    round_totals: pl.DataFrame  # steamid, side, n_rounds

    _demo: object = None  # the awpy Demo, kept only for compress()

    @property
    def n_rounds(self) -> int:
        return self.rounds.height

    @property
    def trade_window(self) -> int:
        return TRADE_SECONDS * self.tickrate

    def write_parquet(self, out_dir: Path) -> Path | None:
        """Dump the bulk tables via awpy's own zipped-parquet writer.

        Returns the file written, or None if awpy declined (or this map was read
        back from stored Tick Data, which has no awpy Demo behind it). This is
        the Tick Data bundle: ~9 MB against a 319 MB demo; see
        :func:`app.services.tickdata.pack`.

        ``footsteps``/``shots`` are lazy on awpy's side -- computed for the
        first time *inside* ``compress()``, from ``player_sound``/
        ``weapon_fire`` events that nothing in ``parse_map`` ever touches.
        Some demos (older Valve/FACEIT recordings mostly) carry neither event
        at all, and awpy raises a bare ``KeyError`` reaching for them
        (https://github.com/pnxenopoulos/awpy/issues/396, still open as of
        the 2.0.2 pinned here) -- which used to take the whole bundle down
        even though every table this module already forces eagerly (kills,
        damages, bomb, ticks...) had parsed cleanly, so a map could show
        correct stats and still have no replay. Priming the two properties
        here and substituting an empty frame on failure means ``compress()``
        finds an already-cached value instead of re-raising, and the bundle
        writes with those two tables empty rather than not writing at all.
        """
        if self._demo is None:
            return None
        out_dir.mkdir(parents=True, exist_ok=True)
        for lazy in ("footsteps", "shots"):
            try:
                getattr(self._demo, lazy)
            except Exception as exc:  # awpy's own KeyError, or anything else it raises
                logger.warning(
                    "%s: awpy %s unavailable (%s) -- writing empty", self.path.name, lazy, exc
                )
                setattr(self._demo, lazy, pl.DataFrame())
        before = set(out_dir.glob("*.zip"))
        self._demo.compress(outpath=out_dir)
        written = sorted(set(out_dir.glob("*.zip")) - before)
        if written:
            return written[0]
        # compress() overwrites in place on a re-parse, so nothing is "new".
        expected = out_dir / f"{self.path.stem}.zip"
        return expected if expected.exists() else None


def _grenade_detonation(dem, event_name: str) -> pl.DataFrame:
    """One row per flashbang/HE pop, shaped like awpy's own smoke/inferno tables.

    ``flashbang_detonate`` and ``hegrenade_detonate`` are already parsed into
    ``dem.events`` by the ``dem.parse()`` call in :func:`parse_map` -- they are
    in awpy's own ``default_events`` list -- so this only reshapes what is
    already there, at no extra parsing cost. Unlike smokes/infernos there is no
    paired "expire" event to join against (a flash/HE detonation is one moment,
    not a lifetime), so this reuses awpy's own "user_" -> "thrower_" rename
    directly instead of ``awpy.parsers.grenades.parse_timed_grenade_entity``,
    which requires a matching end event neither grenade type has.
    """
    import awpy.parsers.rounds
    import awpy.parsers.utils

    frame = dem.events.get(event_name)
    if frame is None or frame.is_empty():
        return pl.DataFrame()
    frame = awpy.parsers.utils.rename_columns_with_affix(
        frame, old_affix="user_", new_affix="thrower_"
    )
    frame = frame.rename({"entityid": "entity_id", "x": "X", "y": "Y", "z": "Z"})
    frame = awpy.parsers.rounds.apply_round_num(df=frame, rounds_df=dem.rounds, tick_col="tick")
    return frame.filter(pl.col("round_num").is_not_null())


def _economy(dem) -> pl.DataFrame:
    """One row per player per round: ``ECONOMY_PROPS`` as the round went live.

    Empty, with a warning, when demoparser cannot read them: the map still
    parses, it just has no Buy types.
    """
    freeze = dem.rounds.select(
        pl.col("round_num").cast(pl.Int64), pl.col("freeze_end").cast(pl.Int64).alias("tick")
    ).drop_nulls()
    if freeze.is_empty():
        return pl.DataFrame()
    try:
        frame = pl.from_pandas(
            dem.parser.parse_ticks(ECONOMY_PROPS, ticks=freeze["tick"].to_list())
        )
    except Exception as exc:  # demoparser raises bare exceptions on odd demos
        logger.warning("economy unavailable (%s) -- writing empty", exc)
        return pl.DataFrame()
    if frame.is_empty():
        return pl.DataFrame()
    return (
        frame.with_columns(pl.col("tick").cast(pl.Int64))
        .join(freeze, on="tick")
        .select(
            "round_num",
            pl.col("steamid").cast(pl.UInt64),
            "balance",
            pl.col("current_equip_value").alias("equip_value"),
            pl.col("armor_value").alias("armor"),
            pl.col("has_helmet").alias("helmet"),
            pl.col("has_defuser").alias("defuser"),
            "inventory",
        )
    )


def derive_tickrate(rounds: pl.DataFrame) -> int:
    """Measure the tickrate from freeze time instead of trusting awpy (H10).

    Freeze time is a fixed 20 s in competitive CS2, so the modal
    ``freeze_end - start`` over normal rounds divided by 20 is the tickrate.
    Half-time and pauses inflate that gap, hence the cutoff.
    """
    if rounds.is_empty():
        return DEFAULT_TICKRATE
    gaps = rounds.select((pl.col("freeze_end") - pl.col("start")).alias("f"))
    normal = gaps.filter((pl.col("f") > 0) & (pl.col("f") < _MAX_NORMAL_FREEZE_TICKS))["f"]
    if normal.is_empty():
        return DEFAULT_TICKRATE
    return max(1, int(round(normal.mode()[0] / FREEZE_SECONDS)))


def sides_from_ticks(ticks: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """``(roster, round_sides, player_sides)``, read off the tick stream.

    Shared by a parse of the Demo and a re-parse of stored Tick Data, so both
    attribute players and sides the same way.
    """
    # The tick stream is the only source that lists every player, including one
    # who never fired a shot, and it carries their club name.
    roster = (
        ticks.group_by(["steamid", "name", "team_clan_name"])
        .len()
        .sort("len", descending=True)
        .unique(subset=["steamid"], keep="first")
        .select(["steamid", "name", pl.col("team_clan_name").alias("clan_name")])
    )
    # Sides swap at half, so this is per round, not per map (H1).
    round_sides = (
        ticks.group_by(["round_num", "side", "team_clan_name"])
        .len()
        .sort("len", descending=True)
        .unique(subset=["round_num", "side"], keep="first")
        .pivot(on="side", index="round_num", values="team_clan_name", aggregate_function="first")
    )
    for side in ("ct", "t"):
        if side not in round_sides.columns:
            round_sides = round_sides.with_columns(pl.lit(None, dtype=pl.String).alias(side))
    round_sides = round_sides.select(
        "round_num", pl.col("ct").alias("ct_clan"), pl.col("t").alias("t_clan")
    )
    player_sides = (
        ticks.group_by(["round_num", "steamid", "side"])
        .len()
        .sort("len", descending=True)
        .unique(subset=["round_num", "steamid"], keep="first")
        .select(["round_num", "steamid", "side"])
    )
    return roster, round_sides, player_sides


def parse_map(path: Path) -> ParsedMap:
    """Parse one ``.dem`` into frames plus the derived facts."""
    try:
        import awpy
        from awpy import Demo
    except ImportError as exc:  # pragma: no cover - depends on install
        raise DemoParseError("awpy is not installed. Run: pip install awpy") from exc

    if not path.exists():
        raise DemoParseError(f"demo is not on disk: {path}")

    try:
        dem = Demo(path)
        dem.parse(player_props=PLAYER_PROPS)
    except Exception as exc:  # awpy raises a wide range of parser errors
        raise DemoParseError(f"awpy could not parse {path.name}: {exc}") from exc

    if dem.rounds is None or dem.rounds.is_empty():
        raise DemoParseError(f"{path.name} has no rounds -- not a match demo?")
    if "team_clan_name" not in dem.ticks.columns:
        raise DemoParseError(
            "ticks carry no team_clan_name; the demo cannot be attributed to a team (H1)."
        )

    ticks = dem.ticks
    roster, round_sides, player_sides = sides_from_ticks(ticks)

    return ParsedMap(
        path=path,
        map_name=str(dem.header.get("map_name") or "").strip(),
        tickrate=derive_tickrate(dem.rounds),
        awpy_version=getattr(awpy, "__version__", "") or "",
        rounds=dem.rounds,
        ticks=ticks,
        kills=dem.kills,
        damages=dem.damages,
        bomb=dem.bomb,
        smokes=dem.smokes,
        infernos=dem.infernos,
        flashes=_grenade_detonation(dem, "flashbang_detonate"),
        he_grenades=_grenade_detonation(dem, "hegrenade_detonate"),
        economy=_economy(dem),
        roster=roster,
        round_sides=round_sides,
        player_sides=player_sides,
        round_totals=dem.player_round_totals,
        _demo=dem,
    )
