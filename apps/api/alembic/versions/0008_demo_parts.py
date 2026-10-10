"""demo parts

A Match Map whose server was restarted mid-play comes as Demo parts
(``…-m2-inferno-p1.dem``, ``…-p2.dem``), merged into one Match Map
(docs/adr/0009). ``demos.part`` tells them apart, so the unique key moves from
``(match, map)`` to ``(match, map, part)``.

Rows written before this kept a file's whole stem as its map, with no map
number. They are read again from the filename here; the parts among them were
parsed as unrelated maps, so they are left unprocessed for the next Scout that
covers their Match to download and merge.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-10

"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# app.services.archive's names as of this revision, copied so the migration
# never changes under a later edit.
_DEM_NAME = re.compile(r"-m(\d+)-([A-Za-z0-9_]+?)(?:-p(\d+))?\.dem$", re.IGNORECASE)
_BO1_NAME = re.compile(r"-([A-Za-z0-9_]+?)(?:-p(\d+))?\.dem$", re.IGNORECASE)


def _map(value: str) -> str:
    value = value.strip().lower()
    return (value[3:] if value.startswith("de_") else value)[:40]


def _read_name(filename: str) -> tuple[str, int | None, int] | None:
    match = _DEM_NAME.search(filename)
    if match:
        return _map(match.group(2)), int(match.group(1)), int(match.group(3) or 0)
    match = _BO1_NAME.search(filename)
    if match:
        return _map(match.group(1)), None, int(match.group(2) or 0)
    return None


def upgrade() -> None:
    small = sa.SmallInteger().with_variant(mysql.SMALLINT(unsigned=True), "mysql")
    op.add_column("demos", sa.Column("part", small, server_default="0", nullable=False))
    # The new key first: on MySQL the old one is the index the match_id foreign
    # key uses, and it can't be dropped while nothing else serves it.
    op.create_unique_constraint("uq_demos_match_map_part", "demos", ["match_id", "map", "part"])
    op.drop_constraint("uq_demos_match_map", "demos", type_="unique")

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, match_id, map, map_number, filename FROM demos "
            "WHERE map <> '' AND filename <> '' AND (map_number IS NULL OR map LIKE '%-%')"
        )
    ).all()
    for id_, match_id, old_map, map_number, filename in rows:
        read = _read_name(filename)
        if read is None:
            continue
        new_map, number, part = read
        taken = conn.execute(
            sa.text(
                "SELECT 1 FROM demos WHERE match_id = :m AND map = :map AND part = :part "
                "AND id <> :id"
            ),
            {"m": match_id, "map": new_map, "part": part, "id": id_},
        ).first()
        changes = new_map != old_map or part or (map_number is None and number is not None)
        if taken or not changes:
            continue
        conn.execute(
            sa.text(
                "UPDATE demos SET map = :map, map_number = COALESCE(map_number, :number), "
                "part = :part, is_processed = CASE WHEN :part > 0 THEN 0 ELSE is_processed END "
                "WHERE id = :id"
            ),
            {"map": new_map, "number": number, "part": part, "id": id_},
        )


def downgrade() -> None:
    # Part 1 holds each merged Match Map; the later parts' rows go.
    op.execute("DELETE FROM demos WHERE part > 1")
    op.create_unique_constraint("uq_demos_match_map", "demos", ["match_id", "map"])
    op.drop_constraint("uq_demos_match_map_part", "demos", type_="unique")
    op.drop_column("demos", "part")
