"""tick data in mysql

A Match Map's Tick Data moves from a parquet file on disk into
``tick_datasets.bundle``, with the Replay rounds, walked routes and callout
geometry cut from it stored beside it. See docs/adr/0002-tick-data-in-mysql.md.

The existing ``tick_datasets`` rows only pointed at files, so they are deleted
here; ``npm run data:import`` reads the files back in.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BigId = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
LongBlob = sa.LargeBinary().with_variant(mysql.LONGBLOB(), "mysql")
MediumBlob = sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql")


def upgrade() -> None:
    op.create_table(
        "replay_rounds",
        sa.Column("id", BigId, nullable=False),
        sa.Column("match_map_id", BigId, nullable=False),
        sa.Column(
            "number",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("payload", MediumBlob, nullable=False),
        sa.ForeignKeyConstraint(
            ["match_map_id"],
            ["match_maps.id"],
            name=op.f("fk_replay_rounds_match_map_id_match_maps"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_replay_rounds")),
        sa.UniqueConstraint("match_map_id", "number", name="uq_replay_round"),
    )
    op.execute("DELETE FROM tick_datasets")
    op.drop_column("tick_datasets", "path")
    op.add_column("tick_datasets", sa.Column("bundle", LongBlob, nullable=False))
    op.add_column("tick_datasets", sa.Column("geometry", sa.JSON(), nullable=False))
    op.add_column("tick_datasets", sa.Column("walks", MediumBlob, nullable=True))
    op.add_column("tick_datasets", sa.Column("replay", sa.JSON(), nullable=False))
    op.add_column(
        "tick_datasets", sa.Column("derived_version", sa.String(length=16), nullable=False)
    )
    op.drop_column("match_maps", "parquet_path")


def downgrade() -> None:
    op.add_column(
        "match_maps",
        sa.Column("parquet_path", sa.String(length=500), nullable=False, server_default=""),
    )
    op.execute("DELETE FROM tick_datasets")
    op.drop_column("tick_datasets", "derived_version")
    op.drop_column("tick_datasets", "replay")
    op.drop_column("tick_datasets", "walks")
    op.drop_column("tick_datasets", "geometry")
    op.drop_column("tick_datasets", "bundle")
    op.add_column(
        "tick_datasets",
        sa.Column("path", sa.String(length=500), nullable=False, server_default=""),
    )
    op.drop_table("replay_rounds")
