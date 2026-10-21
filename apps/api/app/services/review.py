"""The Review (CONTEXT.md): what decided each Round of a Match Map, and who.

Every kill, plant and defuse moves its Team's Win probability
(:mod:`app.services.winprob`); that move is the action's Swing, credited to the
Players behind it the way the Review was agreed:

* a kill's Swing goes to the killer, less a share for each teammate who had
  damaged the victim earlier in the Round (by the HP they took, at most half in
  all) and 20% for the teammate whose flash still had the victim blind;
* the victim is charged the whole of their Team's loss; a Trade wins it back
  for the trader, so an entry that is traded nets out near zero for the Team.
  A kill never takes Swing from the killer's side (the model's clock can make
  one look like a loss); a teamkill charges the teamkiller alone;
* a plant goes to the planter and is charged to the CTs alive, a defuse to the
  defuser and is charged to the Ts alive;
* Swing v2 (RV-2, after HLTV Rating 3.0 and Leetify): whatever the events left
  unassigned (the clock, a Round the bomb or the time decided) is settled at
  the end, so each Team's Players add up to exactly its Win probability's move
  over the Round. The winners share it 1x surviving, 2x for a kill that moved
  the number (after the plant only, once there is one), 1x the clutch, 1x the
  defuse; the losers alive at the end carry theirs, or all of them when none is.
  A traded death gets back 20% of the Trade's gain from the trader, and the
  teammate who could have traded and didn't takes 20% of the death's loss.

On that timeline the detectors below look for the four kinds of Finding: Key
plays, Mistakes, Missed chances and Utility effects. A Finding is stored as
structured facts (who, where, how much); :mod:`app.services.review_view` words
it, so changing a sentence never needs a rebuild.

Everything is cut from the Tick Data at ingest, like the Replay, and stored as
one gzip JSON row per Match Map (``match_map_reviews``). :func:`version` moves
with :data:`REVIEW_SCHEMA`, the Win probability model and the Spots, and
:func:`ensure` rebuilds a stale Review from the stored bundle on first read.

A Match Map whose Tick Data has no Sightings (parsed before schema 13) gets
every Finding that doesn't need them; the ones that do are marked ``sight`` and
listed in the payload's ``needs_sightings`` (docs/adr/0006). The same for the
Loadout (schema 12): ``needs_loadout`` lists :data:`LOADOUT_CODES`.
"""

from __future__ import annotations

import gzip
import json
import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    BombEvent,
    MapRoster,
    MatchMap,
    MatchMapReview,
    Player,
    PlayerRound,
    Round,
    TickDataset,
)
from app.services import spots, winprob

logger = logging.getLogger(__name__)

# Bump when the stored payload's shape or a detector changes.
# 4: the Loadout's availability, entry/big_frag rarer, lost_weapon_save not at
# a half's end, moving shots per weapon class, unscoped_awp held long enough.
# 5: Swing v2 (RV-2): every Round settled to its Win probability's move.
# 6: each Player's engagements (PL-5): time to damage, crosshair, counter-strafe.
REVIEW_SCHEMA = 6

# CONTEXT.md: a Trade is killing the killer within 5 seconds.
TRADE_SECONDS = 5.0
# Close enough to have taken a fight: two-dimensional distance, and no further
# apart in height than a staircase (another floor is not "close").
REACH = 900.0
REACH_DZ = 220.0
# Close enough to have taken the Trade: tighter without Sightings, where
# distance is all there is to go on.
TRADE_REACH = 700.0
TRADE_REACH_SEEN = 1000.0
# How far a teammate may be from a blinded enemy and still be said to have had
# the chance to punish it.
FLASH_REACH = 600.0

# Swing thresholds (fractions of a Round). A Key play needs a big positive
# Swing; a death is only a Mistake when it cost this much and has a cause.
KEY_SWING = 0.12  # a plant, defuse or clutch
# An entry is the Round's first kill, for the side that won it, worth this much:
# at 0.0 one Team in three had one every Round (7.5 per 24 over 113 Reviews,
# a tenth of them under 0.04, an opening kill in an eco). With Win probability
# v2, 0.12 leaves about 4 per 24 Rounds a Team.
ENTRY_SWING = 0.12
# Measured the same way, 0.20 and 0.33 made 8.9 big frags per 24 Rounds a Team:
# a Key play should stand out. With v2 these leave about 4.
BIG_FRAG_SWING = 0.28  # a kill on its own, by the side that won the Round
BIG_FRAG_HUGE = 0.40  # a kill on its own, whoever won
MISTAKE_SWING = 0.06
CHANCE_SWING = 0.05
SAVE_WP = 0.10  # below this the Round is lost: guns should be saved
ADVANTAGE_WP = 0.80  # a Round this far gone and still lost was thrown
ADVANTAGE_MEN = 2  # "two up" is an advantage

# Utility.
FLASH_SHARE = 0.20
# Of a Trade's gain to the death it avenged, and of an untraded death's loss to
# the teammate who could have traded (Leetify).
TRADE_SHARE = 0.20
# How a Round's unassigned Win probability is shared among its winners (HLTV
# Rating 3.0, 2025-10): weights added up per Player.
RESIDUAL_WEIGHTS = {"survived": 1.0, "killed": 2.0, "clutch": 1.0, "defuse": 1.0}
DAMAGE_SHARE_CAP = 0.50
BLIND_MEANINGFUL = 1.0  # seconds; less is a flicker
BLIND_UNPUNISHED = 2.0
TEAM_FLASH_SECONDS = 1.0
TEAM_FLASH_DEATH = 0.5
TEAM_FLASH_FINDING = 4.0  # teammate-seconds before a team flash is a Finding
UTILITY_DAMAGE_MIN = 20
MOLLY_BOMB_REACH = 220.0
EMPTY_UTILITY_MIN = 4  # flashes that blinded no enemy, at least half of theirs
# Unused utility worth naming: this much money of it, this far into the Round.
UNUSED_UTILITY_VALUE = 700
UNUSED_UTILITY_AFTER = 20.0
GRENADE_PRICE = {"Flashbang": 200, "Smoke Grenade": 300, "High Explosive Grenade": 300,
                 "Molotov": 400, "Incendiary Grenade": 500}  # fmt: skip

# Duels.
UNFINISHED_DAMAGE = 50
AWP_MISS_SECONDS = 2.0
AWP_MISS_GAP = 0.2  # a shot fired as they died is a trade of shots, not a miss
# Of the weapon's top speed, above which a shot was fired running: CS2's rifles
# lose their accuracy above about a third of it, snipers sooner, SMGs, pistols
# and shotguns are built to be shot on the move.
MOVING_SHARE = {"rifle": 0.34, "sniper": 0.25, "scout": 0.34, "smg": 0.55, "pistol": 0.55,
                "shotgun": 0.70, "mg": 0.50}  # fmt: skip
CROSSHAIR_DEGREES = 15.0
SIGHT_HOLD_SECONDS = 0.5
SIGHT_FIRST_LEAD = 0.15
# A knife or grenade in hand this long before dying is no switch made in the
# fight: the gun was away when it started. A grenade gets longer for the throw.
NO_GUN_SECONDS = {"knife": 1.0, "grenade": 1.5}
NO_GUN_LEAD = 3.0  # the Finding starts where the gun went away, at most this early
# Kills that are no duel: what the victim held changed nothing.
NOT_A_DUEL = {"hegrenade", "inferno", "molotov", "incgrenade", "flashbang", "smokegrenade",
              "decoy", "planted_c4", "c4", "world", "worldent", ""}  # fmt: skip
EYE_STANDING = 64.0
EYE_CROUCHING = 46.0

# Top speed per weapon (units/s), from the game's weapon scripts. A shot fired
# above MOVING_SHARE of it is a shot fired running.
MAX_SPEED = {
    "ak47": 215, "m4a1": 225, "m4a1_silencer": 225, "galilar": 215, "famas": 220, "aug": 220,
    "sg556": 210, "awp": 200, "ssg08": 230, "g3sg1": 215, "scar20": 215, "mac10": 240,
    "mp9": 240, "mp7": 220, "mp5sd": 235, "ump45": 230, "p90": 230, "bizon": 240,
    "nova": 220, "xm1014": 215, "mag7": 225, "sawedoff": 210, "m249": 195, "negev": 150,
    "glock": 240, "usp_silencer": 240, "hkp2000": 240, "p250": 240, "fiveseven": 240,
    "tec9": 240, "cz75a": 240, "deagle": 230, "elite": 240, "revolver": 220,
}  # fmt: skip
WEAPON_CLASS = {
    **dict.fromkeys(("ak47", "m4a1", "m4a1_silencer", "galilar", "famas", "aug", "sg556"), "rifle"),
    **dict.fromkeys(("awp", "g3sg1", "scar20"), "sniper"),
    "ssg08": "scout",
    **dict.fromkeys(("mac10", "mp9", "mp7", "mp5sd", "ump45", "p90", "bizon"), "smg"),
    **dict.fromkeys(("nova", "xm1014", "mag7", "sawedoff"), "shotgun"),
    **dict.fromkeys(("m249", "negev"), "mg"),
    **dict.fromkeys(
        (
            "glock",
            "usp_silencer",
            "hkp2000",
            "p250",
            "fiveseven",
            "tec9",
            "cz75a",
            "deagle",
            "elite",
            "revolver",
        ),
        "pistol",
    ),  # fmt: skip
}
RIFLES = {"AK-47", "M4A4", "M4A1-S", "AWP", "AUG", "SG 553", "Galil AR", "FAMAS", "SSG 08",
          "G3SG1", "SCAR-20"}  # fmt: skip
GRENADES = {"Flashbang", "Smoke Grenade", "High Explosive Grenade", "Molotov",
            "Incendiary Grenade"}  # fmt: skip
NOT_AIMING = ("knife", "bayonet", "karambit", "dagger", "grenade", "flashbang", "molotov",
              "incendiary", "decoy", "c4")  # fmt: skip
FIRE = ("inferno", "molotov", "incgrenade")
KNIVES = ("knife", "bayonet", "karambit", "dagger")

# The Findings that need Sightings (schema 13).
SIGHT_CODES = ("crosshair", "unscoped_awp", "saw_no_shot", "saw_first_lost")
# The codes that read the Loadout (schema 12): without it they never fire.
LOADOUT_CODES = ("no_gun_in_hand", "unused_utility", "unscoped_awp", "saw_no_shot")
# Engagements (PL-5, Leetify's measures): time to damage counts within this long
# of the first Sighting; a shot hits when its damage lands this many ticks after.
TTD_MAX_SECONDS = 1.0
HIT_TICKS = 3
# An AWP is a mistake unscoped only when the enemy was in sight this long first.
UNSCOPED_MIN_SECONDS = 0.5
# Regulation halves end here; overtime halves every OT_HALF after.
HALF_ENDS = (12, 24)
OT_HALF = 3
# Which kind of Finding each code is (CONTEXT.md), for readers that hold only codes.
CODE_KIND = {
    **dict.fromkeys(
        ("entry", "big_frag", "multikill", "clutch", "plant", "defuse", "retake"), "key_play"
    ),
    **dict.fromkeys(
        (
            "untraded",
            "died_in_advantage",
            "team_flashed_death",
            "no_gun_in_hand",
            "unused_utility",
            "lost_weapon_save",
            "bomb_lost",
            "awp_miss",
            "moving_shots",
            "crosshair",
            "unscoped_awp",
            "time_out",
            "kitless",
        ),
        "mistake",
    ),  # fmt: skip
    **dict.fromkeys(
        (
            "no_trade",
            "unfinished",
            "blind_unpunished",
            "advantage_lost",
            "defuse_chance",
            "saw_no_shot",
            "saw_first_lost",
        ),
        "missed_chance",
    ),  # fmt: skip
    **dict.fromkeys(
        ("flash_kill", "nade_damage_kill", "fire_delay", "team_flash", "empty_utility"), "utility"
    ),
}


def version() -> str:
    """The Review's code and model. The Spots are kept per Map apart (VIZ-11)."""
    return f"{REVIEW_SCHEMA}.{winprob.version()}"


def _map_name(match_map: MatchMap) -> str:
    return match_map.game_map.name if match_map.game_map else ""


def current(row: MatchMapReview | None, match_map: MatchMap) -> bool:
    """Whether a stored Review is at this code, model and the Map's Spots."""
    return (
        row is not None
        and row.version == version()
        and row.spots_version == spots.version(_map_name(match_map))
    )


# ---------------------------------------------------------------- storage ---
def ensure(db: Session, match_map: MatchMap, stale_ok: bool = False) -> dict | None:
    """This Match Map's Review, rebuilt first if it is missing or stale; None
    without Tick Data.

    ``stale_ok`` (a page, OPS-8): a stored Review whose detectors are this code's
    and only its model or Spots moved is served as it is, marked ``stale``, and
    the worker is asked to rebuild it, rather than holding the page for seconds.
    One cut by other detectors may not have the fields the page reads: rebuilt here.
    """
    row = db.scalar(select(MatchMapReview).where(MatchMapReview.match_map_id == match_map.id))
    if current(row, match_map):
        return json.loads(gzip.decompress(row.payload))
    if stale_ok and row is not None and row.version.split(".")[0] == str(REVIEW_SCHEMA):
        from app.services import dbctx, review_pool

        with dbctx.using(db):
            review_pool.request_refresh()
        return {**json.loads(gzip.decompress(row.payload)), "stale": True}
    built = rebuild(db, match_map)
    if built is not None:
        db.commit()
    return built


def rebuild(db: Session, match_map: MatchMap, bundle=None) -> dict | None:
    """Cut the Review from the Tick Data (``bundle`` if the caller has it read)
    and store it, in the caller's transaction."""
    from app.services import tickdata

    if bundle is None:
        dataset = db.scalar(select(TickDataset).where(TickDataset.match_map_id == match_map.id))
        if dataset is None:
            return None
        bundle = tickdata.read(tickdata.load_bundle(dataset))
    try:
        payload = build(db, match_map, bundle)
    except Exception:  # a Review must never take an ingest down with it
        logger.exception("review failed for map %s", match_map.id)
        return None
    blob = gzip.compress(json.dumps(payload, separators=(",", ":")).encode(), 6)
    row = db.scalar(select(MatchMapReview).where(MatchMapReview.match_map_id == match_map.id))
    if row is None:
        row = MatchMapReview(match_map_id=match_map.id)
        db.add(row)
    row.version = payload["version"]
    row.spots_version = spots.version(_map_name(match_map))
    row.sightings = payload["sightings"]
    row.payload = blob
    db.flush()
    return payload


# ------------------------------------------------------------ the inputs ---
@dataclass
class Track:
    """One Player through one Round, every tick."""

    ticks: np.ndarray
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    hp: np.ndarray
    yaw: np.ndarray
    fd: np.ndarray
    place: list
    side: str = ""  # from the ticks, for a Player with no player_rounds row
    blinds: list = field(default_factory=list)  # Blind episodes

    def at(self, tick: int) -> int:
        i = int(np.searchsorted(self.ticks, tick, side="right")) - 1
        return max(0, min(i, len(self.ticks) - 1))

    def pos(self, tick: int) -> tuple[float, float, float]:
        i = self.at(tick)
        return float(self.x[i]), float(self.y[i]), float(self.z[i])

    def speed(self, tick: int, rate: int) -> float:
        """Horizontal speed at ``tick``, from the positions two ticks apart."""
        i = self.at(tick)
        j = max(0, i - 2)
        dt = (self.ticks[i] - self.ticks[j]) / rate
        if dt <= 0:
            return 0.0
        return math.hypot(self.x[i] - self.x[j], self.y[i] - self.y[j]) / dt


@dataclass
class Blind:
    sid: str
    onset: int
    end: int
    seconds: float
    thrower: str | None
    flash_tick: int | None


def _f(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _sid(value) -> str | None:
    if value is None:
        return None
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return str(out) if out else None


def _weapon_key(name) -> str:
    key = (name or "").strip().lower()
    return key[len("weapon_") :] if key.startswith("weapon_") else key


def _held_kind(name) -> str:
    """'gun', 'knife', 'grenade', 'other' (the bomb, the Zeus), or '' for nothing."""
    key = (name or "").lower()
    if not key:
        return ""
    if "c4" in key or "zeus" in key or "taser" in key:
        return "other"
    if any(w in key for w in KNIVES):
        return "knife"
    if "grenade" in key or key in ("flashbang", "molotov"):
        return "grenade"
    return "gun"


def _dist(a, b) -> tuple[float, float]:
    """(2D distance, height difference)."""
    return math.hypot(a[0] - b[0], a[1] - b[1]), abs(a[2] - b[2])


def _near(a, b, reach: float = REACH) -> bool:
    d, dz = _dist(a, b)
    return d <= reach and dz <= REACH_DZ


class _Inputs:
    """Everything one build reads, indexed by Round."""

    def __init__(self, db: Session, match_map: MatchMap, bundle) -> None:
        frames = bundle.tables
        self.match_map = match_map
        self.map_name = match_map.game_map.name if match_map.game_map else ""
        self.rate = match_map.tickrate or 64
        self.sightings = all(
            name in frames and not frames[name].is_empty() for name in ("sightings", "aim")
        )
        self.has_loadout = "loadout" in frames and not frames["loadout"].is_empty()

        roster = list(
            db.scalars(
                select(MapRoster)
                .options(joinedload(MapRoster.player), joinedload(MapRoster.team))
                .where(MapRoster.match_map_id == match_map.id)
            )
        )
        self.players = {}
        pid_sid = {}
        for r in roster:
            if not r.player.steamid:
                continue
            sid = str(r.player.steamid)
            pid_sid[r.player_id] = sid
            self.players[sid] = {
                "sid": sid,
                "name": r.display_name or r.player.name,
                "team_id": r.team_id,
                "team": r.team.name if r.team else r.clan_name,
            }
        self.rounds = list(
            db.scalars(
                select(Round).where(Round.match_map_id == match_map.id).order_by(Round.number)
            )
        )
        by_id = {r.id: r.number for r in self.rounds}
        self.player_rounds: dict[int, dict[str, PlayerRound]] = defaultdict(dict)
        for pr in db.scalars(select(PlayerRound).where(PlayerRound.round_id.in_(list(by_id)))):
            sid = pid_sid.get(pr.player_id)
            if sid:
                self.player_rounds[by_id[pr.round_id]][sid] = pr
        self.bomb: dict[int, list] = defaultdict(list)
        for ev in db.execute(
            select(
                BombEvent.round_id,
                BombEvent.tick,
                BombEvent.event,
                Player.steamid,
                BombEvent.x,
                BombEvent.y,
                BombEvent.z,
            )
            .outerjoin(Player, Player.id == BombEvent.player_id)
            .where(BombEvent.round_id.in_(list(by_id)))
            .order_by(BombEvent.tick)
        ):
            self.bomb[by_id[ev.round_id]].append(
                {
                    "tick": ev.tick,
                    "event": ev.event,
                    "sid": _sid(ev.steamid),
                    "pos": (ev.x, ev.y, ev.z),
                }
            )

        self.tracks = self._tracks(frames.get("ticks"))
        self._cells = None
        self._ticks = frames.get("ticks")
        self.kills = self._rows(frames.get("kills"), self._kill)
        self.damages = self._rows(frames.get("damages"), self._damage)
        self.flashes = self._rows(frames.get("flashes"), self._pop)
        self.hes = self._rows(frames.get("he_grenades"), self._pop)
        self.infernos = self._rows(frames.get("infernos"), self._fire)
        self.shots = self._shots(frames.get("shots"))
        self.loadout = self._loadout(frames.get("loadout"))
        self.sight = self._sight(frames.get("sightings")) if self.sightings else {}
        self.aim = self._aim(frames.get("aim")) if self.sightings else {}
        for number, tracks in self.tracks.items():
            for sid, track in tracks.items():
                track.blinds = self._blinds(sid, track, self.flashes.get(number, []))

    def callout(self, pos) -> str:
        """The Callout of a point nobody stood on (where a grenade landed)."""
        from app.services import tickdata

        if pos is None or None in pos:
            return ""
        if self._cells is None:
            self._cells = tickdata.callout_cells(self._ticks)
        return tickdata.callouts_at(self._cells, [tuple(pos)])[0]

    # Each table, split by Round and made into plain rows.
    def _rows(self, frame, convert) -> dict[int, list]:
        out: dict[int, list] = defaultdict(list)
        if frame is None or frame.is_empty() or "round_num" not in frame.columns:
            return out
        for row in frame.sort("tick" if "tick" in frame.columns else "start_tick").iter_rows(
            named=True
        ):
            item = convert(row)
            if item is not None and row.get("round_num") is not None:
                out[int(row["round_num"])].append(item)
        return out

    @staticmethod
    def _kill(row) -> dict:
        return {
            "tick": int(row["tick"]),
            "attacker": _sid(row.get("attacker_steamid")),
            "victim": _sid(row.get("victim_steamid")),
            "assister": _sid(row.get("assister_steamid")),
            "attacker_side": (row.get("attacker_side") or "").lower(),
            "victim_side": (row.get("victim_side") or "").lower(),
            "weapon": _weapon_key(row.get("weapon")),
            "headshot": bool(row.get("headshot")),
            "thrusmoke": bool(row.get("thrusmoke")),
            "wallbang": int(row.get("penetrated") or 0) > 0,
            "noscope": bool(row.get("noscope")),
            "attacker_blind": bool(row.get("attackerblind")),
            "a_pos": (
                _f(row.get("attacker_X")),
                _f(row.get("attacker_Y")),
                _f(row.get("attacker_Z")),
            ),
            "v_pos": (_f(row.get("victim_X")), _f(row.get("victim_Y")), _f(row.get("victim_Z"))),
            "a_place": row.get("attacker_place") or "",
            "v_place": row.get("victim_place") or "",
            "distance": _f(row.get("distance")),
        }

    @staticmethod
    def _damage(row) -> dict:
        return {
            "tick": int(row["tick"]),
            "attacker": _sid(row.get("attacker_steamid")),
            "victim": _sid(row.get("victim_steamid")),
            "attacker_side": (row.get("attacker_side") or "").lower(),
            "victim_side": (row.get("victim_side") or "").lower(),
            "weapon": _weapon_key(row.get("weapon")),
            "dmg": int(row.get("dmg_health_real") or row.get("dmg_health") or 0),
            "hp_after": int(row.get("health") or 0),
        }

    @staticmethod
    def _pop(row) -> dict:
        return {
            "tick": int(row["tick"]),
            "thrower": _sid(row.get("thrower_steamid")),
            "side": (row.get("thrower_side") or "").lower(),
            "pos": (_f(row.get("X")), _f(row.get("Y")), _f(row.get("Z"))),
            "from": (_f(row.get("thrower_X")), _f(row.get("thrower_Y")), _f(row.get("thrower_Z"))),
            "from_place": row.get("thrower_place") or "",
        }

    @staticmethod
    def _fire(row) -> dict | None:
        if row.get("start_tick") is None:
            return None
        return {
            "start": int(row["start_tick"]),
            "end": int(row["end_tick"]) if row.get("end_tick") is not None else None,
            "thrower": _sid(row.get("thrower_steamid")),
            "side": (row.get("thrower_side") or "").lower(),
            "pos": (_f(row.get("X")), _f(row.get("Y")), _f(row.get("Z"))),
        }

    def _tracks(self, ticks) -> dict[int, dict[str, Track]]:
        out: dict[int, dict[str, Track]] = defaultdict(dict)
        if ticks is None or ticks.is_empty():
            return out
        cols = [
            "round_num",
            "steamid",
            "tick",
            "X",
            "Y",
            "Z",
            "health",
            "yaw",
            "flash_duration",
            "place",
            "side",
        ]
        frame = ticks.select([c for c in cols if c in ticks.columns]).sort("tick")
        for (number, steamid), part in frame.group_by(["round_num", "steamid"]):
            sid = _sid(steamid)
            if sid is None or number is None:
                continue
            part = part.sort("tick")
            out[int(number)][sid] = Track(
                ticks=part["tick"].to_numpy().astype(np.int64),
                x=part["X"].fill_null(np.nan).to_numpy().astype(float),
                y=part["Y"].fill_null(np.nan).to_numpy().astype(float),
                z=part["Z"].fill_null(np.nan).to_numpy().astype(float),
                hp=part["health"].fill_null(0).to_numpy().astype(float),
                yaw=(
                    part["yaw"].fill_null(0).to_numpy().astype(float)
                    if "yaw" in part.columns
                    else np.zeros(part.height)
                ),
                fd=(
                    part["flash_duration"].fill_null(0).to_numpy().astype(float)
                    if "flash_duration" in part.columns
                    else np.zeros(part.height)
                ),
                place=part["place"].fill_null("").to_list() if "place" in part.columns else [],
                side=(
                    str(part["side"].drop_nulls().mode().first() or "").lower()
                    if "side" in part.columns and part["side"].drop_nulls().len()
                    else ""
                ),
            )
        return out

    def _blinds(self, sid: str, track: Track, pops: list) -> list[Blind]:
        """Each time this Player went blind: when, for how long, whose flash."""
        out = []
        fd = track.fd
        if not len(fd):
            return out
        changed = np.flatnonzero((fd > 0) & (np.concatenate(([0.0], fd[:-1])) != fd))
        for i in changed:
            onset = int(track.ticks[i])
            seconds = float(fd[i])
            near = [p for p in pops if onset - 4 <= p["tick"] <= onset + 1]
            here = track.pos(onset)
            near.sort(
                key=lambda p: (
                    abs(onset - p["tick"]),
                    _dist(here, p["pos"])[0] if None not in p["pos"] else 1e9,
                )
            )
            pop = near[0] if near else None
            out.append(
                Blind(
                    sid=sid,
                    onset=onset,
                    end=onset + int(seconds * self.rate),
                    seconds=seconds,
                    thrower=pop["thrower"] if pop else None,
                    flash_tick=pop["tick"] if pop else None,
                )
            )
        # A new flash cuts the one before it short.
        for a, b in zip(out, out[1:], strict=False):
            a.end = min(a.end, b.onset)
        return out

    def _shots(self, frame) -> dict[int, dict[str, tuple]]:
        out: dict[int, dict[str, tuple]] = defaultdict(dict)
        if frame is None or frame.is_empty():
            return out
        frame = frame.select("round_num", "tick", "player_steamid", "weapon").sort("tick")
        for (number, steamid), part in frame.group_by(["round_num", "player_steamid"]):
            sid = _sid(steamid)
            if sid is None or number is None:
                continue
            out[int(number)][sid] = (
                part["tick"].to_numpy().astype(np.int64),
                [_weapon_key(w) for w in part["weapon"].to_list()],
            )
        return out

    def _loadout(self, frame) -> dict[int, dict[str, tuple]]:
        out: dict[int, dict[str, tuple]] = defaultdict(dict)
        if frame is None or frame.is_empty():
            return out
        frame = frame.select("round_num", "tick", "steamid", "held", "inventory").sort("tick")
        for (number, steamid), part in frame.group_by(["round_num", "steamid"]):
            sid = _sid(steamid)
            if sid is None or number is None:
                continue
            out[int(number)][sid] = (
                part["tick"].to_numpy().astype(np.int64),
                part["held"].to_list(),
                part["inventory"].to_list(),
            )
        return out

    def _sight(self, frame) -> dict[int, dict[tuple[str, str], np.ndarray]]:
        """``{round: {(spotter, seen): ticks}}``."""
        out: dict[int, dict] = defaultdict(dict)
        if frame is None or frame.is_empty():
            return out
        for (number, spotter, seen), part in frame.sort("tick").group_by(
            ["round_num", "spotter", "steamid"]
        ):
            a, b = _sid(spotter), _sid(seen)
            if a and b and number is not None:
                out[int(number)][(a, b)] = part["tick"].to_numpy().astype(np.int64)
        return out

    def _aim(self, frame) -> dict[int, dict[str, tuple]]:
        out: dict[int, dict] = defaultdict(dict)
        if frame is None or frame.is_empty():
            return out
        frame = frame.sort("tick")
        for (number, steamid), part in frame.group_by(["round_num", "steamid"]):
            sid = _sid(steamid)
            if sid is None or number is None:
                continue
            out[int(number)][sid] = (
                part["tick"].to_numpy().astype(np.int64),
                part["pitch"].fill_null(0).to_numpy().astype(float),
                part["scoped"].fill_null(False).to_numpy(),
                part["ducking"].fill_null(False).to_numpy(),
            )
        return out


# --------------------------------------------------------------- one Round ---
class _RoundReview:
    """One Round: its Win probability timeline, Swing, and Findings."""

    def __init__(self, inputs: _Inputs, rnd: Round) -> None:
        self.i = inputs
        self.rnd = rnd
        self.n = rnd.number
        self.rate = inputs.rate
        self.start = rnd.freeze_end_tick
        self.end = rnd.end_tick
        self.tracks = inputs.tracks.get(self.n, {})
        prs = inputs.player_rounds.get(self.n, {})
        self.side: dict[str, str] = {}
        for sid in self.tracks:
            pr = prs.get(sid)
            side = pr.side if pr and pr.side in ("ct", "t") else self.tracks[sid].side
            if side in ("ct", "t"):
                self.side[sid] = side
        self.equip = {
            sid: float((prs[sid].equip_value or 0) if sid in prs else 0) for sid in self.side
        }
        self.kit = {sid for sid in self.side if sid in prs and prs[sid].defuser}
        self.primary = {sid: (prs[sid].primary_weapon if sid in prs else "") for sid in self.side}
        self.kills = [k for k in inputs.kills.get(self.n, []) if k["tick"] >= self.start]
        self.damages = inputs.damages.get(self.n, [])
        self.bomb = inputs.bomb.get(self.n, [])
        self.plant = rnd.bomb_plant_tick
        self.defuse = next((b for b in self.bomb if b["event"] == "defuse"), None)
        self.planter = next((b["sid"] for b in self.bomb if b["event"] == "plant"), None)
        # When the defuse that finished began: 5 s before with a kit, 10 without.
        # From then on the bomb clock is read where it stood as the defuse began,
        # so the clock running down under a defuse that will finish is not a CT
        # loss (it read 0 there, and the defuser got the whole Round as Swing).
        self.defuse_from: int | None = None
        if self.defuse is not None and self.plant is not None:
            took = (
                winprob.DEFUSE_KIT_SECONDS
                if self.defuse.get("sid") in self.kit
                else winprob.DEFUSE_SECONDS
            )
            self.defuse_from = max(self.plant, self.defuse["tick"] - int(took * self.rate))
        self.bomb_pos = next((b["pos"] for b in self.bomb if b["event"] == "plant"), None)
        self.findings: list[dict] = []
        self.swing: dict[str, float] = defaultdict(float)
        self.wp: list[list] = []
        self.events: list[dict] = []

    # -- helpers ----------------------------------------------------------
    def t(self, tick: int) -> float:
        return round((tick - self.start) / self.rate, 2)

    def team(self, side: str) -> int | None:
        return self.rnd.ct_team_id if side == "ct" else self.rnd.t_team_id

    def won(self, side: str) -> bool:
        return self.rnd.winner_side == side

    def pos(self, sid: str, tick: int):
        track = self.tracks.get(sid)
        return track.pos(tick) if track else (None, None, None)

    def place(self, sid: str, tick: int) -> str:
        track = self.tracks.get(sid)
        if not track or not track.place:
            return ""
        return track.place[track.at(tick)] or ""

    def spot(self, sid: str | None, tick: int, pos=None, place=None) -> str:
        if sid is None and place is None and pos is not None and None not in pos:
            place = self.i.callout(pos)
        if pos is None or None in pos:
            if sid is None:
                return spots.callout_label(place)
            pos = self.pos(sid, tick)
            place = place or self.place(sid, tick)
        if None in pos or any(v != v for v in pos):
            return spots.callout_label(place)
        return spots.spot_at(self.i.map_name, pos[0], pos[1], pos[2], place)

    def alive_at(self, tick: int, inclusive: bool = False) -> set[str]:
        """Who is alive just before ``tick`` (or just after, ``inclusive``)."""
        dead = {
            k["victim"]
            for k in self.kills
            if (k["tick"] <= tick if inclusive else k["tick"] < tick)
        }
        return {sid for sid in self.side if sid not in dead}

    def state(self, alive: set[str], tick: int) -> winprob.State:
        planted = self.plant is not None and tick >= self.plant
        defusing = (
            planted
            and self.defuse_from is not None
            and self.defuse_from <= tick <= self.defuse["tick"]
        )
        if planted:
            at = self.defuse_from if defusing else tick
            left = winprob.BOMB_SECONDS - (at - self.plant) / self.rate
        else:
            left = winprob.ROUND_SECONDS - (tick - self.start) / self.rate
        ct = [s for s in alive if self.side.get(s) == "ct"]
        t = [s for s in alive if self.side.get(s) == "t"]
        return winprob.State(
            ct_alive=len(ct),
            t_alive=len(t),
            ct_equip=sum(self.equip.get(s, 0.0) for s in ct),
            t_equip=sum(self.equip.get(s, 0.0) for s in t),
            planted=planted,
            seconds_left=left,
            ct_kits=sum(1 for s in ct if s in self.kit),
            map_name=self.i.map_name,
            defusing=defusing,
            ct_hp=sum(self._hp(s, tick) for s in ct),
            t_hp=sum(self._hp(s, tick) for s in t),
            ct_util=sum(self._util(s, tick) for s in ct),
            t_util=sum(self._util(s, tick) for s in t),
            last=self._last_kill(alive, tick),
            race=self._race(ct, tick, left) if planted and not defusing else None,
            ct_buy=self.rnd.ct_buy or "",
            t_buy=self.rnd.t_buy or "",
        )

    # -- Win probability v2's reads (RV-4) -------------------------------
    def _hp(self, sid: str, tick: int) -> float:
        """Health just before ``tick``: at a kill's own tick the victim already
        reads 0, which would hand the killer the duel before he won it."""
        track = self.tracks.get(sid)
        if track is None or not len(track.ticks):
            return 100.0
        return float(track.hp[track.at(tick - 1)])

    def _util(self, sid: str, tick: int) -> int:
        _held, inv = self.loadout_at(sid, tick)
        return sum(1 for x in inv if x in GRENADES)

    def _last_kill(self, alive: set[str], tick: int) -> int:
        """+1 if the CTs made the last kill already counted in ``alive``, -1 the Ts."""
        for k in reversed(self.kills):
            if k["tick"] > tick or k["victim"] in alive:
                continue
            side = self.side.get(k["attacker"]) if k["attacker"] else None
            if side and side != self.side.get(k["victim"]):
                return 1 if side == "ct" else -1
        return 0

    def _race(self, cts: list[str], tick: int, left: float) -> float | None:
        """The bomb's clock less the quickest defuse a living CT can reach: his run
        to the bomb and his defuse, kit or not."""
        if self.bomb_pos is None or None in self.bomb_pos or not cts:
            return None
        best = None
        for sid in cts:
            pos = self.pos(sid, tick)
            if None in pos or any(v != v for v in pos):
                continue
            far = math.dist(pos, self.bomb_pos)
            need = far / winprob.RUN_SPEED + (
                winprob.DEFUSE_KIT_SECONDS if sid in self.kit else winprob.DEFUSE_SECONDS
            )
            best = need if best is None else min(best, need)
        return None if best is None else left - best

    def sample_states(self) -> list[winprob.State]:
        """The states the Win probability model is fitted on: as the Round went
        live, after each kill and the plant, and every SAMPLE_EVERY_SECONDS."""
        moments = {self.start}
        moments |= {k["tick"] for k in self.kills if self.start <= k["tick"] <= self.end}
        if self.plant is not None and self.start <= self.plant <= self.end:
            moments.add(self.plant + 1)
        step = max(1, int(winprob.SAMPLE_EVERY_SECONDS * self.rate))
        moments |= set(range(self.start, self.end, step))
        return [self.state(self.alive_at(t, inclusive=True), t) for t in sorted(moments)]

    def wp_ct(self, alive: set[str], tick: int) -> float:
        return winprob.ct_win(self.state(alive, tick))

    def blind_at(self, sid: str, tick: int) -> Blind | None:
        track = self.tracks.get(sid)
        if not track:
            return None
        for b in track.blinds:
            if b.onset <= tick <= b.end:
                return b
        return None

    def loadout_at(self, sid: str, tick: int) -> tuple[str, list]:
        found = self.i.loadout.get(self.n, {}).get(sid)
        if not found:
            return "", []
        ticks, held, inv = found
        i = int(np.searchsorted(ticks, tick, side="right")) - 1
        if i < 0:
            return "", []
        return held[i] or "", list(inv[i] or [])

    def shots_between(self, sid: str, t0: int, t1: int) -> list[tuple[int, str]]:
        found = self.i.shots.get(self.n, {}).get(sid)
        if not found:
            return []
        ticks, weapons = found
        lo = int(np.searchsorted(ticks, t0, side="left"))
        hi = int(np.searchsorted(ticks, t1, side="right"))
        return [(int(ticks[j]), weapons[j]) for j in range(lo, hi)]

    def damage(self, attacker: str, victim: str, t0: int, t1: int) -> int:
        return sum(
            d["dmg"]
            for d in self.damages
            if d["attacker"] == attacker and d["victim"] == victim and t0 <= d["tick"] <= t1
        )

    def seen_ticks(self, spotter: str, seen: str) -> np.ndarray:
        return self.i.sight.get(self.n, {}).get((spotter, seen), np.empty(0, dtype=np.int64))

    def first_seen(self, spotter: str, seen: str, t0: int, t1: int) -> int | None:
        ticks = self.seen_ticks(spotter, seen)
        lo = int(np.searchsorted(ticks, t0, side="left"))
        return int(ticks[lo]) if lo < len(ticks) and ticks[lo] <= t1 else None

    def aim_at(self, sid: str, tick: int):
        found = self.i.aim.get(self.n, {}).get(sid)
        if not found:
            return None
        ticks, pitch, scoped, ducking = found
        i = int(np.searchsorted(ticks, tick, side="right")) - 1
        if i < 0:
            return None
        return float(pitch[i]), bool(scoped[i]), bool(ducking[i])

    def add(
        self,
        kind: str,
        code: str,
        tick: int,
        sids: list[str],
        swing: float,
        sight: bool = False,
        **facts,
    ) -> None:
        main = sids[0] if sids else None
        side = self.side.get(main, "") if main else facts.get("side", "")
        self.findings.append(
            {
                "id": f"r{self.n}-{len(self.findings) + 1}",
                "kind": kind,
                "code": code,
                "round": self.n,
                "tick": int(tick),
                "t": self.t(tick),
                "side": side,
                "team_id": self.team(side) if side else None,
                "sids": [s for s in sids if s],
                "swing": round(float(swing), 4),
                "sight": sight,
                "facts": facts,
            }
        )

    # -- the timeline ----------------------------------------------------
    def timeline(self) -> None:
        """Win probability through the Round, each event's Swing and who gets it."""
        live = [k for k in self.kills if k["tick"] <= self.end]
        events = [(k["tick"], 0, "kill", k) for k in live]
        if self.plant is not None and self.start <= self.plant <= self.end:
            events.append((self.plant, 1, "plant", None))
        if self.defuse is not None:
            events.append((self.defuse["tick"], 2, "defuse", self.defuse))
        events.sort(key=lambda e: (e[0], e[1]))

        alive = set(self.side)
        self._start_wp = self.wp_ct(alive, self.start)
        self.wp.append([0.0, round(self._start_wp, 4)])
        step = int(2 * self.rate)
        cursor = self.start + step
        first_kill = True
        for tick, _order, kind, item in events:
            while cursor < tick:
                self.wp.append([self.t(cursor), round(self.wp_ct(alive, cursor), 4)])
                cursor += step
            before = self.wp_ct(alive, tick - 1 if kind == "plant" else tick)
            if kind == "kill":
                alive.discard(item["victim"])
                after = self.wp_ct(alive, tick)
                self._credit_kill(item, before, after, first_kill)
                first_kill = False
            elif kind == "plant":
                after = self.wp_ct(alive, tick + 1)
                if self.planter:
                    self.swing[self.planter] += before - after
                self._share([s for s in alive if self.side.get(s) == "ct"], after - before)
                self.events.append(
                    {
                        "t": self.t(tick),
                        "kind": "plant",
                        "sid": self.planter,
                        "d_ct": round(after - before, 4),
                    }
                )
                self._plant = {"tick": tick, "before": before, "after": after, "alive": set(alive)}
            else:
                after = 1.0
                sid = item.get("sid")
                if sid:
                    self.swing[sid] += after - before
                self._share([s for s in alive if self.side.get(s) == "t"], before - after)
                self.events.append(
                    {
                        "t": self.t(tick),
                        "kind": "defuse",
                        "sid": sid,
                        "d_ct": round(after - before, 4),
                    }
                )
                self._defuse = {"tick": tick, "before": before, "alive": set(alive)}
            self.wp.append([self.t(tick), round(after, 4)])
        while cursor < self.end:
            self.wp.append([self.t(cursor), round(self.wp_ct(alive, cursor), 4)])
            cursor += step
        final = 1.0 if self.rnd.winner_side == "ct" else 0.0
        self.wp.append([self.t(self.end), final])
        for k in self.kills:
            if k["tick"] > self.end:
                k["post"] = True
                k["d_team"] = 0.0
                k["credits"] = {}
                k["wp_ct_before"] = final
                k["alive_before"] = (0, 0)

    def _share(self, sids: list[str], amount: float) -> None:
        """``amount`` split evenly among ``sids``."""
        for s in sids:
            self.swing[s] += amount / len(sids)

    def _credit_kill(self, k: dict, before: float, after: float, opening: bool) -> None:
        attacker, victim = k["attacker"], k["victim"]
        a_side = self.side.get(attacker) or k["attacker_side"]
        v_side = self.side.get(victim) or k["victim_side"]
        d_ct = after - before
        k["wp_ct_before"], k["wp_ct_after"] = before, after
        k["opening"] = opening
        alive = self.alive_at(k["tick"])
        k["alive_before"] = (
            sum(1 for s in alive if self.side.get(s) == "ct"),
            sum(1 for s in alive if self.side.get(s) == "t"),
        )
        credits: dict[str, float] = defaultdict(float)
        victim_loss = d_ct if v_side == "ct" else -d_ct  # negative for the victim's team
        enemy = bool(attacker and a_side and a_side != v_side)
        # A kill never costs the killer's side; what the model moved is left to settle().
        if enemy and victim_loss > 0:
            victim_loss = 0.0
        # A teamkill is the teamkiller's loss alone.
        teamkill = bool(attacker and attacker != victim and a_side == v_side)
        if victim and not teamkill:
            credits[victim] += victim_loss
        if enemy:
            gain = -victim_loss
            shares: dict[str, float] = defaultdict(float)
            for d in self.damages:
                if (
                    d["victim"] == victim
                    and d["tick"] <= k["tick"]
                    and d["attacker"]
                    and d["attacker"] != attacker
                    and self.side.get(d["attacker"]) == a_side
                ):
                    shares[d["attacker"]] += d["dmg"] / 100.0
            total = sum(shares.values())
            if total > DAMAGE_SHARE_CAP:
                shares = {s: v * DAMAGE_SHARE_CAP / total for s, v in shares.items()}
            blind = self.blind_at(victim, k["tick"]) if victim else None
            flasher = None
            if (
                blind
                and blind.seconds >= BLIND_MEANINGFUL
                and blind.thrower
                and blind.thrower != attacker
                and self.side.get(blind.thrower) == a_side
            ):
                flasher = blind.thrower
                shares[flasher] = shares.get(flasher, 0.0) + FLASH_SHARE
            k["flasher"] = flasher
            k["blind_by"] = blind.thrower if blind else None
            k["assist_shares"] = {s: round(v, 3) for s, v in shares.items()}
            shared = sum(shares.values())
            rest = max(0.3, 1.0 - shared)
            scale = (1.0 - rest) / shared if shared > 0 else 0.0
            credits[attacker] += gain * rest
            for s, v in shares.items():
                credits[s] += gain * v * scale
            k["d_team"] = gain
        else:
            # A teamkill: the teamkiller carries the loss. The bomb, a fall: the victim.
            if teamkill:
                credits[attacker] += victim_loss
            k["d_team"] = victim_loss
            k["flasher"] = None
            k["blind_by"] = None
            k["assist_shares"] = {}
        k["credits"] = dict(credits)
        for s, v in credits.items():
            self.swing[s] += v
        self.events.append(
            {
                "t": self.t(k["tick"]),
                "kind": "kill",
                "sid": attacker,
                "victim": victim,
                "d_ct": round(d_ct, 4),
                "hs": k["headshot"],
                "weapon": k["weapon"],
            }
        )

    # -- trades -------------------------------------------------------------
    def trades(self) -> None:
        window = int(TRADE_SECONDS * self.rate)
        for k in self.kills:
            k["traded_by"] = None
        for i, k in enumerate(self.kills):
            if not k["attacker"] or k.get("post"):
                continue
            v_side = self.side.get(k["victim"])
            for later in self.kills[i + 1 :]:
                if later["tick"] - k["tick"] > window:
                    break
                if later["victim"] == k["attacker"] and self.side.get(later["attacker"]) == v_side:
                    k["traded_by"] = later["attacker"]
                    later["trade_of"] = k["victim"]
                    break

    # -- Key plays ----------------------------------------------------------
    def key_plays(self) -> None:
        winner = self.rnd.winner_side
        live = [k for k in self.kills if not k.get("post")]
        by_player: dict[str, list] = defaultdict(list)
        for k in live:
            if k["attacker"] and self.side.get(k["attacker"]) != self.side.get(k["victim"]):
                by_player[k["attacker"]].append(k)
        claimed: set[int] = set()

        # Clutch: the last one alive on their Team, against at least one, and won.
        for sid, side in self.side.items():
            if side != winner:
                continue
            mates = [s for s, sd in self.side.items() if sd == side and s != sid]
            deaths = {k["victim"]: k["tick"] for k in live}
            if sid in deaths or not mates or not all(m in deaths for m in mates):
                continue
            alone_from = max(deaths[m] for m in mates)
            enemies = [
                s
                for s, sd in self.side.items()
                if sd != side and deaths.get(s, self.end + 1) > alone_from
            ]
            if not enemies:
                continue
            mine = [k for k in by_player.get(sid, []) if k["tick"] > alone_from]
            swing = sum(k["credits"].get(sid, 0.0) for k in mine)
            defused = self.defuse is not None and self.defuse.get("sid") == sid
            if defused:
                swing += 1.0 - self._defuse["before"]
            claimed |= {id(k) for k in mine}
            self.add(
                "key_play",
                "clutch",
                alone_from,
                [sid],
                swing,
                vs=len(enemies),
                kills=len(mine),
                defused=defused,
                victims=[k["victim"] for k in mine],
                spot=self.spot(sid, mine[-1]["tick"] if mine else alone_from),
            )

        # Multi-kill: three or more in the Round, for the side that won it.
        for sid, ks in by_player.items():
            if len(ks) < 3 or self.side.get(sid) != winner:
                continue
            if all(id(k) in claimed for k in ks):
                continue
            swing = sum(k["credits"].get(sid, 0.0) for k in ks)
            if swing < KEY_SWING:
                continue  # exit kills in a Round already won
            claimed |= {id(k) for k in ks}
            self.add(
                "key_play",
                "multikill",
                ks[0]["tick"],
                [sid],
                swing,
                kills=len(ks),
                seconds=round((ks[-1]["tick"] - ks[0]["tick"]) / self.rate, 1),
                headshots=sum(1 for k in ks if k["headshot"]),
                victims=[k["victim"] for k in ks],
                spot=self.spot(sid, ks[0]["tick"], k_pos(ks[0]), ks[0]["a_place"]),
            )

        # Entry: the Round's first kill, for the side that won it.
        if live and live[0]["attacker"] and id(live[0]) not in claimed:
            k = live[0]
            sid = k["attacker"]
            if (
                self.side.get(sid) == winner
                and self.side.get(k["victim"]) != winner
                and k["credits"].get(sid, 0.0) >= ENTRY_SWING
            ):
                claimed.add(id(k))
                self.add(
                    "key_play",
                    "entry",
                    k["tick"],
                    [sid, k["victim"]],
                    k["credits"].get(sid, 0.0),
                    **self._kill_facts(k),
                )

        # Any other kill that swung the Round on its own.
        for k in live:
            sid = k["attacker"]
            if not sid or id(k) in claimed or self.side.get(sid) == self.side.get(k["victim"]):
                continue
            gain = k["credits"].get(sid, 0.0)
            if gain >= BIG_FRAG_HUGE or (gain >= BIG_FRAG_SWING and self.side.get(sid) == winner):
                claimed.add(id(k))
                self.add(
                    "key_play",
                    "big_frag",
                    k["tick"],
                    [sid, k["victim"]],
                    gain,
                    **self._kill_facts(k),
                )

        # The bomb: a plant or a defuse that swung it, or came under pressure.
        plant = getattr(self, "_plant", None)
        if plant and self.planter:
            gain = plant["before"] - plant["after"]
            alive = plant["alive"]
            cts = sum(1 for s in alive if self.side.get(s) == "ct")
            ts = sum(1 for s in alive if self.side.get(s) == "t")
            left = winprob.ROUND_SECONDS - (plant["tick"] - self.start) / self.rate
            if gain >= KEY_SWING or (left < 12 and winner == "t") or (ts == 1 and cts >= 2):
                self.add(
                    "key_play",
                    "plant",
                    plant["tick"],
                    [self.planter],
                    gain,
                    site=self.rnd.bomb_site,
                    cts=cts,
                    ts=ts,
                    clock=round(left, 1),
                    spot=self.spot(self.planter, plant["tick"]),
                )
        defuse = getattr(self, "_defuse", None)
        if (
            defuse
            and self.defuse.get("sid")
            and not any(f["code"] == "clutch" and f["facts"].get("defused") for f in self.findings)
        ):
            sid = self.defuse["sid"]
            gain = 1.0 - defuse["before"]
            ts = sum(1 for s in defuse["alive"] if self.side.get(s) == "t")
            left = (
                winprob.BOMB_SECONDS - (defuse["tick"] - (self.plant or defuse["tick"])) / self.rate
            )
            if gain >= KEY_SWING or ts > 0 or left < 2:
                self.add(
                    "key_play",
                    "defuse",
                    defuse["tick"],
                    [sid],
                    gain,
                    ts=ts,
                    spare=round(left, 1),
                    kit=sid in self.kit,
                    spot=self.spot(sid, defuse["tick"]),
                )

        # A retake: CTs winning after the plant; the CT who swung it most leads it.
        if plant and winner == "ct":
            post = [
                k
                for k in live
                if k["tick"] >= plant["tick"] and self.side.get(k["attacker"]) == "ct"
            ]
            if post:
                best = max(
                    {k["attacker"] for k in post},
                    key=lambda s: sum(k["credits"].get(s, 0.0) for k in post),
                )
                if not any(
                    f["sids"][:1] == [best] and f["code"] in ("clutch",) for f in self.findings
                ):
                    gain = sum(k["credits"].get(best, 0.0) for k in post)
                    ts_at_plant = sum(1 for s in plant["alive"] if self.side.get(s) == "t")
                    cts_at_plant = sum(1 for s in plant["alive"] if self.side.get(s) == "ct")
                    self.add(
                        "key_play",
                        "retake",
                        post[0]["tick"],
                        [best],
                        gain,
                        kills=sum(1 for k in post if k["attacker"] == best),
                        cts=cts_at_plant,
                        ts=ts_at_plant,
                        site=self.rnd.bomb_site,
                    )

    def _kill_facts(self, k: dict) -> dict:
        return {
            "victim": k["victim"],
            "weapon": k["weapon"],
            "headshot": k["headshot"],
            "thrusmoke": k["thrusmoke"],
            "wallbang": k["wallbang"],
            "noscope": k["noscope"],
            "spot": self.spot(k["attacker"], k["tick"], k_pos(k), k["a_place"]),
            "victim_spot": self.spot(k["victim"], k["tick"], v_pos(k), k["v_place"]),
            "alive": list(k.get("alive_before") or (0, 0)),
            "wp_before": round(self._team_wp(k["attacker"], k), 3),
            "wp_after": round(self._team_wp(k["attacker"], k) + k.get("d_team", 0.0), 3),
            "team_swing": round(k.get("d_team", 0.0), 3),
            "flasher": k.get("flasher"),
            "traded_by": k.get("traded_by"),
            "opening": bool(k.get("opening")),
        }

    def _team_wp(self, sid: str | None, k: dict) -> float:
        p = k.get("wp_ct_before", 0.5)
        return p if self.side.get(sid) == "ct" else 1.0 - p

    # -- Mistakes -------------------------------------------------------
    def mistakes(self) -> None:
        for k in self.kills:
            victim = k["victim"]
            v_side = self.side.get(victim)
            if not victim or not v_side:
                continue
            tick = k["tick"]
            loss = k["credits"].get(victim, 0.0) if not k.get("post") else 0.0
            team_wp = self._team_wp(victim, k)
            alive = self.alive_at(tick)
            mates = [s for s in alive if self.side.get(s) == v_side and s != victim]
            foes = [s for s in alive if self.side.get(s) not in (None, v_side)]
            here = v_pos(k) if None not in v_pos(k) else self.pos(victim, tick)
            killer = (
                k["attacker"] if k["attacker"] and self.side.get(k["attacker"]) != v_side else None
            )
            lost = not self.won(v_side)
            facts = {
                "killer": killer,
                "weapon": k["weapon"],
                "spot": self.spot(victim, tick, here, k["v_place"]),
                "killer_spot": self.spot(killer, tick, k_pos(k), k["a_place"]) if killer else "",
                "alive": [len(mates) + 1, len(foes)],
            }

            # Losing a gun in a Round already lost (after its end, too).
            held, inv = self.loadout_at(victim, tick - 1)
            gun = next((x for x in inv if x in RIFLES), "") or (
                self.primary.get(victim) if self.primary.get(victim) in RIFLES else ""
            )
            if gun and (k.get("post") or team_wp < SAVE_WP) and lost and not self._last_of_half():
                self.add(
                    "mistake",
                    "lost_weapon_save",
                    tick,
                    [victim, killer],
                    loss,
                    gun=gun,
                    team_wp=round(team_wp, 3),
                    post=bool(k.get("post")),
                    next_buy=self._next_buy(v_side),
                    **facts,
                )
                continue
            if k.get("post") or loss > -MISTAKE_SWING:
                continue

            # Blind from a teammate's flash.
            blind = self.blind_at(victim, tick)
            if (
                blind
                and blind.thrower
                and blind.thrower != victim
                and self.side.get(blind.thrower) == v_side
                and (blind.end - tick) / self.rate >= -0.1
                and blind.seconds >= TEAM_FLASH_DEATH
            ):
                self.add(
                    "mistake",
                    "team_flashed_death",
                    tick,
                    [blind.thrower, victim, killer],
                    loss,
                    victim=victim,
                    seconds=round(blind.seconds, 1),
                    **facts,
                )
                continue

            # Caught in a duel with a knife or a grenade in hand.
            if killer and k["weapon"] not in NOT_A_DUEL:
                if self._no_gun_in_hand(k, victim, held, inv, loss, facts):
                    continue

            # Two up and died, and the Round was lost.
            if lost and len(mates) + 1 - len(foes) >= ADVANTAGE_MEN and not k.get("traded_by"):
                self.add("mistake", "died_in_advantage", tick, [victim, killer], loss, **facts)
                continue

            # The bomb carrier, alone, and no plant came.
            dropped = any(
                b["event"] == "drop" and b["sid"] == victim and abs(b["tick"] - tick) <= 4
                for b in self.bomb
            )
            if (
                dropped
                and v_side == "t"
                and self.plant is None
                and lost
                and not any(_near(here, self.pos(m, tick), 800.0) for m in mates)
            ):
                self.add("mistake", "bomb_lost", tick, [victim, killer], loss, **facts)
                continue

            # Alone and nobody traded.
            if (
                mates
                and not k.get("traded_by")
                and not any(_near(here, self.pos(m, tick)) for m in mates)
            ):
                nearest = min(
                    (
                        _dist(here, self.pos(m, tick))[0]
                        for m in mates
                        if None not in self.pos(m, tick)
                    ),
                    default=None,
                )
                self.add(
                    "mistake",
                    "untraded",
                    tick,
                    [victim, killer],
                    loss,
                    nearest=round(nearest) if nearest is not None else None,
                    **facts,
                )
                continue

            # An AWP shot that missed, and dead within two seconds.
            missed = [
                s
                for s in self.shots_between(victim, tick - int(AWP_MISS_SECONDS * self.rate), tick)
                if s[1] == "awp"
                and not any(
                    d["attacker"] == victim and d["weapon"] == "awp" and 0 <= d["tick"] - s[0] <= 3
                    for d in self.damages
                )
            ]
            missed = [m for m in missed if (tick - m[0]) / self.rate >= AWP_MISS_GAP]
            if missed and killer:
                self.add(
                    "mistake",
                    "awp_miss",
                    tick,
                    [victim, killer],
                    loss,
                    after=round((tick - missed[-1][0]) / self.rate, 2),
                    **facts,
                )
                continue

            # Shooting while running, in the duel that killed them.
            fired = [
                s
                for s in self.shots_between(victim, tick - 3 * self.rate, tick)
                if s[1] in MAX_SPEED and s[1] in WEAPON_CLASS
            ]
            track = self.tracks.get(victim)
            if (
                killer
                and track
                and len(fired) >= 2
                and self.damage(victim, killer, tick - 3 * self.rate, tick) < UNFINISHED_DAMAGE
            ):
                speeds = [track.speed(s[0], self.rate) / MAX_SPEED[s[1]] for s in fired]
                moving = sum(
                    1
                    for s, v in zip(fired, speeds, strict=True)
                    if v > MOVING_SHARE[WEAPON_CLASS[s[1]]]
                )
                if moving * 2 > len(fired):
                    self.add(
                        "mistake",
                        "moving_shots",
                        tick,
                        [victim, killer],
                        loss,
                        shots=len(fired),
                        moving=moving,
                        speed=round(100 * sum(speeds) / len(speeds)),
                        **facts,
                    )
                    continue

            # With Sightings: where the crosshair was, and an unscoped AWP.
            if self.i.sightings and killer:
                if self._crosshair(k, victim, killer, loss, facts):
                    continue
                if self._unscoped_awp(k, victim, killer, loss, facts):
                    continue

            # Dying with the utility still in the pocket, in a lost Round.
            nades = [x for x in inv if x in GRENADES]
            if (
                lost
                and sum(GRENADE_PRICE.get(x, 0) for x in nades) >= UNUSED_UTILITY_VALUE
                and (tick - self.start) / self.rate >= UNUSED_UTILITY_AFTER
            ):
                self.add(
                    "mistake", "unused_utility", tick, [victim, killer], loss, nades=nades, **facts
                )

        # Team Mistakes.
        if self.rnd.end_reason == "time_ran_out" and self.plant is None:
            alive = self.alive_at(self.end, inclusive=True)
            ts = [s for s in alive if self.side.get(s) == "t"]
            if ts:
                self.add(
                    "mistake",
                    "time_out",
                    self.end,
                    ts,
                    -0.0,
                    side="t",
                    ts=len(ts),
                    cts=sum(1 for s in alive if self.side.get(s) == "ct"),
                )
        if self.rnd.end_reason == "bomb_exploded" and self.plant is not None:
            alive = self.alive_at(self.end, inclusive=True)
            cts = [s for s in alive if self.side.get(s) == "ct"]
            if cts and not any(s in self.kit for s in cts):
                last_t = self._last_t_death()
                if last_t is not None:
                    left = winprob.BOMB_SECONDS - (last_t - self.plant) / self.rate
                    travel = self._travel(cts, last_t)
                    if (
                        winprob.DEFUSE_KIT_SECONDS + travel
                        <= left
                        < winprob.DEFUSE_SECONDS + travel
                    ):
                        self.add(
                            "mistake",
                            "kitless",
                            last_t,
                            cts,
                            -0.0,
                            side="ct",
                            left=round(left, 1),
                            travel=round(travel, 1),
                        )

    def _last_of_half(self) -> bool:
        """A half's or the Map's last Round: nothing carries over, so nothing to save."""
        n = self.n
        last = self.i.rounds[-1].number if self.i.rounds else n
        overtime = n > HALF_ENDS[-1] and (n - HALF_ENDS[-1]) % OT_HALF == 0
        return n in HALF_ENDS or overtime or n == last

    def _next_buy(self, side: str) -> str:
        """What this side's Team bought the next Round (a BuyType value, or "")."""
        team = self.team(side)
        nxt = next((r for r in self.i.rounds if r.number == self.n + 1), None)
        if nxt is None or team is None:
            return ""
        if nxt.ct_team_id == team:
            return nxt.ct_buy or ""
        if nxt.t_team_id == team:
            return nxt.t_buy or ""
        return ""

    def _no_gun_in_hand(self, k, victim, held, inv, loss, facts) -> bool:
        """A knife or grenade in hand, a gun in the Loadout, and no gun drawn
        for long enough before dying that the switch was no part of the duel."""
        kind = _held_kind(held)
        if kind not in NO_GUN_SECONDS or not any(_held_kind(x) == "gun" for x in inv):
            return False
        ticks, helds, _inv = self.i.loadout[self.n][victim]
        tick = k["tick"]
        i = int(np.searchsorted(ticks, tick - 1, side="right")) - 1
        # Back to the last sample with a gun in hand, or to the freeze end; a
        # gap in the Round is unknown, not unarmed.
        j = i
        while j >= 0 and ticks[j] >= self.start and _held_kind(helds[j]) not in ("gun", ""):
            j -= 1
        last = helds[j] if j >= 0 else None
        if j >= 0 and ticks[j] >= self.start and _held_kind(last) != "gun":
            return False
        away = max(int(ticks[j + 1]), self.start)
        seconds = (tick - away) / self.rate
        if seconds < NO_GUN_SECONDS[kind]:
            return False
        self.add(
            "mistake",
            "no_gun_in_hand",
            max(away, tick - int(NO_GUN_LEAD * self.rate)),
            [victim, facts["killer"]],
            loss,
            held=held,
            held_kind=kind,
            seconds=round(seconds, 1),
            gun=last if _held_kind(last) == "gun" else "",
            **facts,
        )
        return True

    def _last_t_death(self) -> int | None:
        if self.plant is None:
            return None
        ts = [s for s, sd in self.side.items() if sd == "t"]
        deaths = {k["victim"]: k["tick"] for k in self.kills if not k.get("post")}
        if not ts or not all(s in deaths for s in ts):
            return None
        last = max(deaths[s] for s in ts)
        return max(last, self.plant)

    def _travel(self, cts: list[str], tick: int) -> float:
        if not self.bomb_pos or None in self.bomb_pos:
            return 0.0
        dists = [
            _dist(self.pos(s, tick), self.bomb_pos)[0] for s in cts if None not in self.pos(s, tick)
        ]
        return min(dists) / 230.0 if dists else 0.0

    def _crosshair(self, k, victim, killer, loss, facts) -> bool:
        tick = k["tick"]
        first = self.first_seen(victim, killer, tick - 3 * self.rate, tick)
        if first is None or (tick - first) / self.rate > 1.5:
            return False
        if self.damage(victim, killer, first, tick) >= UNFINISHED_DAMAGE:
            return False
        error = self._aim_error(victim, killer, first)
        if error is None or error <= CROSSHAIR_DEGREES:
            return False
        self.add(
            "mistake",
            "crosshair",
            first,
            [victim, killer],
            loss,
            sight=True,
            degrees=round(error),
            reaction=round((tick - first) / self.rate, 2),
            **facts,
        )
        return True

    def _aim_error(self, viewer: str, target: str, tick: int) -> float | None:
        track = self.tracks.get(viewer)
        aim = self.aim_at(viewer, tick)
        other = self.aim_at(target, tick)
        if not track or aim is None:
            return None
        i = track.at(tick)
        yaw = math.radians(float(track.yaw[i]))
        pitch = math.radians(aim[0])
        ex, ey, ez = self.pos(viewer, tick)
        tx, ty, tz = self.pos(target, tick)
        if None in (ex, ey, ez, tx, ty, tz):
            return None
        ez += EYE_CROUCHING if aim[2] else EYE_STANDING
        tz += (EYE_CROUCHING if other and other[2] else EYE_STANDING) - 6.0
        view = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), -math.sin(pitch))
        dx, dy, dz = tx - ex, ty - ey, tz - ez
        norm = math.sqrt(dx * dx + dy * dy + dz * dz)
        if norm < 1:
            return None
        cos = (view[0] * dx + view[1] * dy + view[2] * dz) / norm
        return math.degrees(math.acos(max(-1.0, min(1.0, cos))))

    def _unscoped_awp(self, k, victim, killer, loss, facts) -> bool:
        tick = k["tick"]
        held, _inv = self.loadout_at(victim, tick - 1)
        if held != "AWP":
            return False
        first = self.first_seen(victim, killer, tick - 2 * self.rate, tick)
        if first is None or (tick - first) / self.rate < UNSCOPED_MIN_SECONDS:
            return False
        aims = [self.aim_at(victim, t) for t in range(first, tick, max(1, self.rate // 16))]
        aims = [a for a in aims if a is not None]
        if not aims or any(a[1] for a in aims):
            return False
        self.add("mistake", "unscoped_awp", first, [victim, killer], loss, sight=True, **facts)
        return True

    # -- Missed chances -------------------------------------------------
    def missed_chances(self) -> None:
        live = [k for k in self.kills if not k.get("post")]
        window = int(TRADE_SECONDS * self.rate)
        # A Trade someone was close enough to take.
        taken: dict[tuple[str, str], dict] = {}
        for k in live:
            victim, killer = k["victim"], k["attacker"]
            v_side = self.side.get(victim)
            if not killer or not v_side or self.side.get(killer) == v_side or k.get("traded_by"):
                continue
            team_loss = -k["credits"].get(victim, 0.0)
            if team_loss < CHANCE_SWING:
                continue
            tick = k["tick"]
            k_here = k_pos(k) if None not in k_pos(k) else self.pos(killer, tick)
            if any(x["victim"] == killer and 0 <= x["tick"] - tick <= window for x in live):
                continue
            deaths = {x["victim"]: x["tick"] for x in live}
            close = []
            for m in self.alive_at(tick, inclusive=True):
                if self.side.get(m) != v_side:
                    continue
                # Killed in the same breath: they took the fight and lost it.
                if m in deaths and deaths[m] - tick <= self.rate:
                    continue
                if self.blind_at(m, tick):
                    continue
                p = self.pos(m, tick)
                if None in p:
                    continue
                saw = None
                if self.i.sightings:
                    saw = (
                        self.first_seen(m, killer, tick - self.rate, tick + 3 * self.rate)
                        is not None
                    )
                if not _near(p, k_here, TRADE_REACH_SEEN if saw else TRADE_REACH):
                    continue
                close.append((saw is True, -_dist(p, k_here)[0], m, saw))
            if not close:
                continue
            close.sort(reverse=True)
            _seen, neg, mate, saw = close[0]
            key = (mate, killer)
            if key in taken and taken[key]["swing"] <= -team_loss:
                continue
            taken[key] = {
                "tick": tick,
                "sids": [mate, victim, killer],
                "swing": -team_loss,
                "facts": {
                    "victim": victim,
                    "killer": killer,
                    "distance": round(-neg),
                    "saw": saw,
                    "spot": self.spot(mate, tick),
                    "killer_spot": self.spot(killer, tick, k_here, k["a_place"]),
                },
            }
        for found in taken.values():
            self.add(
                "missed_chance",
                "no_trade",
                found["tick"],
                found["sids"],
                found["swing"],
                **found["facts"],
            )

        # An enemy they had damaged and left alive, who then hurt them.
        hits: dict[tuple[str, str], list] = defaultdict(list)
        for d in self.damages:
            if (
                d["attacker"]
                and d["victim"]
                and d["weapon"] not in FIRE + ("hegrenade",)
                and self.side.get(d["attacker"]) not in (None, self.side.get(d["victim"]))
            ):
                hits[(d["attacker"], d["victim"])].append(d)
        deaths = {k["victim"]: k["tick"] for k in self.kills}
        for (attacker, enemy), ds in hits.items():
            dealt = sum(d["dmg"] for d in ds)
            if dealt < UNFINISHED_DAMAGE or ds[-1]["hp_after"] <= 0:
                continue
            last = ds[-1]["tick"]
            died = deaths.get(enemy)
            if died is not None and died - last <= window:
                continue  # finished by someone soon enough
            a_side = self.side.get(attacker)
            later = [
                k
                for k in live
                if k["attacker"] == enemy
                and k["tick"] > last
                and self.side.get(k["victim"]) == a_side
            ]
            enemy_won = self.won(self.side.get(enemy, ""))
            if not later:
                continue
            cost = sum(-k["credits"].get(k["victim"], 0.0) for k in later)
            if cost < CHANCE_SWING:
                continue
            self.add(
                "missed_chance",
                "unfinished",
                last,
                [attacker, enemy],
                -cost,
                enemy=enemy,
                dealt=dealt,
                hp=ds[-1]["hp_after"],
                kills_after=len(later),
                enemy_won=enemy_won,
                victims=[k["victim"] for k in later],
                spot=self.spot(attacker, last),
            )

        # A blinded enemy nobody punished: one Finding per flash, for the
        # teammate of the thrower who was closest.
        unpunished: dict[tuple[int, str], dict] = {}
        for sid, track in self.tracks.items():
            s_side = self.side.get(sid)
            for b in track.blinds:
                if not b.thrower or b.seconds < BLIND_UNPUNISHED or not s_side:
                    continue
                t_side = self.side.get(b.thrower)
                if not t_side or t_side == s_side or b.onset > self.end:
                    continue
                if deaths.get(sid) is not None and b.onset <= deaths[sid] <= b.end + self.rate:
                    continue
                if deaths.get(sid) is not None and deaths[sid] < b.onset:
                    continue
                here = track.pos(b.onset)
                near = []
                for m in self.alive_at(b.onset):
                    if self.side.get(m) != t_side or None in self.pos(m, b.onset):
                        continue
                    if self.blind_at(m, b.onset + self.rate // 2):
                        continue
                    saw = None
                    if self.i.sightings:
                        saw = self.first_seen(m, sid, b.onset, b.end) is not None
                    reach = FLASH_REACH * 1.5 if saw else FLASH_REACH
                    if _near(self.pos(m, b.onset), here, reach):
                        near.append((saw is True, -_dist(self.pos(m, b.onset), here)[0], m, saw))
                if not near:
                    continue
                near.sort(reverse=True)
                _seen, neg, mate, saw = near[0]
                key = (b.flash_tick or b.onset, mate)
                found = unpunished.setdefault(
                    key,
                    {
                        "tick": b.onset,
                        "mate": mate,
                        "thrower": b.thrower,
                        "enemies": [],
                        "distance": round(-neg),
                        "saw": saw,
                        "spot": self.spot(sid, b.onset),
                    },
                )
                found["enemies"].append({"sid": sid, "seconds": round(b.seconds, 1)})
        for found in unpunished.values():
            enemies = [e["sid"] for e in found["enemies"]]
            self.add(
                "missed_chance",
                "blind_unpunished",
                found["tick"],
                [found["mate"], *enemies, found["thrower"]],
                -0.0,
                enemies=found["enemies"],
                thrower=found["thrower"],
                saw=found["saw"],
                distance=found["distance"],
                spot=found["spot"],
            )

        # A Round two up, or 80% won, and still lost.
        for side in ("ct", "t"):
            if self.won(side):
                continue
            peak, peak_t = 0.0, None
            for t, p in self.wp:
                mine = p if side == "ct" else 1.0 - p
                if mine > peak:
                    peak, peak_t = mine, t
            if peak >= ADVANTAGE_WP and peak_t is not None:
                tick = self.start + int(peak_t * self.rate)
                after = [
                    k for k in live if k["tick"] >= tick and self.side.get(k["victim"]) == side
                ]
                alive = self.alive_at(tick, inclusive=True)
                self.add(
                    "missed_chance",
                    "advantage_lost",
                    tick,
                    [k["victim"] for k in after] or [s for s in alive if self.side.get(s) == side],
                    -(peak - 0.0),
                    side=side,
                    peak=round(peak, 3),
                    men=[
                        sum(1 for s in alive if self.side.get(s) == side),
                        sum(1 for s in alive if self.side.get(s) not in (None, side)),
                    ],
                    deaths=[
                        {"sid": k["victim"], "swing": round(k["credits"].get(k["victim"], 0.0), 3)}
                        for k in after
                    ],
                )

        # Time for a defuse, and nobody went.
        if self.rnd.end_reason == "bomb_exploded" and self.plant is not None:
            last_t = self._last_t_death()
            cts = [s for s in self.alive_at(self.end, inclusive=True) if self.side.get(s) == "ct"]
            if last_t is not None and cts:
                left = winprob.BOMB_SECONDS - (last_t - self.plant) / self.rate
                best = None
                for s in cts:
                    p = self.pos(s, last_t)
                    if None in p or not self.bomb_pos or None in self.bomb_pos:
                        continue
                    need = (
                        winprob.DEFUSE_KIT_SECONDS if s in self.kit else winprob.DEFUSE_SECONDS
                    ) + _dist(p, self.bomb_pos)[0] / 230.0
                    if left >= need + 1.0 and (best is None or need < best[0]):
                        best = (need, s)
                if best:
                    self.add(
                        "missed_chance",
                        "defuse_chance",
                        last_t,
                        [best[1]],
                        -0.0,
                        left=round(left, 1),
                        need=round(best[0], 1),
                        kit=best[1] in self.kit,
                    )

        if self.i.sightings:
            self._saw_no_shot(live)
            self._saw_first_lost(live)

    def _spans(self, ticks: np.ndarray) -> list[tuple[int, int]]:
        """Continuous stretches of a Sighting (gaps of up to 0.15 s bridged)."""
        if not len(ticks):
            return []
        gap = int(0.15 * self.rate)
        out, s, prev = [], int(ticks[0]), int(ticks[0])
        for t in ticks[1:]:
            t = int(t)
            if t - prev > gap:
                out.append((s, prev))
                s = t
            prev = t
        out.append((s, prev))
        return out

    def _saw_no_shot(self, live: list) -> None:
        """Had an enemy in view half a second or more, fired nothing, and that
        enemy killed them or a teammate within three seconds."""
        hold = int(SIGHT_HOLD_SECONDS * self.rate)
        for (spotter, seen), ticks in self.i.sight.get(self.n, {}).items():
            s_side = self.side.get(spotter)
            if not s_side or self.side.get(seen) in (None, s_side):
                continue
            for a, b in self._spans(ticks):
                if b - a < hold or a > self.end:
                    continue
                held, _ = self.loadout_at(spotter, a)
                if not held or any(w in held.lower() for w in NOT_AIMING):
                    continue
                if self.blind_at(spotter, a) or self.shots_between(spotter, a, b + self.rate // 5):
                    continue
                hit = next(
                    (
                        k
                        for k in live
                        if k["attacker"] == seen
                        and b <= k["tick"] <= b + 3 * self.rate
                        and self.side.get(k["victim"]) == s_side
                    ),
                    None,
                )
                if hit is None:
                    continue
                if spotter in {k["victim"] for k in live if k["tick"] < a}:
                    continue
                self.add(
                    "missed_chance",
                    "saw_no_shot",
                    a,
                    [spotter, seen, hit["victim"]],
                    hit["credits"].get(hit["victim"], 0.0),
                    sight=True,
                    enemy=seen,
                    seconds=round((b - a) / self.rate, 1),
                    victim=hit["victim"],
                    self_killed=hit["victim"] == spotter,
                    spot=self.spot(spotter, a),
                    enemy_spot=self.spot(seen, a),
                )
                break

    def _saw_first_lost(self, live: list) -> None:
        """Saw the enemy first, by a clear margin, and still lost the duel."""
        lead = int(SIGHT_FIRST_LEAD * self.rate)
        for k in live:
            victim, killer = k["victim"], k["attacker"]
            if not killer or self.side.get(killer) in (None, self.side.get(victim)):
                continue
            tick = k["tick"]
            mine = self.first_seen(victim, killer, tick - 3 * self.rate, tick)
            theirs = self.first_seen(killer, victim, tick - 3 * self.rate, tick)
            if mine is None or (theirs is not None and theirs - mine < lead):
                continue
            if self.damage(victim, killer, mine, tick) >= UNFINISHED_DAMAGE:
                continue
            if any(
                f["code"] in ("crosshair", "unscoped_awp")
                and f["round"] == self.n
                and f["tick"] == mine
                and f["sids"][:1] == [victim]
                for f in self.findings
            ):
                continue
            shots = self.shots_between(victim, mine, tick)
            self.add(
                "missed_chance",
                "saw_first_lost",
                mine,
                [victim, killer],
                k["credits"].get(victim, 0.0),
                sight=True,
                enemy=killer,
                lead=round(((theirs if theirs is not None else tick) - mine) / self.rate, 2),
                shots=len(shots),
                weapon=k["weapon"],
                spot=self.spot(victim, mine),
                enemy_spot=self.spot(killer, mine),
            )

    # -- Utility effects ----------------------------------------------------
    def utility(self) -> dict[str, dict]:
        """Utility effect Findings, and each thrower's tally for the player card."""
        tally: dict[str, dict] = defaultdict(lambda: defaultdict(float))
        live = [k for k in self.kills if not k.get("post")]
        # Flashes: who they blinded, and what came of it.
        pops = self.i.flashes.get(self.n, [])
        blinded: dict[int, list[Blind]] = defaultdict(list)
        for track in self.tracks.values():
            for b in track.blinds:
                if b.flash_tick is not None and b.thrower:
                    blinded[b.flash_tick].append(b)
        for pop in pops:
            thrower = pop["thrower"]
            side = self.side.get(thrower)
            if not thrower or not side or pop["tick"] > self.end:
                continue
            hits = [b for b in blinded.get(pop["tick"], []) if b.thrower == thrower]
            foes = [
                b
                for b in hits
                if self.side.get(b.sid) not in (None, side) and b.seconds >= BLIND_MEANINGFUL
            ]
            mates = [
                b
                for b in hits
                if self.side.get(b.sid) == side
                and b.sid != thrower
                and b.seconds >= TEAM_FLASH_SECONDS
            ]
            tally[thrower]["flashes"] += 1
            tally[thrower]["enemies_blinded"] += len(foes)
            tally[thrower]["blind_seconds"] += sum(b.seconds for b in foes)
            if not foes:
                tally[thrower]["empty_flashes"] += 1
            if mates:
                tally[thrower]["team_flashes"] += 1
                died = [
                    b
                    for b in mates
                    if any(k["victim"] == b.sid and b.onset <= k["tick"] <= b.end for k in live)
                ]
                if died or sum(b.seconds for b in mates) >= TEAM_FLASH_FINDING:
                    self.add(
                        "utility",
                        "team_flash",
                        pop["tick"],
                        [thrower] + [b.sid for b in mates],
                        -0.0,
                        blinded=[{"sid": b.sid, "seconds": round(b.seconds, 1)} for b in mates],
                        died=[b.sid for b in died],
                        spot=self.spot(None, pop["tick"], pop["pos"]),
                    )
            # The kills it set up.
            for k in live:
                b = next(
                    (b for b in foes if b.sid == k["victim"] and b.onset <= k["tick"] <= b.end),
                    None,
                )
                if b is None or self.side.get(k["attacker"]) != side:
                    continue
                tally[thrower]["flash_kills"] += 1
                share = k["credits"].get(thrower, 0.0)
                self.add(
                    "utility",
                    "flash_kill",
                    pop["tick"],
                    [thrower, k["attacker"], k["victim"]],
                    share,
                    killer=k["attacker"],
                    victim=k["victim"],
                    own=k["attacker"] == thrower,
                    seconds=round(b.seconds, 1),
                    kill_t=self.t(k["tick"]),
                    kill_swing=round(k.get("d_team", 0.0), 3),
                    spot=self.spot(k["victim"], k["tick"], v_pos(k), k["v_place"]),
                )

        # HE and fire: damage that let a kill land.
        util_hits: dict[tuple[str, str], list] = defaultdict(list)
        for d in self.damages:
            if (
                d["weapon"] in FIRE + ("hegrenade",)
                and d["attacker"]
                and self.side.get(d["attacker"]) not in (None, self.side.get(d["victim"]))
            ):
                util_hits[(d["attacker"], d["victim"])].append(d)
                key = "he_damage" if d["weapon"] == "hegrenade" else "fire_damage"
                tally[d["attacker"]][key] += d["dmg"]
        for (thrower, enemy), ds in util_hits.items():
            dealt = sum(d["dmg"] for d in ds)
            if dealt < UTILITY_DAMAGE_MIN:
                continue
            side = self.side.get(thrower)
            kill = next(
                (
                    k
                    for k in live
                    if k["victim"] == enemy
                    and k["tick"] >= ds[0]["tick"]
                    and k["tick"] - ds[-1]["tick"] <= 15 * self.rate
                    and self.side.get(k["attacker"]) == side
                ),
                None,
            )
            if kill is None:
                continue
            others = sum(
                d["dmg"]
                for d in self.damages
                if d["victim"] == enemy
                and d["tick"] <= kill["tick"]
                and d["weapon"] not in FIRE + ("hegrenade",)
            )
            if others >= 100:
                continue  # they would have died anyway
            self.add(
                "utility",
                "nade_damage_kill",
                ds[0]["tick"],
                [thrower, kill["attacker"], enemy],
                kill["credits"].get(thrower, 0.0),
                nade="he" if ds[0]["weapon"] == "hegrenade" else "fire",
                dealt=dealt,
                killer=kill["attacker"],
                victim=enemy,
                kill_t=self.t(kill["tick"]),
                spot=self.spot(enemy, ds[0]["tick"]),
            )

        # Fire that held up a defuse or a plant.
        for fire in self.i.infernos.get(self.n, []):
            thrower, side = fire["thrower"], self.side.get(fire["thrower"])
            if not thrower or not side or fire["end"] is None or None in fire["pos"]:
                continue
            tally[thrower]["fires"] += 1
            if (
                side == "t"
                and self.plant is not None
                and fire["start"] >= self.plant - self.rate
                and self.bomb_pos
                and None not in self.bomb_pos
                and _dist(fire["pos"], self.bomb_pos)[0] <= MOLLY_BOMB_REACH
            ):
                cts = [s for s in self.alive_at(fire["start"]) if self.side.get(s) == "ct"]
                if not cts:
                    continue
                stop = self.defuse["tick"] if self.defuse else self.end
                held = (min(fire["end"], stop) - max(fire["start"], self.plant)) / self.rate
                if held >= 2.0 and (self.defuse is None or self.defuse["tick"] >= fire["end"]):
                    self.add(
                        "utility",
                        "fire_delay",
                        fire["start"],
                        [thrower],
                        -0.0,
                        what="defuse",
                        seconds=round(held, 1),
                        exploded=self.defuse is None,
                        spot=self.spot(None, fire["start"], fire["pos"]),
                    )
            elif side == "ct" and (self.plant is None or self.plant > fire["start"]):
                ts_near = [
                    s
                    for s in self.alive_at(fire["start"])
                    if self.side.get(s) == "t"
                    and _near(self.pos(s, fire["start"]), fire["pos"], 800.0)
                ]
                if len(ts_near) < 2:
                    continue
                if (
                    self.plant is not None
                    and self.bomb_pos
                    and None not in self.bomb_pos
                    and _dist(fire["pos"], self.bomb_pos)[0] <= 500
                    and self.plant >= fire["end"]
                ):
                    held = (fire["end"] - fire["start"]) / self.rate
                    self.add(
                        "utility",
                        "fire_delay",
                        fire["start"],
                        [thrower],
                        -0.0,
                        what="plant",
                        seconds=round(held, 1),
                        ts=len(ts_near),
                        spot=self.spot(None, fire["start"], fire["pos"]),
                    )
        for pop in self.i.hes.get(self.n, []):
            if pop["thrower"] in self.side:
                tally[pop["thrower"]]["hes"] += 1
                if not util_hits or not any(
                    t == pop["thrower"] and any(abs(d["tick"] - pop["tick"]) <= 2 for d in ds)
                    for (t, _e), ds in util_hits.items()
                ):
                    tally[pop["thrower"]]["empty_hes"] += 1
        return {sid: dict(v) for sid, v in tally.items()}

    # -- engagements (PL-5) ---------------------------------------------
    def engagements(self) -> dict[str, dict]:
        """Each Player's clean engagements this Round: a stretch of Sighting of a
        living enemy, gun in hand, not blind. For each: the crosshair's angle off
        the enemy's head as he came into view, the time to the first damage on
        him (within :data:`TTD_MAX_SECONDS`), the shots fired below the weapon
        class's moving share (counter-strafed), and whether the first shot hit."""
        out: dict[str, dict] = {}
        if not self.i.sightings:
            return out
        reach = int(TTD_MAX_SECONDS * self.rate)
        for (spotter, seen), ticks in self.i.sight.get(self.n, {}).items():
            s_side = self.side.get(spotter)
            if not s_side or self.side.get(seen) in (None, s_side):
                continue
            track = self.tracks.get(spotter)
            for a, b in self._spans(ticks):
                if a < self.start or a > self.end:
                    continue
                alive = self.alive_at(a)
                if spotter not in alive or seen not in alive or self.blind_at(spotter, a):
                    continue
                held, _ = self.loadout_at(spotter, a)
                if not held or any(w in held.lower() for w in NOT_AIMING):
                    continue
                o = out.setdefault(spotter, {"engagements": 0, "ttd": [], "xhair": [],
                                             "shots": 0, "still": 0, "first": 0,
                                             "first_hit": 0})  # fmt: skip
                o["engagements"] += 1
                err = self._aim_error(spotter, seen, a)
                if err is not None:
                    o["xhair"].append(round(err, 1))
                hurt = [
                    d["tick"]
                    for d in self.damages
                    if d["attacker"] == spotter
                    and d["victim"] == seen
                    and a <= d["tick"] <= a + reach
                ]
                if hurt:
                    o["ttd"].append(round((min(hurt) - a) / self.rate, 3))
                shots = [
                    x for x in self.shots_between(spotter, a, b + self.rate // 5)
                    if x[1] in WEAPON_CLASS
                ]  # fmt: skip
                for tick, weapon in shots:
                    o["shots"] += 1
                    if track and (
                        track.speed(tick, self.rate) / MAX_SPEED[weapon]
                        <= MOVING_SHARE[WEAPON_CLASS[weapon]]
                    ):
                        o["still"] += 1
                if shots:
                    o["first"] += 1
                    o["first_hit"] += int(
                        any(
                            d["attacker"] == spotter
                            and d["victim"] == seen
                            and 0 <= d["tick"] - shots[0][0] <= HIT_TICKS
                            for d in self.damages
                        )
                    )
        return out

    # -- settling the Round (RV-2) --------------------------------------
    def settle(self) -> None:
        """The Trades' shares, then what the events left unassigned, so each
        Team's Players add up to its Win probability's move over the Round."""
        for k in self.kills:
            trader = k.get("traded_by")
            if not trader or k.get("post"):
                continue
            revenge = next(
                (
                    x
                    for x in self.kills
                    if x.get("trade_of") == k["victim"] and x["attacker"] == trader
                ),
                None,
            )
            gain = revenge["credits"].get(trader, 0.0) if revenge else 0.0
            if gain > 0:
                self.swing[trader] -= TRADE_SHARE * gain
                self.swing[k["victim"]] += TRADE_SHARE * gain
        for f in self.findings:
            if f["code"] == "no_trade" and len(f["sids"]) >= 2:
                mate, victim = f["sids"][0], f["sids"][1]
                moved = TRADE_SHARE * abs(f["swing"])
                self.swing[mate] -= moved
                self.swing[victim] += moved

        start = getattr(self, "_start_wp", None)
        if start is None:
            return
        winner = self.rnd.winner_side
        final = 1.0 if winner == "ct" else 0.0
        alive = self.alive_at(self.end, inclusive=True)
        planted = self.plant is not None and self.start <= self.plant <= self.end
        clutcher = next((f["sids"][0] for f in self.findings if f["code"] == "clutch"), None)
        defuser = self.defuse.get("sid") if self.defuse else None
        for side in ("ct", "t"):
            members = [s for s, sd in self.side.items() if sd == side]
            if not members:
                continue
            moved = (final - start) if side == "ct" else (start - final)
            rest = moved - sum(self.swing.get(s, 0.0) for s in members)
            if abs(rest) < 1e-9:
                continue
            weights = {}
            for s in members:
                w = RESIDUAL_WEIGHTS["survived"] if s in alive else 0.0
                if side == winner:
                    killed = any(
                        x["attacker"] == s
                        and not x.get("post")
                        and x["credits"].get(s, 0.0) > 0
                        and (not planted or x["tick"] >= self.plant)
                        for x in self.kills
                    )
                    w += RESIDUAL_WEIGHTS["killed"] if killed else 0.0
                    w += RESIDUAL_WEIGHTS["clutch"] if s == clutcher else 0.0
                    w += RESIDUAL_WEIGHTS["defuse"] if s == defuser else 0.0
                weights[s] = w
            total = sum(weights.values())
            if total <= 0:
                weights, total = dict.fromkeys(members, 1.0), float(len(members))
            for s, w in weights.items():
                self.swing[s] += rest * w / total

    def run(self) -> tuple[dict, dict]:
        self.timeline()
        self.trades()
        self.key_plays()
        self.mistakes()
        self.missed_chances()
        self.settle()
        tally = self.utility()
        self.aim = self.engagements()
        deaths = [k for k in self.kills if not k.get("post")]
        winners = [s for s, sd in self.side.items() if sd == self.rnd.winner_side]
        decider = max(winners, key=lambda s: self.swing.get(s, 0.0)) if winners else None
        summary = {
            "n": self.n,
            "winner_side": self.rnd.winner_side,
            "winner_team_id": self.rnd.winner_team_id,
            "ct_team_id": self.rnd.ct_team_id,
            "t_team_id": self.rnd.t_team_id,
            "reason": self.rnd.end_reason,
            "site": self.rnd.bomb_site,
            "ct_buy": self.rnd.ct_buy,
            "t_buy": self.rnd.t_buy,
            "seconds": self.t(self.end),
            "wp": self.wp,
            "events": self.events,
            "swing": {s: round(v, 4) for s, v in self.swing.items()},
            "sides": dict(self.side),
            "decider": decider,
            "kills": [
                {
                    "t": self.t(k["tick"]),
                    "a": k["attacker"],
                    "v": k["victim"],
                    "traded": bool(k.get("traded_by")),
                    "opening": bool(k.get("opening")),
                    "weapon": k["weapon"],
                    "hs": k["headshot"],
                }
                for k in deaths
            ],
        }
        return summary, tally


def states(db: Session, match_map: MatchMap, bundle=None) -> list[tuple[list, bool]]:
    """Each decided Round's sampled states and whether the CTs won it, read the
    way the Review reads them: what :func:`winprob.fit` is fitted on (RV-4)."""
    from app.services import tickdata

    if bundle is None:
        dataset = db.scalar(select(TickDataset).where(TickDataset.match_map_id == match_map.id))
        if dataset is None:
            return []
        bundle = tickdata.read(tickdata.load_bundle(dataset))
    inputs = _Inputs(db, match_map, bundle)
    out = []
    for rnd in inputs.rounds:
        if rnd.winner_side not in ("ct", "t"):
            continue
        rr = _RoundReview(inputs, rnd)
        if len(rr.side) < 2:
            continue
        out.append((rr.sample_states(), rnd.winner_side == "ct"))
    return out


def k_pos(k: dict):
    return k["a_pos"]


def v_pos(k: dict):
    return k["v_pos"]


# ---------------------------------------------------------------- the build ---
def build(db: Session, match_map: MatchMap, bundle) -> dict:
    """The whole Review of one Match Map, as stored."""
    inputs = _Inputs(db, match_map, bundle)
    rounds, findings = [], []
    tallies: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    aims: dict[str, dict] = {}
    for rnd in inputs.rounds:
        if rnd.number not in inputs.tracks or rnd.winner_side not in ("ct", "t"):
            continue
        review = _RoundReview(inputs, rnd)
        summary, tally = review.run()
        rounds.append(summary)
        findings += review.findings
        for sid, o in review.aim.items():
            mine = aims.setdefault(sid, {"engagements": 0, "ttd": [], "xhair": [], "shots": 0,
                                         "still": 0, "first": 0, "first_hit": 0})  # fmt: skip
            for key, value in o.items():
                mine[key] += value
        for sid, counts in tally.items():
            for key, value in counts.items():
                tallies[sid][key] += value

    # Utility that touched nobody, once per Player per Match Map.
    for sid, t in tallies.items():
        empty = int(t.get("empty_flashes", 0))
        if (
            empty >= EMPTY_UTILITY_MIN
            and empty * 2 >= t.get("flashes", 0)
            and sid in inputs.players
        ):
            findings.append(
                {
                    "id": f"m-empty-{sid}",
                    "kind": "utility",
                    "code": "empty_utility",
                    "round": None,
                    "tick": None,
                    "t": None,
                    "side": "",
                    "team_id": inputs.players[sid]["team_id"],
                    "sids": [sid],
                    "swing": 0.0,
                    "sight": False,
                    "facts": {
                        "flashes": int(t.get("flashes", 0)),
                        "empty_flashes": int(t.get("empty_flashes", 0)),
                        "hes": int(t.get("hes", 0)),
                        "empty_hes": int(t.get("empty_hes", 0)),
                    },
                }
            )

    players = []
    for sid, info in inputs.players.items():
        per_round = {r["n"]: r["swing"].get(sid, 0.0) for r in rounds if sid in r["sides"]}
        if not per_round:
            continue
        mine = [f for f in findings if f["sids"][:1] == [sid]]
        counts = defaultdict(int)
        for f in mine:
            counts[f["kind"]] += 1
        best = max(per_round, key=per_round.get)
        worst = min(per_round, key=per_round.get)
        t = tallies.get(sid, {})
        players.append(
            {
                **info,
                "rounds": len(per_round),
                "swing": round(sum(per_round.values()), 4),
                "swing_per_round": round(sum(per_round.values()) / len(per_round), 4),
                "best_round": {"n": best, "swing": round(per_round[best], 4)},
                "worst_round": {"n": worst, "swing": round(per_round[worst], 4)},
                "counts": dict(counts),
                "utility": {k: round(float(v), 1) for k, v in t.items()},
                # Engagements, with Sightings only (PL-5).
                "aim": aims.get(sid),
            }
        )
    players.sort(key=lambda p: (str(p["team_id"]), -p["swing"]))
    return {
        "version": version(),
        "sightings": inputs.sightings,
        "needs_sightings": [] if inputs.sightings else list(SIGHT_CODES),
        "loadout": inputs.has_loadout,
        "needs_loadout": [] if inputs.has_loadout else list(LOADOUT_CODES),
        "map": inputs.map_name,
        "tickrate": inputs.rate,
        "players": players,
        "rounds": rounds,
        "findings": findings,
    }
