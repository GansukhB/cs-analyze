"""stored answer digest

The sha1 of a stored answer's JSON, so recomputing an answer that came out the
same rewrites its stamp alone, not its payload (docs/adr/0015).

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("stored_answers", sa.Column("digest", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("stored_answers", "digest")
