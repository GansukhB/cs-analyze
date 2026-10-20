"""development goals

One Player's KPI goal over a block of weeks, its progress read from his Match
Maps and Scrims (app/models/development.py; docs/plans/07 RV-9).

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "development_goals",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "workspace_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("kpi", sa.String(length=32), nullable=False),
        sa.Column("baseline", sa.Double(), nullable=True),
        sa.Column("target", sa.Double(), nullable=False),
        sa.Column("start_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
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
            name=op.f("fk_development_goals_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_development_goals_player_id_players"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_development_goals_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_development_goals")),
    )
    op.create_index(
        op.f("ix_development_goals_player_id"), "development_goals", ["player_id"], unique=False
    )
    op.create_index(
        op.f("ix_development_goals_workspace_id"),
        "development_goals",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    # MySQL refuses to drop an index a foreign key uses: drop the table only.
    op.drop_table("development_goals")
