"""What comes out of parsing a demo: rounds, events, and the rollups built on them.

The split from ``source.py`` is deliberate. Those models track *files*: whether a
demo was downloaded and unpacked. These track *what happened in the game*, and
survive the file being deleted: a parsed map keeps its analysis after the
``.dem`` is reclaimed.

Ported from cstat's ``hltv/models/analysis.py``. The hazard notes (H1-H10) in the
comments refer to cstat's ``plans/ANALYZE.md``, which measured each one against
real awpy output.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import (
    BigId,
    DateTime6,
    Float,
    LongBlob,
    MediumBlob,
    PositiveInt,
    PositiveSmallInt,
    TimestampMixin,
)

if TYPE_CHECKING:
    from app.models.source import Demo, Match, Team


def _team_fk(ondelete: str = "RESTRICT") -> Any:
    return mapped_column(BigId, ForeignKey("teams.id", ondelete=ondelete))


def _player_fk(nullable: bool = False) -> Any:
    return mapped_column(BigId, ForeignKey("players.id", ondelete="RESTRICT"), nullable=nullable)


def _match_map_fk() -> Any:
    return mapped_column(BigId, ForeignKey("match_maps.id", ondelete="CASCADE"))


def _round_fk() -> Any:
    return mapped_column(BigId, ForeignKey("rounds.id", ondelete="CASCADE"))


class Side(StrEnum):
    """The two sides. awpy writes them lowercase and only ever these two."""

    CT = "ct"  # Counter-Terrorist
    T = "t"  # Terrorist


class BuyType(StrEnum):
    """How a Team equipped itself for a Round (CONTEXT.md: Buy type)."""

    PISTOL = "pistol"
    ECO = "eco"
    FORCE = "force"
    FULL = "full"


# ---------------------------------------------------------------- identity ---
class Player(TimestampMixin, Base):
    """One steamid, forever.

    Names change between matches and even between maps; the steamid does not, so
    it is the only identity worth keying on. BIGINT fits both awpy's UInt64 and
    Int64 steamids (H9): the largest real one is about 7.7e16.
    """

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    steamid: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(String(64), index=True, doc="Most recently seen.")
    first_seen: Mapped[datetime | None] = mapped_column(DateTime6)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime6)

    aliases: Mapped[list[PlayerAlias]] = relationship(back_populates="player", passive_deletes=True)
    map_appearances: Mapped[list[MapRoster]] = relationship(back_populates="player")
    kills_made: Mapped[list[KillEvent]] = relationship(
        back_populates="attacker", foreign_keys="KillEvent.attacker_id"
    )
    deaths: Mapped[list[KillEvent]] = relationship(
        back_populates="victim", foreign_keys="KillEvent.victim_id"
    )
    assists: Mapped[list[KillEvent]] = relationship(
        back_populates="assister", foreign_keys="KillEvent.assister_id"
    )
    damage_dealt: Mapped[list[DamageEvent]] = relationship(
        back_populates="attacker", foreign_keys="DamageEvent.attacker_id"
    )
    damage_taken: Mapped[list[DamageEvent]] = relationship(
        back_populates="victim", foreign_keys="DamageEvent.victim_id"
    )
    bomb_events: Mapped[list[BombEvent]] = relationship(back_populates="player")
    grenades: Mapped[list[GrenadeThrow]] = relationship(back_populates="thrower")
    rounds_played: Mapped[list[PlayerRound]] = relationship(back_populates="player")
    map_stats: Mapped[list[PlayerMap]] = relationship(back_populates="player")
    match_stats: Mapped[list[PlayerMatch]] = relationship(back_populates="player")
    map_positions: Mapped[list[PlayerMapPosition]] = relationship(back_populates="player")
    map_weapons: Mapped[list[PlayerMapWeapon]] = relationship(back_populates="player")
    map_utility: Mapped[list[PlayerMapUtility]] = relationship(back_populates="player")
    map_routes: Mapped[list[PlayerMapRoute]] = relationship(back_populates="player")
    duels_won: Mapped[list[PlayerMapDuel]] = relationship(
        back_populates="killer", foreign_keys="PlayerMapDuel.killer_id"
    )
    duels_lost: Mapped[list[PlayerMapDuel]] = relationship(
        back_populates="victim", foreign_keys="PlayerMapDuel.victim_id"
    )

    def __str__(self) -> str:
        return self.name or str(self.steamid)


class PlayerAlias(TimestampMixin, Base):
    """Every name a player has been seen under, so an old tag still finds them."""

    __tablename__ = "player_aliases"
    __table_args__ = (UniqueConstraint("player_id", "name", name="uq_player_alias"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    player_id: Mapped[int] = mapped_column(BigId, ForeignKey("players.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64), index=True)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime6)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime6)

    player: Mapped[Player] = relationship(back_populates="aliases")

    def __str__(self) -> str:
        return f"{self.name} → {self.player_id}"


class TeamAlias(TimestampMixin, Base):
    """Maps a server-side clan name onto an HLTV team.

    ``team_clan_name`` in a demo is free text set by the match server; it will not
    always match HLTV's spelling and changes when an org renames. Resolving it
    through a table means a mismatch is fixed with one row, not by re-parsing.
    """

    __tablename__ = "team_aliases"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    clan_name: Mapped[str] = mapped_column(String(64), unique=True)
    team_id: Mapped[int] = mapped_column(BigId, ForeignKey("teams.id", ondelete="CASCADE"))
    note: Mapped[str] = mapped_column(String(200), default="")

    team: Mapped[Team] = relationship(back_populates="clan_aliases")

    def __str__(self) -> str:
        return f"{self.clan_name} → {self.team}"


class GameMap(TimestampMixin, Base):
    """A Counter-Strike map, as its own dimension.

    The radar fields turn in-game X/Y into image coordinates; they are null until
    someone wants heatmaps, and awpy ships the values to fill them.
    """

    __tablename__ = "game_maps"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, doc="Demo header name: de_anubis.")
    display_name: Mapped[str] = mapped_column(String(32), default="", doc="Anubis.")
    is_active_duty: Mapped[bool] = mapped_column(default=False)
    radar_pos_x: Mapped[float | None] = mapped_column(Float)
    radar_pos_y: Mapped[float | None] = mapped_column(Float)
    radar_scale: Mapped[float | None] = mapped_column(Float)

    played: Mapped[list[MatchMap]] = relationship(back_populates="game_map")

    def __str__(self) -> str:
        return self.display_name or self.name


# -------------------------------------------------------------- the map ------
class MatchMap(TimestampMixin, Base):
    """One map played inside a match. The anchor everything else hangs off.

    Deliberately not the same row as :class:`Demo`: that one answers "is the file
    here", this one answers "what happened". Deleting a demo to reclaim disk must
    not delete the analysis, so the link is nullable.
    """

    __tablename__ = "match_maps"
    __table_args__ = (UniqueConstraint("match_id", "map_number", name="uq_match_mapnum"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_id: Mapped[int] = mapped_column(BigId, ForeignKey("matches.id", ondelete="CASCADE"))
    demo_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("demos.id", ondelete="SET NULL"), unique=True
    )
    game_map_id: Mapped[int | None] = mapped_column(
        BigId, ForeignKey("game_maps.id", ondelete="RESTRICT")
    )
    map_number: Mapped[int] = mapped_column(PositiveSmallInt, doc="Order within the match.")
    # Never read from awpy, whose default (128) was 2x wrong for these demos.
    # Derived from the modal freeze time / 20s (H10).
    tickrate: Mapped[int | None] = mapped_column(PositiveSmallInt)
    n_rounds: Mapped[int] = mapped_column(PositiveSmallInt, default=0, doc="29 with overtime (H8).")

    team1_id: Mapped[int | None] = _team_fk()
    team2_id: Mapped[int | None] = _team_fk()
    team1_score: Mapped[int | None] = mapped_column(PositiveSmallInt)
    team2_score: Mapped[int | None] = mapped_column(PositiveSmallInt)
    winner_id: Mapped[int | None] = _team_fk()

    parsed_at: Mapped[datetime | None] = mapped_column(DateTime6)
    awpy_version: Mapped[str] = mapped_column(String(16), default="")
    schema_version: Mapped[int] = mapped_column(
        PositiveSmallInt, default=1, doc="Bump to mark every existing row stale."
    )

    match: Mapped[Match] = relationship(back_populates="map_results")
    demo: Mapped[Demo | None] = relationship(back_populates="analysis")
    game_map: Mapped[GameMap | None] = relationship(back_populates="played")
    team1: Mapped[Team | None] = relationship(foreign_keys=[team1_id])
    team2: Mapped[Team | None] = relationship(foreign_keys=[team2_id])
    winner: Mapped[Team | None] = relationship(foreign_keys=[winner_id])

    roster: Mapped[list[MapRoster]] = relationship(back_populates="match_map", passive_deletes=True)
    rounds: Mapped[list[Round]] = relationship(back_populates="match_map", passive_deletes=True)
    player_stats: Mapped[list[PlayerMap]] = relationship(
        back_populates="match_map", passive_deletes=True
    )
    tick_dataset: Mapped[TickDataset | None] = relationship(
        back_populates="match_map", passive_deletes=True
    )
    positions: Mapped[list[PlayerMapPosition]] = relationship(
        back_populates="match_map", passive_deletes=True
    )
    weapon_stats: Mapped[list[PlayerMapWeapon]] = relationship(
        back_populates="match_map", passive_deletes=True
    )
    utility_stats: Mapped[list[PlayerMapUtility]] = relationship(
        back_populates="match_map", passive_deletes=True
    )
    routes: Mapped[list[PlayerMapRoute]] = relationship(
        back_populates="match_map", passive_deletes=True
    )
    duels: Mapped[list[PlayerMapDuel]] = relationship(
        back_populates="match_map", passive_deletes=True
    )

    def __str__(self) -> str:
        return f"{self.match_id} map {self.map_number} ({self.game_map or '?'}) {self.scoreline}"

    @property
    def scoreline(self) -> str:
        if self.team1_score is None or self.team2_score is None:
            return "unplayed"
        return f"{self.team1_score}-{self.team2_score}"

    @property
    def is_parsed(self) -> bool:
        return self.parsed_at is not None

    def seconds(self, ticks: int) -> float:
        """Convert a tick count to seconds using this map's own tickrate (H10)."""
        return ticks / self.tickrate if self.tickrate else float("nan")


class MapRoster(TimestampMixin, Base):
    """A player's appearance on one map, and the one place a team is resolved.

    ``clan_name`` is kept raw alongside the resolved ``team`` so a bad or missing
    :class:`TeamAlias` can be spotted and corrected without re-parsing.
    """

    __tablename__ = "map_rosters"
    __table_args__ = (UniqueConstraint("match_map_id", "player_id", name="uq_map_player"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_map_id: Mapped[int] = _match_map_fk()
    player_id: Mapped[int] = _player_fk()
    team_id: Mapped[int | None] = _team_fk()
    clan_name: Mapped[str] = mapped_column(String(64), default="", doc="Raw team_clan_name (H1).")
    display_name: Mapped[str] = mapped_column(String(64), default="", doc="Name in this demo.")
    # From player_round_totals.csv, whose side buckets are the correct
    # denominators for any side-split rate.
    rounds_ct: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    rounds_t: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    rounds_total: Mapped[int] = mapped_column(PositiveSmallInt, default=0)

    match_map: Mapped[MatchMap] = relationship(back_populates="roster")
    player: Mapped[Player] = relationship(back_populates="map_appearances")
    team: Mapped[Team | None] = relationship()

    def __str__(self) -> str:
        return f"{self.display_name or self.player} @ {self.match_map_id}"


class Round(TimestampMixin, Base):
    """One round. The spine every event hangs off.

    ``winner_side`` is what awpy reports; ``winner_team`` is what analysis needs.
    Sides swap at half, so a tally of "ct won" is not a team's score (H1). The
    ``ct_team``/``t_team`` pair records the mapping for this round so the
    conversion happens once, at ingest.
    """

    __tablename__ = "rounds"
    __table_args__ = (UniqueConstraint("match_map_id", "number", name="uq_map_round"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_map_id: Mapped[int] = _match_map_fk()
    number: Mapped[int] = mapped_column(PositiveSmallInt)

    start_tick: Mapped[int] = mapped_column(PositiveInt)
    freeze_end_tick: Mapped[int] = mapped_column(PositiveInt, doc="Buy time ends.")
    end_tick: Mapped[int] = mapped_column(PositiveInt)
    official_end_tick: Mapped[int] = mapped_column(PositiveInt, doc="Includes the post-round.")

    winner_side: Mapped[str] = mapped_column(String(3), default="")
    winner_team_id: Mapped[int | None] = _team_fk()
    ct_team_id: Mapped[int | None] = _team_fk()
    t_team_id: Mapped[int | None] = _team_fk()

    # Free text on purpose: time-expiry and surrender reasons exist beyond the
    # ct_killed / t_killed / bomb_defused / bomb_exploded seen so far.
    end_reason: Mapped[str] = mapped_column(String(24), default="")
    bomb_plant_tick: Mapped[int | None] = mapped_column(PositiveInt)
    bomb_site: Mapped[str] = mapped_column(String(8), default="", doc="'A'/'B'/'' (H5).")

    # Each side's summed equipment value as the round went live, and the Buy type
    # read from it. Null and '' on a map parsed before schema 11 that was never
    # downloaded again (docs/adr/0003).
    ct_equip_value: Mapped[int | None] = mapped_column(PositiveInt)
    t_equip_value: Mapped[int | None] = mapped_column(PositiveInt)
    ct_buy: Mapped[str] = mapped_column(String(8), default="", doc="A BuyType value, or ''.")
    t_buy: Mapped[str] = mapped_column(String(8), default="", doc="A BuyType value, or ''.")
    # Schema 14 (DATA-5): which timeouts ran in this round's freeze time, called
    # by the Side named; None where the Tick Data predates them.
    ct_timeout: Mapped[bool | None] = mapped_column()
    t_timeout: Mapped[bool | None] = mapped_column()
    tech_timeout: Mapped[bool | None] = mapped_column()

    match_map: Mapped[MatchMap] = relationship(back_populates="rounds")
    winner_team: Mapped[Team | None] = relationship(foreign_keys=[winner_team_id])
    ct_team: Mapped[Team | None] = relationship(foreign_keys=[ct_team_id])
    t_team: Mapped[Team | None] = relationship(foreign_keys=[t_team_id])

    kills: Mapped[list[KillEvent]] = relationship(back_populates="round", passive_deletes=True)
    damages: Mapped[list[DamageEvent]] = relationship(back_populates="round", passive_deletes=True)
    bomb_events: Mapped[list[BombEvent]] = relationship(
        back_populates="round", passive_deletes=True
    )
    grenades: Mapped[list[GrenadeThrow]] = relationship(
        back_populates="round", passive_deletes=True
    )
    player_rounds: Mapped[list[PlayerRound]] = relationship(
        back_populates="round", passive_deletes=True
    )
    snapshots: Mapped[list[RoundSnapshot]] = relationship(
        back_populates="round", passive_deletes=True
    )

    def __str__(self) -> str:
        return f"{self.match_map_id} R{self.number} {self.winner_side} ({self.end_reason})"

    @property
    def was_planted(self) -> bool:
        return self.bomb_plant_tick is not None

    @property
    def duration_ticks(self) -> int:
        return self.end_tick - self.freeze_end_tick


# ---------------------------------------------------------------- events ------
class KillEvent(TimestampMixin, Base):
    """One death, from kills.csv (26 of its 52 columns).

    The situational flags are the point: they separate an entry frag through
    smoke from a trade off a teammate's death.
    """

    __tablename__ = "kill_events"
    __table_args__ = (
        Index("ix_kill_events_round_id_tick", "round_id", "tick"),
        Index("ix_kill_events_attacker_id", "attacker_id"),
        Index("ix_kill_events_victim_id", "victim_id"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    round_id: Mapped[int] = _round_fk()
    tick: Mapped[int] = mapped_column(PositiveInt)

    # Nullable: bomb deaths, fall damage and suicides have no attacker (H3).
    attacker_id: Mapped[int | None] = _player_fk(nullable=True)
    victim_id: Mapped[int] = _player_fk()
    assister_id: Mapped[int | None] = _player_fk(nullable=True)
    attacker_side: Mapped[str] = mapped_column(String(3), default="")
    victim_side: Mapped[str] = mapped_column(String(3), default="")

    weapon: Mapped[str] = mapped_column(String(32), index=True)
    hitgroup: Mapped[str] = mapped_column(String(16), default="", doc="'-1' normalised to '' (H4).")
    headshot: Mapped[bool] = mapped_column(default=False)
    distance: Mapped[float | None] = mapped_column(Float)
    dmg_health: Mapped[int] = mapped_column(Integer, default=0, doc="The killing blow only.")
    dmg_armor: Mapped[int] = mapped_column(Integer, default=0)
    penetrated: Mapped[int] = mapped_column(Integer, default=0, doc="Walls shot through.")

    thrusmoke: Mapped[bool] = mapped_column(default=False)
    noscope: Mapped[bool] = mapped_column(default=False)
    attackerblind: Mapped[bool] = mapped_column(default=False)
    attackerinair: Mapped[bool] = mapped_column(default=False)
    assistedflash: Mapped[bool] = mapped_column(default=False)

    attacker_x: Mapped[float | None] = mapped_column(Float)
    attacker_y: Mapped[float | None] = mapped_column(Float)
    attacker_z: Mapped[float | None] = mapped_column(Float)
    victim_x: Mapped[float | None] = mapped_column(Float)
    victim_y: Mapped[float | None] = mapped_column(Float)
    victim_z: Mapped[float | None] = mapped_column(Float)
    attacker_place: Mapped[str] = mapped_column(String(24), default="")
    victim_place: Mapped[str] = mapped_column(String(24), default="")
    attacker_health: Mapped[float | None] = mapped_column(Float, doc="Was the winner hurt.")
    victim_health: Mapped[int | None] = mapped_column(Integer, doc="Health before the blow.")

    round: Mapped[Round] = relationship(back_populates="kills")
    attacker: Mapped[Player | None] = relationship(
        back_populates="kills_made", foreign_keys=[attacker_id]
    )
    victim: Mapped[Player] = relationship(back_populates="deaths", foreign_keys=[victim_id])
    assister: Mapped[Player | None] = relationship(
        back_populates="assists", foreign_keys=[assister_id]
    )

    def __str__(self) -> str:
        return f"{self.attacker or 'world'} → {self.victim} ({self.weapon})"


class DamageEvent(TimestampMixin, Base):
    """One damage tick, from damages.csv.

    ``damage`` is ``dmg_health_real``, capped at what the victim could absorb.
    ``damage_raw`` is what the weapon would have dealt; ADR built on it is
    inflated uniformly and invisibly (H6).
    """

    __tablename__ = "damage_events"
    __table_args__ = (
        Index("ix_damage_events_round_id_tick", "round_id", "tick"),
        Index("ix_damage_events_attacker_id", "attacker_id"),
        Index("ix_damage_events_victim_id", "victim_id"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    round_id: Mapped[int] = _round_fk()
    tick: Mapped[int] = mapped_column(PositiveInt)

    attacker_id: Mapped[int | None] = _player_fk(nullable=True)
    victim_id: Mapped[int] = _player_fk()
    attacker_side: Mapped[str] = mapped_column(String(3), default="")
    victim_side: Mapped[str] = mapped_column(String(3), default="")

    weapon: Mapped[str] = mapped_column(String(32), index=True)
    hitgroup: Mapped[str] = mapped_column(String(16), default="")
    damage: Mapped[int] = mapped_column(PositiveSmallInt, default=0, doc="dmg_health_real.")
    damage_raw: Mapped[int] = mapped_column(PositiveSmallInt, default=0, doc="Uncapped.")
    damage_armor: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    victim_health_before: Mapped[int | None] = mapped_column(Integer)
    victim_health_after: Mapped[int | None] = mapped_column(Integer)
    attacker_place: Mapped[str] = mapped_column(String(24), default="")
    victim_place: Mapped[str] = mapped_column(String(24), default="")

    round: Mapped[Round] = relationship(back_populates="damages")
    attacker: Mapped[Player | None] = relationship(
        back_populates="damage_dealt", foreign_keys=[attacker_id]
    )
    victim: Mapped[Player] = relationship(back_populates="damage_taken", foreign_keys=[victim_id])

    def __str__(self) -> str:
        return f"{self.attacker or 'world'} → {self.victim} {self.damage} ({self.hitgroup})"


class BombEventType(StrEnum):
    PLANT = "plant"
    DEFUSE = "defuse"
    DETONATE = "detonate"
    PICKUP = "pickup"
    DROP = "drop"


class BombEvent(TimestampMixin, Base):
    """One bomb action, from bomb.csv. Retake analysis is mostly this plus Round."""

    __tablename__ = "bomb_events"
    __table_args__ = (Index("ix_bomb_events_round_id_tick", "round_id", "tick"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    round_id: Mapped[int] = _round_fk()
    tick: Mapped[int] = mapped_column(PositiveInt)
    event: Mapped[str] = mapped_column(String(12), index=True, doc="A BombEventType value.")
    player_id: Mapped[int | None] = _player_fk(nullable=True)
    bombsite: Mapped[str] = mapped_column(String(8), default="", doc="'A'/'B'/'' (H5).")
    # Where the bomb was planted decides the shape of the retake.
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    z: Mapped[float | None] = mapped_column(Float)

    round: Mapped[Round] = relationship(back_populates="bomb_events")
    player: Mapped[Player | None] = relationship(back_populates="bomb_events")

    def __str__(self) -> str:
        return f"R{self.round_id} {self.event} {self.bombsite}".strip()


class GrenadeType(StrEnum):
    SMOKE = "smoke"
    INFERNO = "inferno"  # Molotov / Incendiary
    FLASH = "flash"
    HE = "he"


class GrenadeThrow(TimestampMixin, Base):
    """One thrown grenade: smokes/infernos (a lifetime) and flashes/HEs (a moment).

    Not awpy's ``grenades`` trajectory table, where most rows are grenades sitting
    in an inventory and ``entity_id`` repeats across rounds (H2). Hence the key
    is ``(round, entity_id, type)``.

    ``start_tick``/``end_tick`` are the lifetime of the *effect* (the smoke cloud
    or the fire). Flashes and HEs only have a detonate tick (``throw_tick``), so
    their start/end are null.
    """

    __tablename__ = "grenade_throws"
    __table_args__ = (
        UniqueConstraint("round_id", "entity_id", "type", name="uq_round_grenade"),
        Index("ix_grenade_throws_round_id_type", "round_id", "type"),
        Index("ix_grenade_throws_thrower_id", "thrower_id"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    round_id: Mapped[int] = _round_fk()
    entity_id: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(12), index=True, doc="A GrenadeType value.")

    thrower_id: Mapped[int | None] = _player_fk(nullable=True)
    thrower_side: Mapped[str] = mapped_column(String(3), default="")

    throw_tick: Mapped[int | None] = mapped_column(PositiveInt)
    start_tick: Mapped[int | None] = mapped_column(PositiveInt, doc="Effect begins.")
    end_tick: Mapped[int | None] = mapped_column(PositiveInt, doc="Effect ends.")

    # Where it was thrown from: the lineup.
    thrower_x: Mapped[float | None] = mapped_column(Float)
    thrower_y: Mapped[float | None] = mapped_column(Float)
    thrower_z: Mapped[float | None] = mapped_column(Float)
    # The moment it left the hand, from where and with what aim (schema 14,
    # DATA-5): the projectile's first point and the thrower's tick there. Unlike
    # throw_tick and thrower_* (a flash's or HE's pop, and where the thrower
    # stood then), these are the lineup. None before.
    thrown_tick: Mapped[int | None] = mapped_column(PositiveInt)
    thrown_x: Mapped[float | None] = mapped_column(Float)
    thrown_y: Mapped[float | None] = mapped_column(Float)
    thrown_z: Mapped[float | None] = mapped_column(Float)
    thrown_pitch: Mapped[float | None] = mapped_column(Float)
    thrown_yaw: Mapped[float | None] = mapped_column(Float)
    thrown_place: Mapped[str] = mapped_column(String(24), default="")
    # Where it landed.
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    z: Mapped[float | None] = mapped_column(Float)
    thrower_place: Mapped[str] = mapped_column(String(24), default="")
    place: Mapped[str] = mapped_column(
        String(24), default="", doc="The Callout it landed in, read off the Tick Data."
    )

    round: Mapped[Round] = relationship(back_populates="grenades")
    thrower: Mapped[Player | None] = relationship(back_populates="grenades")

    def __str__(self) -> str:
        return f"{self.type} by {self.thrower or '?'} R{self.round_id}"


class SnapshotMoment(StrEnum):
    SETUP = "setup"  # SETUP_SECONDS after freeze end (CONTEXT.md: Setup)
    PLANT = "plant"  # the tick the bomb went down


class RoundSnapshot(TimestampMixin, Base):
    """Where one living player stood at one moment of a round.

    Cut from the Tick Data at ingest, so the Playbook can read Setups and who was
    where when the bomb went down without opening the Tick Data on a page view.
    """

    __tablename__ = "round_snapshots"
    __table_args__ = (
        UniqueConstraint("round_id", "player_id", "moment", name="uq_round_snapshot"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    round_id: Mapped[int] = _round_fk()
    player_id: Mapped[int] = _player_fk()
    moment: Mapped[str] = mapped_column(String(8), doc="A SnapshotMoment value.")
    side: Mapped[str] = mapped_column(String(3), default="")
    place: Mapped[str] = mapped_column(String(24), default="")
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    z: Mapped[float | None] = mapped_column(Float)

    round: Mapped[Round] = relationship(back_populates="snapshots")
    player: Mapped[Player] = relationship()


# --------------------------------------------------------------- rollups ------
class PlayerRound(TimestampMixin, Base):
    """player x round, derived from the event tables rather than from any CSV.

    KAST and opening duels are already resolved here, so a season-wide query
    does not have to re-scan every kill.
    """

    __tablename__ = "player_rounds"
    __table_args__ = (
        UniqueConstraint("round_id", "player_id", name="uq_round_player"),
        Index("ix_player_rounds_player_id_side", "player_id", "side"),
        Index("ix_player_rounds_player_id_round_id", "player_id", "round_id"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    round_id: Mapped[int] = _round_fk()
    player_id: Mapped[int] = _player_fk()
    team_id: Mapped[int | None] = _team_fk()
    side: Mapped[str] = mapped_column(String(3), default="")

    kills: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    deaths: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    assists: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    damage: Mapped[int] = mapped_column(PositiveSmallInt, default=0, doc="Sum of dmg_health_real.")

    survived: Mapped[bool] = mapped_column(default=False)
    traded: Mapped[bool] = mapped_column(default=False, doc="Avenged inside the trade window.")
    opening_kill: Mapped[bool] = mapped_column(default=False)
    opening_death: Mapped[bool] = mapped_column(default=False)
    kast: Mapped[bool] = mapped_column(default=False, doc="Kill, assist, survived or traded.")

    # What the player carried and had left as the round went live (schema 11; null
    # before it, see Round.ct_equip_value).
    money: Mapped[int | None] = mapped_column(PositiveSmallInt, doc="Left after buying.")
    equip_value: Mapped[int | None] = mapped_column(PositiveSmallInt)
    armor: Mapped[int | None] = mapped_column(PositiveSmallInt)
    helmet: Mapped[bool | None] = mapped_column()
    defuser: Mapped[bool | None] = mapped_column()
    # The scoreboard's own numbers for the round (schema 14, DATA-5); None before.
    enemies_flashed: Mapped[int | None] = mapped_column(PositiveSmallInt)
    utility_damage: Mapped[int | None] = mapped_column(PositiveSmallInt)
    money_saved: Mapped[int | None] = mapped_column(PositiveSmallInt)
    kill_reward: Mapped[int | None] = mapped_column(PositiveSmallInt)
    primary_weapon: Mapped[str] = mapped_column(
        String(16), default="", doc="'AK-47', 'AWP'... as the demo names it, or ''."
    )

    round: Mapped[Round] = relationship(back_populates="player_rounds")
    player: Mapped[Player] = relationship(back_populates="rounds_played")
    team: Mapped[Team | None] = relationship()

    def __str__(self) -> str:
        return f"{self.player} R{self.round_id} {self.kills}/{self.deaths}"


class PlayerMap(TimestampMixin, Base):
    """The scoreboard row: player x map.

    Derivable from :class:`PlayerRound`, stored because it is read constantly.
    ``kd_diff`` is deliberately signed: subtracting awpy's UInt32 counts without
    a cast turns -4 into 4,294,967,292 (H7).
    """

    __tablename__ = "player_maps"
    __table_args__ = (
        UniqueConstraint("match_map_id", "player_id", name="uq_map_playerstat"),
        Index("ix_player_maps_player_id_match_map_id", "player_id", "match_map_id"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_map_id: Mapped[int] = _match_map_fk()
    player_id: Mapped[int] = _player_fk()
    team_id: Mapped[int | None] = _team_fk()

    rounds_played: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    kills: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    deaths: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    assists: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    headshots: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    kd_diff: Mapped[int] = mapped_column(SmallInteger, default=0)
    damage: Mapped[int] = mapped_column(PositiveInt, default=0)

    adr: Mapped[float | None] = mapped_column(Float)
    hs_pct: Mapped[float | None] = mapped_column(Float)
    kast_pct: Mapped[float | None] = mapped_column(Float)
    opening_kills: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    opening_deaths: Mapped[int] = mapped_column(PositiveSmallInt, default=0)

    match_map: Mapped[MatchMap] = relationship(back_populates="player_stats")
    player: Mapped[Player] = relationship(back_populates="map_stats")
    team: Mapped[Team | None] = relationship()

    def __str__(self) -> str:
        return f"{self.player} {self.kills}-{self.deaths} ({self.adr} ADR)"


class PlayerMatch(TimestampMixin, Base):
    """player x match: the same numbers summed across the maps of one series."""

    __tablename__ = "player_matches"
    __table_args__ = (
        UniqueConstraint("match_id", "player_id", name="uq_match_playerstat"),
        Index("ix_player_matches_player_id_match_id", "player_id", "match_id"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_id: Mapped[int] = mapped_column(BigId, ForeignKey("matches.id", ondelete="CASCADE"))
    player_id: Mapped[int] = _player_fk()
    team_id: Mapped[int | None] = _team_fk()

    maps_played: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    rounds_played: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    kills: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    deaths: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    assists: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    headshots: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    kd_diff: Mapped[int] = mapped_column(SmallInteger, default=0)
    damage: Mapped[int] = mapped_column(PositiveInt, default=0)

    adr: Mapped[float | None] = mapped_column(Float)
    hs_pct: Mapped[float | None] = mapped_column(Float)
    kast_pct: Mapped[float | None] = mapped_column(Float)
    opening_kills: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    opening_deaths: Mapped[int] = mapped_column(PositiveSmallInt, default=0)

    match: Mapped[Match] = relationship(back_populates="player_stats")
    player: Mapped[Player] = relationship(back_populates="match_stats")
    team: Mapped[Team | None] = relationship()

    def __str__(self) -> str:
        return f"{self.player} {self.kills}-{self.deaths} over {self.maps_played} map(s)"


class TickDataset(TimestampMixin, Base):
    """A Match Map's Tick Data, and what the pages need cut from it.

    ``bundle`` is awpy's zipped parquet dump (ticks, grenade flights, footsteps,
    shots, the event tables, ``header.json``) plus the flashbang and HE
    detonations the ingest also reads: everything a re-parse needs, so the Demo
    can be deleted once it is parsed. About 10 MB a map, against 300-470 MB of
    ``.dem``. It is never read on a page view; ``geometry``, ``walks`` and the
    map's ``ReplayRound`` rows are cut from it at ingest, and rebuilt from it
    when ``derived_version`` falls behind (see ``app/services/tickdata.py``).
    The two blobs are deferred, so loading the row does not load them.
    """

    __tablename__ = "tick_datasets"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_map_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("match_maps.id", ondelete="CASCADE"), unique=True
    )
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    tables: Mapped[list] = mapped_column(JSON, default=list, doc="e.g. ['ticks', 'grenades'].")
    awpy_version: Mapped[str] = mapped_column(String(16), default="")
    bundle: Mapped[bytes] = mapped_column(LongBlob, deferred=True)
    geometry: Mapped[dict] = mapped_column(
        JSON, default=dict, doc="Callout labels per floor, and how each room splits by floor."
    )
    walks: Mapped[bytes | None] = mapped_column(
        MediumBlob, deferred=True, doc="gzip JSON: each route's walks, simplified."
    )
    replay: Mapped[dict] = mapped_column(JSON, default=dict, doc="hz and the round index.")
    derived_version: Mapped[str] = mapped_column(String(16), default="")

    match_map: Mapped[MatchMap] = relationship(back_populates="tick_dataset")

    def __str__(self) -> str:
        return f"map {self.match_map_id} ({', '.join(self.tables) if self.tables else 'empty'})"


class ReplayRound(Base):
    """One round of a Replay, ready to send: gzip JSON, served as it is stored.

    Cut from the Tick Data at ingest (8 frames a second, ~25 KB compressed), so
    the API answers a round with one row read and never touches parquet.
    """

    __tablename__ = "replay_rounds"
    __table_args__ = (UniqueConstraint("match_map_id", "number", name="uq_replay_round"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_map_id: Mapped[int] = _match_map_fk()
    number: Mapped[int] = mapped_column(PositiveSmallInt)
    payload: Mapped[bytes] = mapped_column(MediumBlob)
    # VIZ-7: gzip JSON, each second how many of each Side stood in each Callout,
    # for the Round search; None until the Replay is cut at REPLAY_SCHEMA 7.
    tokens: Mapped[bytes | None] = mapped_column(MediumBlob)


class MatchMapReview(TimestampMixin, Base):
    """A Match Map's Review (CONTEXT.md), cut from its Tick Data: gzip JSON.

    Stored structured (who, when, where, how much Swing), worded on read by
    ``app/services/review_view.py``. ``version`` is ``review.version()`` at build
    time; a mismatch rebuilds it from the Tick Data on the next read.
    """

    __tablename__ = "match_map_reviews"

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_map_id: Mapped[int] = mapped_column(
        BigId, ForeignKey("match_maps.id", ondelete="CASCADE"), unique=True
    )
    version: Mapped[str] = mapped_column(String(48), default="")
    # The Map's Spots it was built with (spots.version(map)), apart from ``version``
    # so that editing one Map's Spots rebuilds that Map's Reviews only (VIZ-11).
    spots_version: Mapped[str] = mapped_column(String(8), default="")
    sightings: Mapped[bool] = mapped_column(default=False, doc="Built with Sightings (schema 13).")
    payload: Mapped[bytes] = mapped_column(MediumBlob)


# --------------------------------------------------- per-player, per-map ------
class PositionKind(StrEnum):
    KILL_FROM = "kill_from"
    VICTIM_AT = "victim_at"
    DEATH_AT = "death_at"


class PlayerMapPosition(TimestampMixin, Base):
    """Where one player killed and died **on one map**.

    Map-scoped on purpose: "BombsiteB" on Anubis and on Cache are different rooms.
    Rows are stored per side; "both halves" is the sum, never a fourth row.
    """

    __tablename__ = "player_map_positions"
    __table_args__ = (
        UniqueConstraint(
            "match_map_id",
            "player_id",
            "kind",
            "side",
            "place",
            name="uq_map_player_kind_side_place",
        ),
        Index("ix_player_map_positions_player_id_kind", "player_id", "kind"),
        Index("ix_player_map_positions_match_map_id_kind", "match_map_id", "kind"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_map_id: Mapped[int] = _match_map_fk()
    player_id: Mapped[int] = _player_fk()
    team_id: Mapped[int | None] = _team_fk()
    kind: Mapped[str] = mapped_column(String(12), index=True, doc="A PositionKind value.")
    side: Mapped[str] = mapped_column(String(3), default="", index=True)
    place: Mapped[str] = mapped_column(String(24))
    count: Mapped[int] = mapped_column(PositiveSmallInt, default=0)

    match_map: Mapped[MatchMap] = relationship(back_populates="positions")
    player: Mapped[Player] = relationship(back_populates="map_positions")
    team: Mapped[Team | None] = relationship()

    def __str__(self) -> str:
        return f"{self.player} {self.kind} {self.place} ×{self.count}"


class PlayerMapWeapon(TimestampMixin, Base):
    """One player's record with one weapon family, on one map.

    ``weapon`` is the *family*: the kill and damage feeds name the same gun
    differently (``usp_silencer`` against ``hkp2000``).
    """

    __tablename__ = "player_map_weapons"
    __table_args__ = (
        UniqueConstraint(
            "match_map_id", "player_id", "weapon", "side", name="uq_map_player_weapon_side"
        ),
        Index("ix_player_map_weapons_player_id_weapon", "player_id", "weapon"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_map_id: Mapped[int] = _match_map_fk()
    player_id: Mapped[int] = _player_fk()
    team_id: Mapped[int | None] = _team_fk()
    weapon: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(3), default="", index=True)
    kills: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    headshots: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    damage: Mapped[int] = mapped_column(PositiveInt, default=0)
    hits: Mapped[int] = mapped_column(PositiveSmallInt, default=0)

    match_map: Mapped[MatchMap] = relationship(back_populates="weapon_stats")
    player: Mapped[Player] = relationship(back_populates="map_weapons")
    team: Mapped[Team | None] = relationship()

    def __str__(self) -> str:
        return f"{self.player} {self.weapon} {self.kills}k"

    @property
    def converts(self) -> bool:
        """Did this weapon actually finish anyone for them."""
        return self.kills > 0

    @property
    def damage_per_kill(self) -> int | None:
        return round(self.damage / self.kills) if self.kills and self.damage else None

    @property
    def hs_pct(self) -> float | None:
        return round(self.headshots / self.kills * 100, 1) if self.kills else None


class PlayerMapUtility(TimestampMixin, Base):
    """One player's utility on one map, and whether it did anything.

    Molotovs are thrown to deny space, so their damage is a poor verdict; only a
    molotov that burned nobody at all is notable.
    """

    __tablename__ = "player_map_utilities"
    __table_args__ = (
        UniqueConstraint("match_map_id", "player_id", "side", name="uq_map_player_side_utility"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_map_id: Mapped[int] = _match_map_fk()
    player_id: Mapped[int] = _player_fk()
    team_id: Mapped[int | None] = _team_fk()
    side: Mapped[str] = mapped_column(String(3), default="", index=True)

    smokes: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    infernos: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    fire_damage: Mapped[int] = mapped_column(PositiveInt, default=0)
    he_damage: Mapped[int] = mapped_column(PositiveInt, default=0)
    flash_assists: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    # Rounds with at least one smoke from this player, and how many of those their
    # team won: correlation, with the baseline alongside it.
    smoke_rounds: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    smoke_rounds_won: Mapped[int] = mapped_column(PositiveSmallInt, default=0)

    match_map: Mapped[MatchMap] = relationship(back_populates="utility_stats")
    player: Mapped[Player] = relationship(back_populates="map_utility")
    team: Mapped[Team | None] = relationship()

    def __str__(self) -> str:
        return f"{self.player} utility on {self.match_map_id}"

    @property
    def damage_per_inferno(self) -> float | None:
        return round(self.fire_damage / self.infernos, 1) if self.infernos else None

    @property
    def smoke_win_pct(self) -> float | None:
        if not self.smoke_rounds:
            return None
        return round(self.smoke_rounds_won / self.smoke_rounds * 100, 1)


class PlayerMapRoute(TimestampMixin, Base):
    """A path one player actually walks on one map, and what it tends to produce.

    The route is the sequence of callouts passed through after freeze time, with
    consecutive repeats collapsed: "TSpawn → Street → TStairs → Canal". Coarse on
    purpose, so the same approach taken in twenty rounds groups into one row.
    """

    __tablename__ = "player_map_routes"
    __table_args__ = (
        UniqueConstraint(
            "match_map_id", "player_id", "side", "route_key", name="uq_map_player_route"
        ),
        Index("ix_player_map_routes_player_id_match_map_id", "player_id", "match_map_id"),
        Index("ix_player_map_routes_match_map_id_side", "match_map_id", "side"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_map_id: Mapped[int] = _match_map_fk()
    player_id: Mapped[int] = _player_fk()
    team_id: Mapped[int | None] = _team_fk()
    side: Mapped[str] = mapped_column(String(3), default="")

    route_key: Mapped[str] = mapped_column(String(200), doc="Callouts joined by >.")
    places: Mapped[list] = mapped_column(JSON, default=list, doc="The callouts, in order.")
    # Mean X/Y at each step, so the route can be drawn without re-reading ticks.
    path: Mapped[list] = mapped_column(JSON, default=list, doc="[{place, x, y}] centroids.")

    rounds: Mapped[int] = mapped_column(PositiveSmallInt, default=0, doc="Times taken.")
    kills: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    deaths: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    rounds_won: Mapped[int] = mapped_column(PositiveSmallInt, default=0)

    match_map: Mapped[MatchMap] = relationship(back_populates="routes")
    player: Mapped[Player] = relationship(back_populates="map_routes")
    team: Mapped[Team | None] = relationship()

    def __str__(self) -> str:
        return f"{self.player} {self.route_key} ×{self.rounds}"

    @property
    def label(self) -> str:
        return " → ".join(self.places)

    @property
    def kills_per_round(self) -> float | None:
        return round(self.kills / self.rounds, 2) if self.rounds else None

    @property
    def deaths_per_round(self) -> float | None:
        return round(self.deaths / self.rounds, 2) if self.rounds else None

    @property
    def win_pct(self) -> float | None:
        return round(self.rounds_won / self.rounds * 100, 1) if self.rounds else None

    @property
    def net_per_round(self) -> float:
        """Kills minus deaths per round: what the colour scale is built on."""
        return round((self.kills - self.deaths) / self.rounds, 2) if self.rounds else 0.0

    @property
    def verdict(self) -> str:
        """Red, amber or green, from the route's own numbers."""
        net = self.net_per_round
        if net >= 0.35:
            return "good"
        if net <= -0.35:
            return "bad"
        return "even"


class PlayerMapDuel(TimestampMixin, Base):
    """One player killing another, aggregated per map, side and position pair.

    Rows are directional (killer to victim), so a matchup is read by pairing a
    row with its mirror. At most one row per distinct (killer, victim, side,
    where each stood), so a few hundred per map.
    """

    __tablename__ = "player_map_duels"
    __table_args__ = (
        UniqueConstraint(
            "match_map_id",
            "killer_id",
            "victim_id",
            "side",
            "killer_place",
            "victim_place",
            name="uq_map_duel",
        ),
        Index("ix_player_map_duels_killer_id_victim_id", "killer_id", "victim_id"),
        Index("ix_player_map_duels_match_map_id_killer_team_id", "match_map_id", "killer_team_id"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    match_map_id: Mapped[int] = _match_map_fk()
    killer_id: Mapped[int] = _player_fk()
    victim_id: Mapped[int] = _player_fk()
    killer_team_id: Mapped[int | None] = _team_fk()
    victim_team_id: Mapped[int | None] = _team_fk()
    side: Mapped[str] = mapped_column(String(3), default="", doc="The killer's side.")
    killer_place: Mapped[str] = mapped_column(String(24), default="")
    victim_place: Mapped[str] = mapped_column(String(24), default="")

    kills: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    headshots: Mapped[int] = mapped_column(PositiveSmallInt, default=0)
    opening_kills: Mapped[int] = mapped_column(
        PositiveSmallInt, default=0, doc="Of these, how many were the round's first kill."
    )

    match_map: Mapped[MatchMap] = relationship(back_populates="duels")
    killer: Mapped[Player] = relationship(back_populates="duels_won", foreign_keys=[killer_id])
    victim: Mapped[Player] = relationship(back_populates="duels_lost", foreign_keys=[victim_id])
    killer_team: Mapped[Team | None] = relationship(foreign_keys=[killer_team_id])
    victim_team: Mapped[Team | None] = relationship(foreign_keys=[victim_team_id])

    def __str__(self) -> str:
        return f"{self.killer} → {self.victim} ×{self.kills}"
