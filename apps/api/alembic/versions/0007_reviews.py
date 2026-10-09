"""match map reviews

Schema 13's Review (CONTEXT.md): one gzip JSON row per Match Map, cut from its
Tick Data and rebuilt when ``review.version()`` moves. See
app/services/review.py and docs/adr/0006-tick-data-without-sightings-is-still-reviewed.md.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "match_map_reviews",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "match_map_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("version", sa.String(length=48), nullable=False),
        sa.Column("sightings", sa.Boolean(), nullable=False),
        sa.Column(
            "payload", sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql"), nullable=False
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
            name=op.f("fk_match_map_reviews_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_map_reviews")),
        sa.UniqueConstraint("match_map_id", name=op.f("uq_match_map_reviews_match_map_id")),
    )


def downgrade() -> None:
    op.drop_table("match_map_reviews")
