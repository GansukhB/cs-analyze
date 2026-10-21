"""strat board

A Strat keeps the board drawn on the radar (docs/plans/08 SB-8).

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("strats", sa.Column("board", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("strats", "board")
