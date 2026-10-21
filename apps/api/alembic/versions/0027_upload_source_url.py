"""upload source url

An upload can name a link the worker fetches the Demo from (docs/plans/02 DATA-1).

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "uploads",
        sa.Column("source_url", sa.String(length=1000), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("uploads", "source_url")
