"""review spots version

Each stored Review keeps the Map's Spots version apart from its own, so that
editing one Map's Spots rebuilds that Map's Reviews only (docs/plans/09 VIZ-11).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "match_map_reviews",
        sa.Column("spots_version", sa.String(length=8), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("match_map_reviews", "spots_version")
