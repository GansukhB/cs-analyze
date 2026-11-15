"""stored answers

Each analytic page's answer, kept with no expiry under the key it is asked by,
with the data stamp it was computed at (docs/adr/0014).

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATETIME6 = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    op.create_table(
        "stored_answers",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("key_hash", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=512), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("stamp", sa.String(length=200), nullable=False),
        sa.Column(
            "payload", sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql"), nullable=False
        ),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("compute_ms", sa.Integer(), nullable=False),
        sa.Column("computed_at", DATETIME6, nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("last_hit_at", DATETIME6, nullable=True),
        sa.Column("wanted_at", DATETIME6, nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stored_answers")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_stored_answers_key_hash")),
    )
    op.create_index(op.f("ix_stored_answers_kind"), "stored_answers", ["kind"], unique=False)
    op.create_index(
        op.f("ix_stored_answers_last_hit_at"), "stored_answers", ["last_hit_at"], unique=False
    )
    op.create_index(
        op.f("ix_stored_answers_wanted_at"), "stored_answers", ["wanted_at"], unique=False
    )


def downgrade() -> None:
    op.drop_table("stored_answers")
