"""forecasts

Every Forecast as made, never changed, and graded once its series is played
(app/models/forecast.py; docs/plans/03-ratings-forecast.md FC-4).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forecasts",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column(
            "workspace_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "my_team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "opponent_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("my_lineup", sa.JSON(), nullable=False),
        sa.Column("their_lineup", sa.JSON(), nullable=False),
        sa.Column("format", sa.String(length=8), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("p_series", sa.Double(), nullable=False),
        sa.Column("match_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column(
            "graded_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=True
        ),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("log_loss", sa.Double(), nullable=True),
        sa.Column("brier", sa.Double(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_forecasts_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_forecasts_match_id_matches"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["my_team_id"],
            ["teams.id"],
            name=op.f("fk_forecasts_my_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opponent_id"],
            ["teams.id"],
            name=op.f("fk_forecasts_opponent_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_forecasts_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_forecasts")),
        sa.UniqueConstraint("public_id", name=op.f("uq_forecasts_public_id")),
    )
    op.create_index(
        "ix_forecasts_ws_created", "forecasts", ["workspace_id", "created_at"], unique=False
    )


def downgrade() -> None:
    # MySQL refuses to drop an index a foreign key uses: drop the table only.
    op.drop_table("forecasts")
