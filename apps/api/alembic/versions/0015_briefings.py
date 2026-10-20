"""briefings

Frozen selections of a Game Plan's lines with Staff's notes, handed to the
Players (app/models/briefing.py; docs/plans/01 WS-5).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "briefings",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column(
            "workspace_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "my_team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "opponent_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("my_lineup", sa.JSON(), nullable=False),
        sa.Column("their_lineup", sa.JSON(), nullable=False),
        sa.Column("match_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column(
            "payload", sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql"), nullable=False
        ),
        sa.Column("include_forecast", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "shared_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_briefings_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_briefings_match_id_matches"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["my_team_id"],
            ["teams.id"],
            name=op.f("fk_briefings_my_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opponent_id"],
            ["teams.id"],
            name=op.f("fk_briefings_opponent_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_briefings_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_briefings")),
        sa.UniqueConstraint("public_id", name=op.f("uq_briefings_public_id")),
    )
    op.create_index(op.f("ix_briefings_workspace_id"), "briefings", ["workspace_id"], unique=False)


def downgrade() -> None:
    # MySQL refuses to drop an index a foreign key uses: drop the table only.
    op.drop_table("briefings")
