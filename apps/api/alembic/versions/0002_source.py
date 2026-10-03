"""source

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "hltv_id",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column(
            "unidentified_name",
            sa.String(length=120),
            sa.Computed("CASE WHEN hltv_id IS NULL THEN name END", persisted=True),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("hltv_id", name=op.f("uq_teams_hltv_id")),
        sa.UniqueConstraint("unidentified_name", name=op.f("uq_teams_unidentified_name")),
    )
    op.create_index(op.f("ix_teams_name"), "teams", ["name"], unique=False)
    op.create_index(op.f("ix_teams_slug"), "teams", ["slug"], unique=False)
    op.create_table(
        "tournaments",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "hltv_id",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tournaments")),
        sa.UniqueConstraint("hltv_id", name=op.f("uq_tournaments_hltv_id")),
        sa.UniqueConstraint("name", name=op.f("uq_tournaments_name")),
    )
    op.create_index(op.f("ix_tournaments_slug"), "tournaments", ["slug"], unique=False)
    op.create_table(
        "matches",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "hltv_id",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=200), nullable=False),
        sa.Column("team1_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("team2_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column(
            "tournament_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column("score", sa.String(length=40), nullable=False),
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
        sa.Column(
            "played_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=True
        ),
        sa.Column("demo_url", sa.String(length=200), nullable=False),
        sa.Column(
            "demo_checked_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["team1_id"], ["teams.id"], name=op.f("fk_matches_team1_id_teams"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["team2_id"], ["teams.id"], name=op.f("fk_matches_team2_id_teams"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tournament_id"],
            ["tournaments.id"],
            name=op.f("fk_matches_tournament_id_tournaments"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_matches")),
        sa.UniqueConstraint("hltv_id", name=op.f("uq_matches_hltv_id")),
    )
    op.create_index(op.f("ix_matches_played_at"), "matches", ["played_at"], unique=False)
    op.create_index(op.f("ix_matches_slug"), "matches", ["slug"], unique=False)
    op.create_table(
        "demos",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("match_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("map", sa.String(length=40), nullable=False),
        sa.Column(
            "map_number",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=True,
        ),
        sa.Column("url", sa.String(length=200), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("is_downloaded", sa.Boolean(), nullable=False),
        sa.Column(
            "downloaded_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"),
            nullable=True,
        ),
        sa.Column("is_processed", sa.Boolean(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.CheckConstraint(
            "NOT is_processed OR is_downloaded", name=op.f("ck_demos_processed_requires_download")
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["matches.id"], name=op.f("fk_demos_match_id_matches"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_demos")),
        sa.UniqueConstraint("match_id", "map", name="uq_demos_match_map"),
    )


def downgrade() -> None:
    # drop_table removes a table's indexes; dropping them first fails on MySQL for FK indexes.
    op.drop_table("demos")
    op.drop_table("matches")
    op.drop_table("tournaments")
    op.drop_table("teams")
