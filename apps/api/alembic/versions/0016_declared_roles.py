"""declared roles

The role Staff say one of their Players plays on a Side, optionally per Map
(app/models/workspace.py DeclaredRole; docs/plans/04 PL-4).

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "declared_roles",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "workspace_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("side", sa.String(length=2), nullable=False),
        sa.Column("map", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_declared_roles_player_id_players"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_declared_roles_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_declared_roles")),
        sa.UniqueConstraint("workspace_id", "player_id", "side", "map", name="uq_declared_role"),
    )
    op.create_index(
        op.f("ix_declared_roles_workspace_id"), "declared_roles", ["workspace_id"], unique=False
    )


def downgrade() -> None:
    # MySQL refuses to drop an index a foreign key uses: drop the table only.
    op.drop_table("declared_roles")
