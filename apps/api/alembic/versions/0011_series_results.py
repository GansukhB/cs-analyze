"""series results

Results known without their Demos, what Ratings are fitted on: every series
Valve Regional Standings counted (``series_results``) and each roster's line in
each monthly snapshot (``vrs_standings``). See app/models/results.py and
docs/plans/02-data-sources.md DATA-2.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "series_results",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("key", sa.String(length=190), nullable=False),
        sa.Column("played_on", sa.Date(), nullable=False),
        sa.Column("team_a", sa.String(length=120), nullable=False),
        sa.Column("team_b", sa.String(length=120), nullable=False),
        sa.Column("team_a_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("team_b_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("a_won", sa.Boolean(), nullable=False),
        sa.Column("lan", sa.Boolean(), nullable=True),
        sa.Column("roster_a", sa.JSON(), nullable=False),
        sa.Column("roster_b", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["team_a_id"],
            ["teams.id"],
            name=op.f("fk_series_results_team_a_id_teams"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["team_b_id"],
            ["teams.id"],
            name=op.f("fk_series_results_team_b_id_teams"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_series_results")),
        sa.UniqueConstraint("source", "key", name="uq_series_source_key"),
    )
    op.create_index(
        op.f("ix_series_results_played_on"), "series_results", ["played_on"], unique=False
    )
    op.create_index(
        op.f("ix_series_results_team_a_id"), "series_results", ["team_a_id"], unique=False
    )
    op.create_index(
        op.f("ix_series_results_team_b_id"), "series_results", ["team_b_id"], unique=False
    )
    op.create_table(
        "vrs_standings",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("snapshot", sa.Date(), nullable=False),
        sa.Column("global_rank", sa.Integer(), nullable=False),
        sa.Column("region", sa.String(length=24), nullable=False),
        sa.Column("regional_rank", sa.Integer(), nullable=True),
        sa.Column("points", sa.Double(), nullable=False),
        sa.Column("team_name", sa.String(length=120), nullable=False),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("roster", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_vrs_standings_team_id_teams"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vrs_standings")),
        sa.UniqueConstraint("snapshot", "global_rank", name="uq_vrs_snapshot_rank"),
    )
    op.create_index(op.f("ix_vrs_standings_snapshot"), "vrs_standings", ["snapshot"], unique=False)
    op.create_index(op.f("ix_vrs_standings_team_id"), "vrs_standings", ["team_id"], unique=False)
    op.create_index(
        op.f("ix_vrs_standings_team_name"), "vrs_standings", ["team_name"], unique=False
    )


def downgrade() -> None:
    # MySQL refuses to drop an index a foreign key uses: drop the tables only.
    op.drop_table("vrs_standings")
    op.drop_table("series_results")
