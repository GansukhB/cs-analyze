"""note drawings

A Note keeps what Staff drew on the Replay with it (docs/plans/09 VIZ-8).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("review_notes", sa.Column("drawing", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("review_notes", "drawing")
