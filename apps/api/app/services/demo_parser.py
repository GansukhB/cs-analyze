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
from dataclasses import dataclass, field
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

# What every player carried, had in hand and had left, on the Replay's frame grid
# (LOADOUT_HZ is replay.REPLAY_HZ), from freeze end to the round's official end.
# Read the same way as the economy, at those ticks only: ~140 K rows and ~140 KB
# a map, against hundreds of MB were inventory a PLAYER_PROPS column.
LOADOUT_PROPS = [
    "active_weapon_name",
    "inventory",
    "armor_value",
    "has_helmet",
    "has_defuser",
    "balance",
]
LOADOUT_HZ = 8

# Sightings (CONTEXT.md): who had which enemy in view, the game's own radar
# spotting, read on a 32 Hz grid from freeze end to the round's end. Almost every
# sample is empty (no enemy in view), so only the non-empty ones are kept, one row
# per (seen, spotter): a few thousand rows a map. Measured on an Inferno demo: the
# killer had spotted the victim in the 3 s before 58% of kills, so a kill without
# a Sighting is normal (docs/adr/0006).
SIGHT_PROPS = ["approximate_spotted_by"]
SIGHT_HZ = 32

# How each player held their aim and body, on a 16 Hz grid plus every tick a shot
# was fired: pitch (yaw is already a tick prop), scoped, crouched, walking. Speed
# is not here: demoparser drops velocity on a sparse grid, and the every-tick
# positions in ``ticks`` already give it.
AIM_PROPS = ["pitch", "is_scoped", "ducking", "is_walking", "in_bomb_zone", "is_defusing"]
AIM_HZ = 16

# Schema 14 (docs/plans/02 DATA-5): what the game says that awpy drops or never
# asks for. One pass over three events (0.3 s a map): grenades as they leave the
# hand (with the exact aim; measured on a Nuke demo, only 64 of 112 smokes and 38
# of 62 flashes have one, so the throw itself comes from the trajectory, see
# projectile_starts), every item picked up (who hands the AWP to whom), every
# ping. Recorded GOTV demos carry no bomb_beginplant/bomb_begindefuse; a defuse's
# start is ``is_defusing`` on the aim grid. Like the Sightings, Tick Data without
# these is never downloaded again.
EVENT_NAMES = ["grenade_thrown", "item_pickup", "player_ping"]
EVENT_PLAYER_PROPS = ["X", "Y", "Z", "pitch", "yaw"]
# The game rules' timeout flags, read once a second over each freeze time (a
# timeout runs in the freeze time after it is called). The flags follow the
# Side, not the Team: the counts swap at half.
TIMEOUT_PROPS = ["is_terrorist_timeout", "is_ct_timeout", "is_technical_timeout"]
# awpy's projectile classes, as GrenadeType values, and the gap in ticks after
# which an entity id that came back is a new grenade.
PROJECTILE_KIND = {
    "CSmokeGrenadeProjectile": "smoke",
    "CMolotovProjectile": "inferno",
    "CFlashbangProjectile": "flash",
    "CHEGrenadeProjectile": "he",
}
PROJECTILE_GAP_TICKS = 16
# The scoreboard's own per-round numbers, read as each round's post-round ends
# (an exit frag's reward lands after the round's end; the next round resets them).
ROUND_STAT_PROPS = {
    "enemies_flashed_this_round": "enemies_flashed",
    "utility_damage_this_round": "utility_damage",
    "money_saved_this_round": "money_saved",
    "kill_reward_this_round": "kill_reward",
    "cash_earned_this_round": "cash_earned",
}

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
    loadout: pl.DataFrame  # round_num, tick, steamid and LOADOUT_PROPS at LOADOUT_HZ

    ticks: pl.DataFrame  # every player position, for routes and map shape
    roster: pl.DataFrame  # steamid, name, clan_name
    round_sides: pl.DataFrame  # round_num, ct_clan, t_clan
    player_sides: pl.DataFrame  # round_num, steamid, side
    round_totals: pl.DataFrame  # steamid, side, n_rounds

    # Schema 13. Empty when this map was read back from Tick Data that predates
    # them: nothing else depends on them (docs/adr/0006).
    sightings: pl.DataFrame = field(
        default_factory=pl.DataFrame
    )  # round_num, tick, steamid, spotter
    aim: pl.DataFrame = field(default_factory=pl.DataFrame)  # round_num, tick, steamid, AIM_PROPS
    # awpy's per-tick projectile positions (its ``grenades``), in every bundle.
    grenades: pl.DataFrame = field(default_factory=pl.DataFrame)
    # Schema 14, empty the same way as the Sightings (DATA-5).
    throws: pl.DataFrame = field(
        default_factory=pl.DataFrame
    )  # round_num, tick, steamid, weapon, X, Y, Z, pitch, yaw
    pickups: pl.DataFrame = field(default_factory=pl.DataFrame)  # round_num, tick, steamid, item
    pings: pl.DataFrame = field(
        default_factory=pl.DataFrame
    )  # round_num, tick, steamid, X, Y, Z, urgent
    timeouts: pl.DataFrame = field(default_factory=pl.DataFrame)  # round_num, ct, t, technical
    round_stats: pl.DataFrame = field(
        default_factory=pl.DataFrame
    )  # round_num, steamid, ROUND_STAT_PROPS

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


def _optional(dem, name: str) -> pl.DataFrame:
    """One of awpy's lazy event tables, empty when the demo lacks its events.

    awpy raises a ``KeyError`` for a table whose events never occurred: a short
    Demo part where nobody threw a molotov has no ``inferno_startburn`` at all.
    The empty frame is left on the Demo so ``compress()`` doesn't ask again.
    """
    try:
        return getattr(dem, name)
    except KeyError as exc:
        logger.warning("%s unavailable (%s) -- writing empty", name, exc)
        setattr(dem, name, pl.DataFrame())
        return pl.DataFrame()


# The parse's own sanity check (docs/plans DATA-8). A parser bug can return a
# Player with every position empty (demoparser2 #362, pawn index >= 2048); stored,
# it silently skews every number about him, and the Demo is deleted after the parse.
MAX_EMPTY_POSITION_SHARE = 0.5
MIN_TICKS_TO_JUDGE = 1000
MAX_SHORT_ROUND_SHARE = 0.2
FULL_ROUND_PLAYERS = 10


def quality(parsed: ParsedMap) -> tuple[list[str], list[str]]:
    """``(errors, warnings)`` about what the parse returned. An error means the
    frames can't be trusted; a warning is worth a line in the job log.

    Only Players who held a Side are judged: a spectator slot (a caster, a coach,
    another team's player watching) stays in the ticks with no Side and no
    position, and that is not a parse failure."""
    errors: list[str] = []
    warnings: list[str] = []
    ticks = parsed.ticks
    if ticks.is_empty() or parsed.rounds.is_empty():
        return ["no ticks or no rounds"], warnings
    sides = ticks.filter(pl.col("side").is_in(["ct", "t"]))
    playing = sides.select(pl.col("steamid").unique()).to_series()
    judged = (
        ticks.filter(pl.col("steamid").is_in(playing.implode()))
        .group_by("steamid", "name")
        .agg(pl.col("X").is_null().mean().alias("empty"), pl.len().alias("n"))
        .filter((pl.col("n") >= MIN_TICKS_TO_JUDGE) & (pl.col("empty") > MAX_EMPTY_POSITION_SHARE))
    )
    for row in judged.iter_rows(named=True):
        errors.append(
            f"{row['name'] or row['steamid']} has no position in {row['empty']:.0%} of their ticks"
        )
    per_round = sides.group_by("round_num").agg(pl.col("steamid").n_unique().alias("players"))
    short = per_round.filter(pl.col("players") < FULL_ROUND_PLAYERS).height
    if per_round.height and short / per_round.height > MAX_SHORT_ROUND_SHARE:
        warnings.append(f"{short} of {per_round.height} rounds have fewer than 10 players")
    return errors, warnings


def round_numbers(parsed: ParsedMap) -> pl.DataFrame:
    """``(round_num, number)``: each round as the game counted it.

    A Demo part numbers its rounds from 1 although its server resumed from a
    round backup (CONTEXT.md, docs/adr/0009). The game's own
    ``total_rounds_played`` as each round ends is the round's real number (awpy's
    ``end`` is that event's tick); a round whose end the events don't show
    follows the one before it.
    """
    totals: dict[int, int] = {}
    try:
        ends = parsed._demo.parser.parse_event("round_end", other=["total_rounds_played"])
        for tick, total in zip(ends["tick"], ends["total_rounds_played"], strict=True):
            if total == total and total:  # NaN on the pseudo-event at the start
                totals[int(tick)] = int(total)
    except Exception as exc:  # demoparser raises bare exceptions on odd demos
        logger.warning("%s: round totals unavailable (%s)", parsed.path.name, exc)
    rows, last = [], 0
    for row in parsed.rounds.sort("round_num").iter_rows(named=True):
        end = row.get("end")
        number = totals.get(int(end)) if end is not None else None
        last = number or last + 1
        rows.append((int(row["round_num"]), last))
    return pl.DataFrame(rows, schema={"round_num": pl.Int64, "number": pl.Int64}, orient="row")


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


def _loadout(dem, tickrate: int) -> pl.DataFrame:
    """Each player's Loadout, Held weapon, armor and money on the Replay's grid.

    Empty, with a warning, when demoparser cannot read them: the Replay then
    shows no Loadout, nothing else depends on it.
    """
    step = max(1, int(round(tickrate / LOADOUT_HZ)))
    grid = []
    for row in dem.rounds.iter_rows(named=True):
        start = row.get("freeze_end") or row.get("start")
        end = row.get("official_end") or row.get("end")
        if start is None or end is None or end <= start:
            continue
        grid += [(int(row["round_num"]), tick) for tick in range(int(start), int(end) + 1, step)]
    if not grid:
        return pl.DataFrame()
    at = pl.DataFrame(grid, schema={"round_num": pl.Int64, "tick": pl.Int64}, orient="row")
    try:
        frame = pl.from_pandas(dem.parser.parse_ticks(LOADOUT_PROPS, ticks=at["tick"].to_list()))
    except Exception as exc:  # demoparser raises bare exceptions on odd demos
        logger.warning("loadout unavailable (%s) -- writing empty", exc)
        return pl.DataFrame()
    if frame.is_empty():
        return pl.DataFrame()
    return (
        frame.with_columns(pl.col("tick").cast(pl.Int64))
        .join(at, on="tick")
        .select(
            "round_num",
            "tick",
            pl.col("steamid").cast(pl.UInt64),
            pl.col("active_weapon_name").alias("held"),
            "inventory",
            pl.col("armor_value").alias("armor"),
            pl.col("has_helmet").alias("helmet"),
            pl.col("has_defuser").alias("defuser"),
            "balance",
        )
    )


def _live_grid(dem, tickrate: int, hz: int) -> pl.DataFrame:
    """``(round_num, tick)`` every ``1/hz`` s from each round's freeze end to its end."""
    step = max(1, int(round(tickrate / hz)))
    grid = []
    for row in dem.rounds.iter_rows(named=True):
        start, end = row.get("freeze_end") or row.get("start"), row.get("end")
        if start is None or end is None or end <= start:
            continue
        grid += [(int(row["round_num"]), tick) for tick in range(int(start), int(end) + 1, step)]
    return pl.DataFrame(grid, schema={"round_num": pl.Int64, "tick": pl.Int64}, orient="row")


def _sightings(dem, tickrate: int) -> pl.DataFrame:
    """One row per (tick, seen player, spotter) on the :data:`SIGHT_HZ` grid.

    Empty, with a warning, when demoparser cannot read them.
    """
    at = _live_grid(dem, tickrate, SIGHT_HZ)
    if at.is_empty():
        return pl.DataFrame()
    try:
        frame = dem.parser.parse_ticks(SIGHT_PROPS, ticks=at["tick"].to_list())
    except Exception as exc:  # demoparser raises bare exceptions on odd demos
        logger.warning("sightings unavailable (%s) -- writing empty", exc)
        return pl.DataFrame()
    seen = frame[frame["approximate_spotted_by"].map(len) > 0]
    rows = [
        (int(tick), int(steamid), int(spotter))
        for tick, steamid, spotters in zip(
            seen["tick"], seen["steamid"], seen["approximate_spotted_by"], strict=True
        )
        for spotter in spotters
        if spotter
    ]
    schema = {"tick": pl.Int64, "steamid": pl.UInt64, "spotter": pl.UInt64}
    out = pl.DataFrame(rows, schema=schema, orient="row")
    return out.join(at, on="tick").select("round_num", "tick", "steamid", "spotter")


def _aim(dem, tickrate: int) -> pl.DataFrame:
    """:data:`AIM_PROPS` per player on the :data:`AIM_HZ` grid and at every shot.

    Empty, with a warning, when demoparser cannot read them.
    """
    at = _live_grid(dem, tickrate, AIM_HZ)
    fired = dem.events.get("weapon_fire") if dem.events else None
    if fired is not None and not fired.is_empty():
        live = (
            dem.rounds.select(
                pl.col("round_num").cast(pl.Int64),
                pl.col("freeze_end").cast(pl.Int64).alias("tick"),
                pl.col("end").cast(pl.Int64).alias("_end"),
            )
            .drop_nulls()
            .sort("tick")
        )
        shots = (
            fired.select(pl.col("tick").cast(pl.Int64))
            .unique()
            .sort("tick")
            .join_asof(live, on="tick", strategy="backward")
            .filter(pl.col("tick") <= pl.col("_end"))
        )
        at = pl.concat([at, shots.select("round_num", "tick")]).unique().sort("tick")
    if at.is_empty():
        return pl.DataFrame()
    try:
        frame = pl.from_pandas(dem.parser.parse_ticks(AIM_PROPS, ticks=at["tick"].to_list()))
    except Exception as exc:  # demoparser raises bare exceptions on odd demos
        logger.warning("aim unavailable (%s) -- writing empty", exc)
        return pl.DataFrame()
    if frame.is_empty():
        return pl.DataFrame()
    return (
        frame.with_columns(pl.col("tick").cast(pl.Int64))
        .join(at, on="tick")
        .select(
            "round_num",
            "tick",
            pl.col("steamid").cast(pl.UInt64),
            pl.col("pitch").cast(pl.Float32),
            pl.col("is_scoped").alias("scoped"),
            "ducking",
            pl.col("is_walking").alias("walking"),
            pl.col("in_bomb_zone").alias("in_site"),
            pl.col("is_defusing").alias("defusing"),
        )
    )


def _events(dem) -> dict[str, pl.DataFrame]:
    """:data:`EVENT_NAMES` as the ``throws``, ``pickups`` and ``pings`` tables.

    Missing ones, with a warning, when demoparser cannot read them.
    """
    import awpy.parsers.rounds

    try:
        found = dict(dem.parser.parse_events(EVENT_NAMES, player=EVENT_PLAYER_PROPS))
    except Exception as exc:  # demoparser raises bare exceptions on odd demos
        logger.warning("events unavailable (%s) -- writing none", exc)
        return {}

    def framed(name: str) -> pl.DataFrame | None:
        frame = found.get(name)
        if frame is None or len(frame) == 0:
            return None
        frame = pl.from_pandas(frame).with_columns(
            pl.col("tick").cast(pl.Int64),
            pl.col("user_steamid").cast(pl.UInt64, strict=False).alias("steamid"),
        )
        frame = awpy.parsers.rounds.apply_round_num(df=frame, rounds_df=dem.rounds, tick_col="tick")
        return frame.filter(pl.col("round_num").is_not_null() & pl.col("steamid").is_not_null())

    out = {}
    if (throws := framed("grenade_thrown")) is not None:
        out["throws"] = throws.select(
            pl.col("round_num").cast(pl.Int64),
            "tick",
            "steamid",
            "weapon",
            pl.col("user_X").alias("X"),
            pl.col("user_Y").alias("Y"),
            pl.col("user_Z").alias("Z"),
            pl.col("user_pitch").alias("pitch"),
            pl.col("user_yaw").alias("yaw"),
        )
    if (pickups := framed("item_pickup")) is not None:
        out["pickups"] = pickups.select(
            pl.col("round_num").cast(pl.Int64), "tick", "steamid", "item", "silent"
        )
    if (pings := framed("player_ping")) is not None:
        out["pings"] = pings.select(
            pl.col("round_num").cast(pl.Int64),
            "tick",
            "steamid",
            pl.col("x").alias("X"),
            pl.col("y").alias("Y"),
            pl.col("z").alias("Z"),
            "urgent",
        )
    return out


def projectile_starts(grenades: pl.DataFrame | None) -> pl.DataFrame:
    """``(round_num, tick, steamid, kind, X, Y, Z)``: each grenade's first located
    point, the moment it left the hand. Every throw has one, unlike grenade_thrown.

    An entity id comes back within a round for another grenade, so a gap of more
    than :data:`PROJECTILE_GAP_TICKS` starts a new one."""
    schema = {"round_num": pl.Int64, "tick": pl.Int64, "steamid": pl.UInt64, "kind": pl.String,
              "X": pl.Float64, "Y": pl.Float64, "Z": pl.Float64}  # fmt: skip
    if grenades is None or grenades.is_empty():
        return pl.DataFrame(schema=schema)
    key = ["round_num", "entity_id", "grenade_type", "steamid"]
    located = (
        grenades.drop_nulls(["X", "thrower_steamid", "round_num"])
        .select(
            pl.col("round_num").cast(pl.Int64),
            "entity_id",
            "grenade_type",
            pl.col("thrower_steamid").cast(pl.UInt64).alias("steamid"),
            pl.col("tick").cast(pl.Int64),
            pl.col("X").cast(pl.Float64),
            pl.col("Y").cast(pl.Float64),
            pl.col("Z").cast(pl.Float64),
        )
        .sort([*key, "tick"])
    )
    return (
        located.filter(
            pl.col("tick").diff().over(key).fill_null(PROJECTILE_GAP_TICKS + 1)
            > PROJECTILE_GAP_TICKS
        )
        .with_columns(
            pl.col("grenade_type").replace_strict(PROJECTILE_KIND, default=None).alias("kind")
        )
        .drop_nulls("kind")
        .select(list(schema))
        .sort("tick")
    )


def _timeouts(dem, tickrate: int) -> pl.DataFrame:
    """``(round_num, ct, t, technical)``: which timeouts ran in each round's freeze time.

    Empty, with a warning, when demoparser cannot read them.
    """
    grid = []
    for row in dem.rounds.iter_rows(named=True):
        start, end = row.get("start"), row.get("freeze_end")
        if start is None or end is None or end <= start:
            continue
        grid += [(int(row["round_num"]), t) for t in range(int(start), int(end) + 1, tickrate)]
    if not grid:
        return pl.DataFrame()
    at = pl.DataFrame(grid, schema={"round_num": pl.Int64, "tick": pl.Int64}, orient="row")
    try:
        frame = pl.from_pandas(dem.parser.parse_ticks(TIMEOUT_PROPS, ticks=at["tick"].to_list()))
    except Exception as exc:  # demoparser raises bare exceptions on odd demos
        logger.warning("timeouts unavailable (%s) -- writing empty", exc)
        return pl.DataFrame()
    if frame.is_empty():
        return pl.DataFrame()
    # The game rules are the same for every player row of a tick.
    return (
        frame.with_columns(pl.col("tick").cast(pl.Int64))
        .join(at, on="tick")
        .group_by("round_num")
        .agg(
            pl.col("is_ct_timeout").any().alias("ct"),
            pl.col("is_terrorist_timeout").any().alias("t"),
            pl.col("is_technical_timeout").any().alias("technical"),
        )
        .sort("round_num")
    )


def _round_stats(dem) -> pl.DataFrame:
    """``(round_num, steamid, ...)``: :data:`ROUND_STAT_PROPS` as each round's post-round ends.

    Empty, with a warning, when demoparser cannot read them.
    """
    at = []
    for row in dem.rounds.iter_rows(named=True):
        end = row.get("official_end") or row.get("end")
        if end:
            at.append((int(row["round_num"]), max(0, int(end) - 1)))
    if not at:
        return pl.DataFrame()
    ticks = pl.DataFrame(at, schema={"round_num": pl.Int64, "tick": pl.Int64}, orient="row")
    try:
        frame = pl.from_pandas(
            dem.parser.parse_ticks(list(ROUND_STAT_PROPS), ticks=ticks["tick"].to_list())
        )
    except Exception as exc:  # demoparser raises bare exceptions on odd demos
        logger.warning("round stats unavailable (%s) -- writing empty", exc)
        return pl.DataFrame()
    if frame.is_empty():
        return pl.DataFrame()
    return (
        frame.with_columns(pl.col("tick").cast(pl.Int64))
        .join(ticks, on="tick")
        .select(
            "round_num",
            pl.col("steamid").cast(pl.UInt64),
            *(pl.col(prop).cast(pl.Int64).alias(name) for prop, name in ROUND_STAT_PROPS.items()),
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
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:
        # awpy raises a wide range of parser errors, and a panic in demoparser2's
        # Rust code arrives as pyo3's PanicException, a BaseException. Uncaught, it
        # skipped every handler and left its job RUNNING with nothing behind it.
        raise DemoParseError(f"awpy could not parse {path.name}: {exc}") from exc

    if dem.rounds is None or dem.rounds.is_empty():
        raise DemoParseError(f"{path.name} has no rounds -- not a match demo?")
    if "team_clan_name" not in dem.ticks.columns:
        raise DemoParseError(
            "ticks carry no team_clan_name; the demo cannot be attributed to a team (H1)."
        )

    ticks = dem.ticks
    roster, round_sides, player_sides = sides_from_ticks(ticks)
    tickrate = derive_tickrate(dem.rounds)
    events = _events(dem)

    return ParsedMap(
        path=path,
        map_name=str(dem.header.get("map_name") or "").strip(),
        tickrate=tickrate,
        awpy_version=getattr(awpy, "__version__", "") or "",
        rounds=dem.rounds,
        ticks=ticks,
        kills=dem.kills,
        damages=dem.damages,
        bomb=_optional(dem, "bomb"),
        smokes=_optional(dem, "smokes"),
        infernos=_optional(dem, "infernos"),
        flashes=_grenade_detonation(dem, "flashbang_detonate"),
        he_grenades=_grenade_detonation(dem, "hegrenade_detonate"),
        economy=_economy(dem),
        loadout=_loadout(dem, tickrate),
        roster=roster,
        round_sides=round_sides,
        player_sides=player_sides,
        round_totals=dem.player_round_totals,
        sightings=_sightings(dem, tickrate),
        aim=_aim(dem, tickrate),
        grenades=_optional(dem, "grenades"),
        throws=events.get("throws", pl.DataFrame()),
        pickups=events.get("pickups", pl.DataFrame()),
        pings=events.get("pings", pl.DataFrame()),
        timeouts=_timeouts(dem, tickrate),
        round_stats=_round_stats(dem),
        _demo=dem,
    )
