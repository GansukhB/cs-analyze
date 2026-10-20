"""parse events

Schema 14 (docs/plans/02 DATA-5): each round's timeouts, the scoreboard's
per-round numbers, and the moment, spot and aim each grenade was thrown with.
None where the Tick Data predates them.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "grenade_throws",
        sa.Column(
            "thrown_tick",
            sa.Integer().with_variant(mysql.INTEGER(unsigned=True), "mysql"),
            nullable=True,
        ),
    )
    op.add_column("grenade_throws", sa.Column("thrown_x", sa.Double(), nullable=True))
    op.add_column("grenade_throws", sa.Column("thrown_y", sa.Double(), nullable=True))
    op.add_column("grenade_throws", sa.Column("thrown_z", sa.Double(), nullable=True))
    op.add_column("grenade_throws", sa.Column("thrown_pitch", sa.Double(), nullable=True))
    op.add_column("grenade_throws", sa.Column("thrown_yaw", sa.Double(), nullable=True))
    op.add_column(
        "grenade_throws",
        sa.Column("thrown_place", sa.String(length=24), nullable=False, server_default=""),
    )
    op.add_column(
        "player_rounds",
        sa.Column(
            "enemies_flashed",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=True,
        ),
    )
    op.add_column(
        "player_rounds",
        sa.Column(
            "utility_damage",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=True,
        ),
    )
    op.add_column(
        "player_rounds",
        sa.Column(
            "money_saved",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=True,
        ),
    )
    op.add_column(
        "player_rounds",
        sa.Column(
            "kill_reward",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=True,
        ),
    )
    op.add_column("rounds", sa.Column("ct_timeout", sa.Boolean(), nullable=True))
    op.add_column("rounds", sa.Column("t_timeout", sa.Boolean(), nullable=True))
    op.add_column("rounds", sa.Column("tech_timeout", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("rounds", "tech_timeout")
    op.drop_column("rounds", "t_timeout")
    op.drop_column("rounds", "ct_timeout")
    op.drop_column("player_rounds", "kill_reward")
    op.drop_column("player_rounds", "money_saved")
    op.drop_column("player_rounds", "utility_damage")
    op.drop_column("player_rounds", "enemies_flashed")
    op.drop_column("grenade_throws", "thrown_place")
    op.drop_column("grenade_throws", "thrown_yaw")
    op.drop_column("grenade_throws", "thrown_pitch")
    op.drop_column("grenade_throws", "thrown_z")
    op.drop_column("grenade_throws", "thrown_y")
    op.drop_column("grenade_throws", "thrown_x")
    op.drop_column("grenade_throws", "thrown_tick")
