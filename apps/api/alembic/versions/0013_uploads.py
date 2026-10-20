"""uploads

A Workspace's own Demos (docs/plans/02 DATA-1): ``matches`` gains its Workspace,
its kind (official or scrim) and source, ``hltv_id`` becomes optional for
uploaded Matches, and ``uploads``/``upload_parts`` hold a file on its way in.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uploads",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column(
            "workspace_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("played_on", sa.Date(), nullable=False),
        sa.Column(
            "my_team_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column(
            "opponent_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
        sa.Column("opponent_name", sa.String(length=120), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column(
            "size_bytes", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("parts_total", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("job_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("match_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True),
        sa.Column("maps", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_uploads_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["analysis_jobs.id"],
            name=op.f("fk_uploads_job_id_analysis_jobs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["matches.id"],
            name=op.f("fk_uploads_match_id_matches"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["my_team_id"],
            ["teams.id"],
            name=op.f("fk_uploads_my_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opponent_id"],
            ["teams.id"],
            name=op.f("fk_uploads_opponent_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_uploads_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploads")),
        sa.UniqueConstraint("public_id", name=op.f("uq_uploads_public_id")),
    )
    op.create_index(op.f("ix_uploads_workspace_id"), "uploads", ["workspace_id"], unique=False)
    op.create_table(
        "upload_parts",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column(
            "upload_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False
        ),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column(
            "data", sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), "mysql"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["uploads.id"],
            name=op.f("fk_upload_parts_upload_id_uploads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_upload_parts")),
        sa.UniqueConstraint("upload_id", "n", name="uq_upload_part"),
    )
    op.add_column(
        "matches",
        sa.Column(
            "workspace_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True
        ),
    )
    op.add_column(
        "matches",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="official"),
    )
    op.add_column(
        "matches", sa.Column("source", sa.String(length=16), nullable=False, server_default="hltv")
    )
    op.add_column(
        "matches",
        sa.Column("opponent_label", sa.String(length=120), nullable=False, server_default=""),
    )
    op.alter_column("matches", "hltv_id", existing_type=mysql.INTEGER(unsigned=True), nullable=True)
    op.create_index(op.f("ix_matches_workspace_id"), "matches", ["workspace_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_matches_workspace_id_workspaces"),
        "matches",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Uploaded Matches have no HLTV id; they go before the column is required again.
    op.execute("DELETE FROM matches WHERE hltv_id IS NULL")
    op.drop_constraint(op.f("fk_matches_workspace_id_workspaces"), "matches", type_="foreignkey")
    op.drop_index(op.f("ix_matches_workspace_id"), table_name="matches")
    op.alter_column(
        "matches", "hltv_id", existing_type=mysql.INTEGER(unsigned=True), nullable=False
    )
    op.drop_column("matches", "opponent_label")
    op.drop_column("matches", "source")
    op.drop_column("matches", "kind")
    op.drop_column("matches", "workspace_id")
    # MySQL refuses to drop an index a foreign key uses: drop the tables only.
    op.drop_table("upload_parts")
    op.drop_table("uploads")
