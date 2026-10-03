"""economy and snapshots

Schema 11, what the Playbook reads. Each side's equipment value and Buy type on
``rounds``, and what every player carried as the round went live on
``player_rounds``; where every living player stood at each round's Setup and
plant (``round_snapshots``); the Callout each grenade landed in. Rows parsed
before stay null and '' until their match is downloaded again; see
docs/adr/0003-tick-data-without-economy-means-download-again.md.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BigId = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
DateTime6 = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")
SmallUnsigned = sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql")
IntUnsigned = sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql")


def upgrade() -> None:
    op.add_column("player_rounds", sa.Column("money", SmallUnsigned, nullable=True))
    op.add_column("player_rounds", sa.Column("equip_value", SmallUnsigned, nullable=True))
    op.add_column("player_rounds", sa.Column("armor", SmallUnsigned, nullable=True))
    op.add_column("player_rounds", sa.Column("helmet", sa.Boolean(), nullable=True))
    op.add_column("player_rounds", sa.Column("defuser", sa.Boolean(), nullable=True))
    op.add_column(
        "player_rounds",
        sa.Column("primary_weapon", sa.String(length=16), nullable=False, server_default=""),
    )
    op.add_column("rounds", sa.Column("ct_equip_value", IntUnsigned, nullable=True))
    op.add_column("rounds", sa.Column("t_equip_value", IntUnsigned, nullable=True))
    op.add_column(
        "rounds", sa.Column("ct_buy", sa.String(length=8), nullable=False, server_default="")
    )
    op.add_column(
        "rounds", sa.Column("t_buy", sa.String(length=8), nullable=False, server_default="")
    )
    op.add_column(
        "grenade_throws",
        sa.Column("place", sa.String(length=24), nullable=False, server_default=""),
    )
    op.create_table(
        "round_snapshots",
        sa.Column("id", BigId, nullable=False),
        sa.Column("round_id", BigId, nullable=False),
        sa.Column("player_id", BigId, nullable=False),
        sa.Column("moment", sa.String(length=8), nullable=False),
        sa.Column("side", sa.String(length=3), nullable=False),
        sa.Column("place", sa.String(length=24), nullable=False),
        sa.Column("x", sa.Double(), nullable=True),
        sa.Column("y", sa.Double(), nullable=True),
        sa.Column("z", sa.Double(), nullable=True),
        sa.Column("created_at", DateTime6, nullable=False),
        sa.Column("updated_at", DateTime6, nullable=False),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_round_snapshots_player_id_players"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["rounds.id"],
            name=op.f("fk_round_snapshots_round_id_rounds"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_round_snapshots")),
        sa.UniqueConstraint("round_id", "player_id", "moment", name="uq_round_snapshot"),
    )


def downgrade() -> None:
    op.drop_table("round_snapshots")
    op.drop_column("grenade_throws", "place")
    op.drop_column("rounds", "t_buy")
    op.drop_column("rounds", "ct_buy")
    op.drop_column("rounds", "t_equip_value")
    op.drop_column("rounds", "ct_equip_value")
    op.drop_column("player_rounds", "primary_weapon")
    op.drop_column("player_rounds", "defuser")
    op.drop_column("player_rounds", "helmet")
    op.drop_column("player_rounds", "armor")
    op.drop_column("player_rounds", "equip_value")
    op.drop_column("player_rounds", "money")
