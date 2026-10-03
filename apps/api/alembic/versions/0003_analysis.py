"""analysis

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "game_maps",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=32), nullable=False),
        sa.Column("is_active_duty", sa.Boolean(), nullable=False),
        sa.Column("radar_pos_x", sa.Double(), nullable=True),
        sa.Column("radar_pos_y", sa.Double(), nullable=True),
        sa.Column("radar_scale", sa.Double(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_maps")),
        sa.UniqueConstraint("name", name=op.f("uq_game_maps_name")),
    )
    op.create_table(
        "players",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("steamid", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "first_seen", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=True
        ),
        sa.Column(
            "last_seen", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_players")),
        sa.UniqueConstraint("steamid", name=op.f("uq_players_steamid")),
    )
    op.create_index(op.f("ix_players_name"), "players", ["name"], unique=False)
    op.create_table(
        "player_aliases",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "first_seen", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=True
        ),
        sa.Column(
            "last_seen", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_aliases_player_id_players"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_aliases")),
        sa.UniqueConstraint("player_id", "name", name="uq_player_alias"),
    )
    op.create_index(op.f("ix_player_aliases_name"), "player_aliases", ["name"], unique=False)
    op.create_table(
        "team_aliases",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("clan_name", sa.String(length=64), nullable=False),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_team_aliases_team_id_teams"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_aliases")),
        sa.UniqueConstraint("clan_name", name=op.f("uq_team_aliases_clan_name")),
    )
    op.create_table(
        "player_matches",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("match_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column(
            "maps_played",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "rounds_played",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "kills",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "deaths",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "assists",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "headshots",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("kd_diff", sa.SmallInteger(), nullable=False),
        sa.Column(
            "damage",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("adr", sa.Double(), nullable=True),
        sa.Column("hs_pct", sa.Double(), nullable=True),
        sa.Column("kast_pct", sa.Double(), nullable=True),
        sa.Column(
            "opening_kills",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "opening_deaths",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_player_matches_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_matches_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_player_matches_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_matches")),
        sa.UniqueConstraint("match_id", "player_id", name="uq_match_playerstat"),
    )
    op.create_index(
        "ix_player_matches_player_id_match_id",
        "player_matches",
        ["player_id", "match_id"],
        unique=False,
    )
    op.create_table(
        "match_maps",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("match_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("demo_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column(
            "game_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column(
            "map_number",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "tickrate",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=True,
        ),
        sa.Column(
            "n_rounds",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("team1_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("team2_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column(
            "team1_score",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=True,
        ),
        sa.Column(
            "team2_score",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=True,
        ),
        sa.Column("winner_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("parquet_path", sa.String(length=500), nullable=False),
        sa.Column(
            "parsed_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=True
        ),
        sa.Column("awpy_version", sa.String(length=16), nullable=False),
        sa.Column(
            "schema_version",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["demo_id"], ["demos.id"], name=op.f("fk_match_maps_demo_id_demos"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["game_map_id"],
            ["game_maps.id"],
            name=op.f("fk_match_maps_game_map_id_game_maps"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_match_maps_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team1_id"],
            ["teams.id"],
            name=op.f("fk_match_maps_team1_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team2_id"],
            ["teams.id"],
            name=op.f("fk_match_maps_team2_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["winner_id"],
            ["teams.id"],
            name=op.f("fk_match_maps_winner_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_maps")),
        sa.UniqueConstraint("demo_id", name=op.f("uq_match_maps_demo_id")),
        sa.UniqueConstraint("match_id", "map_number", name="uq_match_mapnum"),
    )
    op.create_table(
        "map_rosters",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "match_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("clan_name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column(
            "rounds_ct",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "rounds_t",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "rounds_total",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["match_map_id"],
            ["match_maps.id"],
            name=op.f("fk_map_rosters_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_map_rosters_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_map_rosters_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_map_rosters")),
        sa.UniqueConstraint("match_map_id", "player_id", name="uq_map_player"),
    )
    op.create_table(
        "player_map_duels",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "match_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "killer_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "victim_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "killer_team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column(
            "victim_team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column("side", sa.String(length=3), nullable=False),
        sa.Column("killer_place", sa.String(length=24), nullable=False),
        sa.Column("victim_place", sa.String(length=24), nullable=False),
        sa.Column(
            "kills",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "headshots",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "opening_kills",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["killer_id"],
            ["players.id"],
            name=op.f("fk_player_map_duels_killer_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["killer_team_id"],
            ["teams.id"],
            name=op.f("fk_player_map_duels_killer_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["match_map_id"],
            ["match_maps.id"],
            name=op.f("fk_player_map_duels_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["victim_id"],
            ["players.id"],
            name=op.f("fk_player_map_duels_victim_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["victim_team_id"],
            ["teams.id"],
            name=op.f("fk_player_map_duels_victim_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_map_duels")),
        sa.UniqueConstraint(
            "match_map_id",
            "killer_id",
            "victim_id",
            "side",
            "killer_place",
            "victim_place",
            name="uq_map_duel",
        ),
    )
    op.create_index(
        "ix_player_map_duels_killer_id_victim_id",
        "player_map_duels",
        ["killer_id", "victim_id"],
        unique=False,
    )
    op.create_index(
        "ix_player_map_duels_match_map_id_killer_team_id",
        "player_map_duels",
        ["match_map_id", "killer_team_id"],
        unique=False,
    )
    op.create_table(
        "player_map_positions",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "match_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("side", sa.String(length=3), nullable=False),
        sa.Column("place", sa.String(length=24), nullable=False),
        sa.Column(
            "count",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["match_map_id"],
            ["match_maps.id"],
            name=op.f("fk_player_map_positions_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_map_positions_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_player_map_positions_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_map_positions")),
        sa.UniqueConstraint(
            "match_map_id",
            "player_id",
            "kind",
            "side",
            "place",
            name="uq_map_player_kind_side_place",
        ),
    )
    op.create_index(
        op.f("ix_player_map_positions_kind"), "player_map_positions", ["kind"], unique=False
    )
    op.create_index(
        "ix_player_map_positions_match_map_id_kind",
        "player_map_positions",
        ["match_map_id", "kind"],
        unique=False,
    )
    op.create_index(
        "ix_player_map_positions_player_id_kind",
        "player_map_positions",
        ["player_id", "kind"],
        unique=False,
    )
    op.create_index(
        op.f("ix_player_map_positions_side"), "player_map_positions", ["side"], unique=False
    )
    op.create_table(
        "player_map_routes",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "match_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("side", sa.String(length=3), nullable=False),
        sa.Column("route_key", sa.String(length=200), nullable=False),
        sa.Column("places", sa.JSON(), nullable=False),
        sa.Column("path", sa.JSON(), nullable=False),
        sa.Column(
            "rounds",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "kills",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "deaths",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "rounds_won",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["match_map_id"],
            ["match_maps.id"],
            name=op.f("fk_player_map_routes_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_map_routes_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_player_map_routes_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_map_routes")),
        sa.UniqueConstraint(
            "match_map_id", "player_id", "side", "route_key", name="uq_map_player_route"
        ),
    )
    op.create_index(
        "ix_player_map_routes_match_map_id_side",
        "player_map_routes",
        ["match_map_id", "side"],
        unique=False,
    )
    op.create_index(
        "ix_player_map_routes_player_id_match_map_id",
        "player_map_routes",
        ["player_id", "match_map_id"],
        unique=False,
    )
    op.create_table(
        "player_map_utilities",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "match_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("side", sa.String(length=3), nullable=False),
        sa.Column(
            "smokes",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "infernos",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "fire_damage",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "he_damage",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "flash_assists",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "smoke_rounds",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "smoke_rounds_won",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["match_map_id"],
            ["match_maps.id"],
            name=op.f("fk_player_map_utilities_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_map_utilities_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_player_map_utilities_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_map_utilities")),
        sa.UniqueConstraint("match_map_id", "player_id", "side", name="uq_map_player_side_utility"),
    )
    op.create_index(
        op.f("ix_player_map_utilities_side"), "player_map_utilities", ["side"], unique=False
    )
    op.create_table(
        "player_map_weapons",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "match_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("weapon", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=3), nullable=False),
        sa.Column(
            "kills",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "headshots",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "damage",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "hits",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["match_map_id"],
            ["match_maps.id"],
            name=op.f("fk_player_map_weapons_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_map_weapons_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_player_map_weapons_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_map_weapons")),
        sa.UniqueConstraint(
            "match_map_id", "player_id", "weapon", "side", name="uq_map_player_weapon_side"
        ),
    )
    op.create_index(
        "ix_player_map_weapons_player_id_weapon",
        "player_map_weapons",
        ["player_id", "weapon"],
        unique=False,
    )
    op.create_index(
        op.f("ix_player_map_weapons_side"), "player_map_weapons", ["side"], unique=False
    )
    op.create_index(
        op.f("ix_player_map_weapons_weapon"), "player_map_weapons", ["weapon"], unique=False
    )
    op.create_table(
        "player_maps",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "match_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column(
            "rounds_played",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "kills",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "deaths",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "assists",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "headshots",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("kd_diff", sa.SmallInteger(), nullable=False),
        sa.Column(
            "damage",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("adr", sa.Double(), nullable=True),
        sa.Column("hs_pct", sa.Double(), nullable=True),
        sa.Column("kast_pct", sa.Double(), nullable=True),
        sa.Column(
            "opening_kills",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "opening_deaths",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["match_map_id"],
            ["match_maps.id"],
            name=op.f("fk_player_maps_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_maps_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_player_maps_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_maps")),
        sa.UniqueConstraint("match_map_id", "player_id", name="uq_map_playerstat"),
    )
    op.create_index(
        "ix_player_maps_player_id_match_map_id",
        "player_maps",
        ["player_id", "match_map_id"],
        unique=False,
    )
    op.create_table(
        "rounds",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "match_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "number",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "start_tick",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "freeze_end_tick",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "end_tick",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "official_end_tick",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("winner_side", sa.String(length=3), nullable=False),
        sa.Column(
            "winner_team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column(
            "ct_team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column("t_team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("end_reason", sa.String(length=24), nullable=False),
        sa.Column(
            "bomb_plant_tick",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=True,
        ),
        sa.Column("bomb_site", sa.String(length=8), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ct_team_id"],
            ["teams.id"],
            name=op.f("fk_rounds_ct_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["match_map_id"],
            ["match_maps.id"],
            name=op.f("fk_rounds_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["t_team_id"], ["teams.id"], name=op.f("fk_rounds_t_team_id_teams"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["winner_team_id"],
            ["teams.id"],
            name=op.f("fk_rounds_winner_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rounds")),
        sa.UniqueConstraint("match_map_id", "number", name="uq_map_round"),
    )
    op.create_table(
        "tick_datasets",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "match_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("tables", sa.JSON(), nullable=False),
        sa.Column("awpy_version", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["match_map_id"],
            ["match_maps.id"],
            name=op.f("fk_tick_datasets_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tick_datasets")),
        sa.UniqueConstraint("match_map_id", name=op.f("uq_tick_datasets_match_map_id")),
    )
    op.create_table(
        "bomb_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("round_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "tick", sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"), nullable=False
        ),
        sa.Column("event", sa.String(length=12), nullable=False),
        sa.Column("player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("bombsite", sa.String(length=8), nullable=False),
        sa.Column("x", sa.Double(), nullable=True),
        sa.Column("y", sa.Double(), nullable=True),
        sa.Column("z", sa.Double(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_bomb_events_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
            name=op.f("fk_bomb_events_round_id_rounds"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bomb_events")),
    )
    op.create_index(op.f("ix_bomb_events_event"), "bomb_events", ["event"], unique=False)
    op.create_index(
        "ix_bomb_events_round_id_tick", "bomb_events", ["round_id", "tick"], unique=False
    )
    op.create_table(
        "damage_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("round_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "tick", sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"), nullable=False
        ),
        sa.Column(
            "attacker_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column(
            "victim_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("attacker_side", sa.String(length=3), nullable=False),
        sa.Column("victim_side", sa.String(length=3), nullable=False),
        sa.Column("weapon", sa.String(length=32), nullable=False),
        sa.Column("hitgroup", sa.String(length=16), nullable=False),
        sa.Column(
            "damage",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "damage_raw",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "damage_armor",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("victim_health_before", sa.Integer(), nullable=True),
        sa.Column("victim_health_after", sa.Integer(), nullable=True),
        sa.Column("attacker_place", sa.String(length=24), nullable=False),
        sa.Column("victim_place", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["attacker_id"],
            ["players.id"],
            name=op.f("fk_damage_events_attacker_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
            name=op.f("fk_damage_events_round_id_rounds"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["victim_id"],
            ["players.id"],
            name=op.f("fk_damage_events_victim_id_players"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_damage_events")),
    )
    op.create_index("ix_damage_events_attacker_id", "damage_events", ["attacker_id"], unique=False)
    op.create_index(
        "ix_damage_events_round_id_tick", "damage_events", ["round_id", "tick"], unique=False
    )
    op.create_index("ix_damage_events_victim_id", "damage_events", ["victim_id"], unique=False)
    op.create_index(op.f("ix_damage_events_weapon"), "damage_events", ["weapon"], unique=False)
    op.create_table(
        "grenade_throws",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("round_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=12), nullable=False),
        sa.Column(
            "thrower_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column("thrower_side", sa.String(length=3), nullable=False),
        sa.Column(
            "throw_tick",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=True,
        ),
        sa.Column(
            "start_tick",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=True,
        ),
        sa.Column(
            "end_tick",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=True,
        ),
        sa.Column("thrower_x", sa.Double(), nullable=True),
        sa.Column("thrower_y", sa.Double(), nullable=True),
        sa.Column("thrower_z", sa.Double(), nullable=True),
        sa.Column("x", sa.Double(), nullable=True),
        sa.Column("y", sa.Double(), nullable=True),
        sa.Column("z", sa.Double(), nullable=True),
        sa.Column("thrower_place", sa.String(length=24), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
            name=op.f("fk_grenade_throws_round_id_rounds"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["thrower_id"],
            ["players.id"],
            name=op.f("fk_grenade_throws_thrower_id_players"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grenade_throws")),
        sa.UniqueConstraint("round_id", "entity_id", "type", name="uq_round_grenade"),
    )
    op.create_index(
        "ix_grenade_throws_round_id_type", "grenade_throws", ["round_id", "type"], unique=False
    )
    op.create_index("ix_grenade_throws_thrower_id", "grenade_throws", ["thrower_id"], unique=False)
    op.create_index(op.f("ix_grenade_throws_type"), "grenade_throws", ["type"], unique=False)
    op.create_table(
        "kill_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("round_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "tick", sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"), nullable=False
        ),
        sa.Column(
            "attacker_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column(
            "victim_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "assister_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column("attacker_side", sa.String(length=3), nullable=False),
        sa.Column("victim_side", sa.String(length=3), nullable=False),
        sa.Column("weapon", sa.String(length=32), nullable=False),
        sa.Column("hitgroup", sa.String(length=16), nullable=False),
        sa.Column("headshot", sa.Boolean(), nullable=False),
        sa.Column("distance", sa.Double(), nullable=True),
        sa.Column("dmg_health", sa.Integer(), nullable=False),
        sa.Column("dmg_armor", sa.Integer(), nullable=False),
        sa.Column("penetrated", sa.Integer(), nullable=False),
        sa.Column("thrusmoke", sa.Boolean(), nullable=False),
        sa.Column("noscope", sa.Boolean(), nullable=False),
        sa.Column("attackerblind", sa.Boolean(), nullable=False),
        sa.Column("attackerinair", sa.Boolean(), nullable=False),
        sa.Column("assistedflash", sa.Boolean(), nullable=False),
        sa.Column("attacker_x", sa.Double(), nullable=True),
        sa.Column("attacker_y", sa.Double(), nullable=True),
        sa.Column("attacker_z", sa.Double(), nullable=True),
        sa.Column("victim_x", sa.Double(), nullable=True),
        sa.Column("victim_y", sa.Double(), nullable=True),
        sa.Column("victim_z", sa.Double(), nullable=True),
        sa.Column("attacker_place", sa.String(length=24), nullable=False),
        sa.Column("victim_place", sa.String(length=24), nullable=False),
        sa.Column("attacker_health", sa.Double(), nullable=True),
        sa.Column("victim_health", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["assister_id"],
            ["players.id"],
            name=op.f("fk_kill_events_assister_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["attacker_id"],
            ["players.id"],
            name=op.f("fk_kill_events_attacker_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
            name=op.f("fk_kill_events_round_id_rounds"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["victim_id"],
            ["players.id"],
            name=op.f("fk_kill_events_victim_id_players"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kill_events")),
    )
    op.create_index("ix_kill_events_attacker_id", "kill_events", ["attacker_id"], unique=False)
    op.create_index(
        "ix_kill_events_round_id_tick", "kill_events", ["round_id", "tick"], unique=False
    )
    op.create_index("ix_kill_events_victim_id", "kill_events", ["victim_id"], unique=False)
    op.create_index(op.f("ix_kill_events_weapon"), "kill_events", ["weapon"], unique=False)
    op.create_table(
        "player_rounds",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("round_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("side", sa.String(length=3), nullable=False),
        sa.Column(
            "kills",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "deaths",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "assists",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "damage",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("survived", sa.Boolean(), nullable=False),
        sa.Column("traded", sa.Boolean(), nullable=False),
        sa.Column("opening_kill", sa.Boolean(), nullable=False),
        sa.Column("opening_death", sa.Boolean(), nullable=False),
        sa.Column("kast", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_player_rounds_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
            name=op.f("fk_player_rounds_round_id_rounds"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_player_rounds_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_player_rounds")),
        sa.UniqueConstraint("round_id", "player_id", name="uq_round_player"),
    )
    op.create_index(
        "ix_player_rounds_player_id_round_id",
        "player_rounds",
        ["player_id", "round_id"],
        unique=False,
    )
    op.create_index(
        "ix_player_rounds_player_id_side", "player_rounds", ["player_id", "side"], unique=False
    )


def downgrade() -> None:
    # drop_table removes a table's indexes; dropping them first fails on MySQL for FK indexes.
    op.drop_table("player_rounds")
    op.drop_table("kill_events")
    op.drop_table("grenade_throws")
    op.drop_table("damage_events")
    op.drop_table("bomb_events")
    op.drop_table("tick_datasets")
    op.drop_table("rounds")
    op.drop_table("player_maps")
    op.drop_table("player_map_weapons")
    op.drop_table("player_map_utilities")
    op.drop_table("player_map_routes")
    op.drop_table("player_map_positions")
    op.drop_table("player_map_duels")
    op.drop_table("map_rosters")
    op.drop_table("match_maps")
    op.drop_table("player_matches")
    op.drop_table("team_aliases")
    op.drop_table("player_aliases")
    op.drop_table("players")
    op.drop_table("game_maps")
