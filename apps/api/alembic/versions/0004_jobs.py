"""jobs

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=True),
        sa.Column("demo_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("my_team_name", sa.String(length=120), nullable=False),
        sa.Column("opponent_name", sa.String(length=120), nullable=False),
        sa.Column(
            "my_team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column(
            "opponent_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column(
            "n_my_matches",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "n_opponent_matches",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column(
            "n_h2h_matches",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("download", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("stage", sa.String(length=12), nullable=False),
        sa.Column(
            "progress",
            sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql"),
            nullable=False,
        ),
        sa.Column("celery_task_id", sa.String(length=64), nullable=False),
        sa.Column(
            "started_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=True
        ),
        sa.Column(
            "finished_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=True
        ),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("activity", sa.JSON(), nullable=False),
        sa.Column("stage_log", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["demo_id"],
            ["demos.id"],
            name=op.f("fk_analysis_jobs_demo_id_demos"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["my_team_id"],
            ["teams.id"],
            name=op.f("fk_analysis_jobs_my_team_id_teams"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["opponent_id"],
            ["teams.id"],
            name=op.f("fk_analysis_jobs_opponent_id_teams"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"],
            ["users.id"],
            name=op.f("fk_analysis_jobs_requested_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_jobs")),
        sa.UniqueConstraint("public_id", name=op.f("uq_analysis_jobs_public_id")),
    )
    op.create_index(
        op.f("ix_analysis_jobs_celery_task_id"), "analysis_jobs", ["celery_task_id"], unique=False
    )
    op.create_index(op.f("ix_analysis_jobs_kind"), "analysis_jobs", ["kind"], unique=False)
    op.create_index(op.f("ix_analysis_jobs_status"), "analysis_jobs", ["status"], unique=False)
    op.create_index(
        "ix_analysis_jobs_status_created_at",
        "analysis_jobs",
        ["status", "created_at"],
        unique=False,
    )
    op.create_table(
        "analysis_artifacts",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("job_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("subtitle", sa.String(length=200), nullable=False),
        sa.Column("map_name", sa.String(length=32), nullable=False),
        sa.Column("player_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("side", sa.String(length=3), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("renderer", sa.String(length=16), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["analysis_jobs.id"],
            name=op.f("fk_analysis_artifacts_job_id_analysis_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.id"],
            name=op.f("fk_analysis_artifacts_player_id_players"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_analysis_artifacts_team_id_teams"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_artifacts")),
    )
    op.create_table(
        "analysis_events",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("job_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("stage", sa.String(length=12), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["analysis_jobs.id"],
            name=op.f("fk_analysis_events_job_id_analysis_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_events")),
    )
    op.create_index(
        "ix_analysis_events_job_id_id", "analysis_events", ["job_id", "id"], unique=False
    )
    op.create_table(
        "analysis_job_matches",
        sa.Column(
            "analysis_job_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("match_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_job_id"],
            ["analysis_jobs.id"],
            name=op.f("fk_analysis_job_matches_analysis_job_id_analysis_jobs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_analysis_job_matches_match_id_matches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "analysis_job_id", "match_id", name=op.f("pk_analysis_job_matches")
        ),
    )


def downgrade() -> None:
    # drop_table removes a table's indexes; dropping them first fails on MySQL for FK indexes.
    op.drop_table("analysis_job_matches")
    op.drop_table("analysis_events")
    op.drop_table("analysis_artifacts")
    op.drop_table("analysis_jobs")
