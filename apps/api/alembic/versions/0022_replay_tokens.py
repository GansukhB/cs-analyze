"""replay tokens

Each stored Replay Round keeps, second by second, how many of each Side stood
in each Callout, for the Round search (docs/plans/09 VIZ-7).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "replay_rounds",
        sa.Column(
            "tokens", sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql"), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("replay_rounds", "tokens")
