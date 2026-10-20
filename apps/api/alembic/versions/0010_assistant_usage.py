"""assistant usage

One row per Assistant chat turn: tokens, speech characters and the cost at the
list prices, for the per-User daily cap and the monthly bill (docs/plans AS-2).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BigId = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
DateTime6 = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    op.create_table(
        "assistant_usage",
        sa.Column("id", BigId, nullable=False),
        sa.Column("created_at", DateTime6, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", BigId, nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("tool_rounds", sa.Integer(), nullable=False),
        sa.Column("tts_chars", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_assistant_usage_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_assistant_usage_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assistant_usage")),
    )
    op.create_index(
        op.f("ix_assistant_usage_created_at"), "assistant_usage", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_assistant_usage_user_id"), "assistant_usage", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_assistant_usage_workspace_id"), "assistant_usage", ["workspace_id"], unique=False
    )


def downgrade() -> None:
    op.drop_table("assistant_usage")
