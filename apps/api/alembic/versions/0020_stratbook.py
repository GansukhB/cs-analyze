"""stratbook

Strats, their example Rounds, their versions and who read or changed them
(app/models/strat.py; docs/plans/08 SB-1, SB-7).

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strats",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "workspace_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("map_name", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("grenades", sa.JSON(), nullable=False),
        sa.Column("timings", sa.Text(), nullable=False),
        sa.Column("variations", sa.Text(), nullable=False),
        sa.Column("calls", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("visibility", sa.String(length=8), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_strats_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name=op.f("fk_strats_team_id_teams"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_strats_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strats")),
    )
    op.create_index(op.f("ix_strats_map_name"), "strats", ["map_name"], unique=False)
    op.create_index(op.f("ix_strats_workspace_id"), "strats", ["workspace_id"], unique=False)
    op.create_table(
        "strat_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("strat_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=12), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["strat_id"],
            ["strats.id"],
            name=op.f("fk_strat_events_strat_id_strats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_strat_events_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strat_events")),
    )
    op.create_index(op.f("ix_strat_events_strat_id"), "strat_events", ["strat_id"], unique=False)
    op.create_table(
        "strat_versions",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("strat_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_strat_versions_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["strat_id"],
            ["strats.id"],
            name=op.f("fk_strat_versions_strat_id_strats"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strat_versions")),
    )
    op.create_index(
        op.f("ix_strat_versions_strat_id"), "strat_versions", ["strat_id"], unique=False
    )
    op.create_table(
        "strat_examples",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("strat_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "match_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["match_map_id"],
            ["match_maps.id"],
            name=op.f("fk_strat_examples_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["strat_id"],
            ["strats.id"],
            name=op.f("fk_strat_examples_strat_id_strats"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strat_examples")),
        sa.UniqueConstraint("strat_id", "match_map_id", "round", name="uq_strat_example"),
    )
    op.create_index(
        op.f("ix_strat_examples_strat_id"), "strat_examples", ["strat_id"], unique=False
    )


def downgrade() -> None:
    # MySQL refuses to drop an index a foreign key uses: drop the tables only.
    op.drop_table("strat_events")
    op.drop_table("strat_versions")
    op.drop_table("strat_examples")
    op.drop_table("strats")
