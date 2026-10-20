"""workspaces

A Workspace (CONTEXT.md, docs/adr/0011) owns a club's Users and the Teams it
calls my team, and later everything else it keeps to itself. Every User so far
becomes Staff of one Workspace, named after the Team most Scouts were run for,
which also becomes its my team.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-21

"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BigId = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
DateTime6 = sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql")


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", BigId, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", DateTime6, nullable=False),
        sa.Column("updated_at", DateTime6, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
        sa.UniqueConstraint("public_id", name=op.f("uq_workspaces_public_id")),
        sa.UniqueConstraint("name", name=op.f("uq_workspaces_name")),
    )
    op.create_table(
        "workspace_teams",
        sa.Column("id", BigId, nullable=False),
        sa.Column("workspace_id", BigId, nullable=False),
        sa.Column("team_id", BigId, nullable=False),
        sa.Column("label", sa.String(length=40), nullable=False),
        sa.Column("created_at", DateTime6, nullable=False),
        sa.Column("updated_at", DateTime6, nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_workspace_teams_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_workspace_teams_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_teams")),
        sa.UniqueConstraint("workspace_id", "team_id", name="uq_ws_team"),
    )
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("workspace_id", BigId, nullable=True))
        batch.add_column(
            sa.Column("role", sa.String(length=12), nullable=False, server_default="staff")
        )
        batch.add_column(sa.Column("player_id", BigId, nullable=True))
        batch.add_column(sa.Column("last_login_at", DateTime6, nullable=True))

    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM users")).scalar():
        now = datetime.now(UTC).replace(tzinfo=None)
        team = bind.execute(
            sa.text(
                "SELECT t.id, t.name FROM analysis_jobs j JOIN teams t ON t.id = j.my_team_id "
                "GROUP BY t.id, t.name ORDER BY COUNT(*) DESC, t.id LIMIT 1"
            )
        ).first()
        bind.execute(
            sa.text(
                "INSERT INTO workspaces (public_id, name, created_at, updated_at) "
                "VALUES (:public_id, :name, :now, :now)"
            ),
            {"public_id": uuid.uuid4().hex, "name": team.name if team else "Workspace", "now": now},
        )
        workspace_id = bind.execute(sa.text("SELECT MAX(id) FROM workspaces")).scalar()
        bind.execute(sa.text("UPDATE users SET workspace_id = :w"), {"w": workspace_id})
        if team:
            bind.execute(
                sa.text(
                    "INSERT INTO workspace_teams (workspace_id, team_id, label, created_at, "
                    "updated_at) VALUES (:w, :t, 'main', :now, :now)"
                ),
                {"w": workspace_id, "t": team.id, "now": now},
            )

    with op.batch_alter_table("users") as batch:
        batch.alter_column("workspace_id", existing_type=BigId, nullable=False)
        batch.create_index(op.f("ix_users_workspace_id"), ["workspace_id"], unique=False)
        batch.create_foreign_key(
            op.f("fk_users_workspace_id_workspaces"),
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            op.f("fk_users_player_id_players"),
            "players",
            ["player_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint(op.f("fk_users_player_id_players"), type_="foreignkey")
        batch.drop_constraint(op.f("fk_users_workspace_id_workspaces"), type_="foreignkey")
        batch.drop_index(op.f("ix_users_workspace_id"))
        batch.drop_column("last_login_at")
        batch.drop_column("player_id")
        batch.drop_column("role")
        batch.drop_column("workspace_id")
    op.drop_table("workspace_teams")
    op.drop_table("workspaces")
