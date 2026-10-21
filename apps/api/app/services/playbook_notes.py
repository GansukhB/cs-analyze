"""Staff's notes on a Playbook's habit lines (docs/plans/06 GP-13).

A habit line is found again on every parse with new numbers, so a note hangs on
its :func:`habit_key`: the habit as found (its spec, GP-8) without the numbers
that move with the data (counts, shares, seconds), but with the ids it is about.
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlaybookNote, User

KEPT_NUMBERS = ("_id", "round", "number")


def _stable(value, key: str = ""):
    if isinstance(value, dict):
        return {k: _stable(v, k) for k, v in sorted(value.items()) if not _moves(k, v)}
    if isinstance(value, list):
        return [_stable(v) for v in value if not _moves("", v)]
    return value


def _moves(key: str, value) -> bool:
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    return numeric and not key.endswith(KEPT_NUMBERS)


def habit_key(spec: dict | None) -> str:
    """The same for a habit found again with other numbers; 16 hex characters."""
    if not spec:
        return ""
    text = json.dumps(_stable(spec), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(text.encode(), usedforsecurity=False).hexdigest()[:16]


def notes(db: Session, workspace_id: int, team_id: int, map_name: str) -> dict[str, dict]:
    """``{habit key: {"text", "by", "at"}}`` for one Team's Playbook on one Map."""
    rows = db.execute(
        select(PlaybookNote, User.username)
        .outerjoin(User, User.id == PlaybookNote.created_by_id)
        .where(
            PlaybookNote.workspace_id == workspace_id,
            PlaybookNote.team_id == team_id,
            PlaybookNote.map_name == map_name,
        )
    ).all()
    return {n.key: {"text": n.text, "by": name or "", "at": n.updated_at} for n, name in rows}


def put(db: Session, user: User, team_id: int, map_name: str, key: str, text: str) -> None:
    """Write, change or (with no text) remove a note."""
    row = db.scalar(
        select(PlaybookNote).where(
            PlaybookNote.workspace_id == user.workspace_id,
            PlaybookNote.team_id == team_id,
            PlaybookNote.map_name == map_name,
            PlaybookNote.key == key,
        )
    )
    text = text.strip()
    if not text:
        if row is not None:
            db.delete(row)
        return
    if row is None:
        row = PlaybookNote(workspace_id=user.workspace_id, team_id=team_id, map_name=map_name,
                           key=key)  # fmt: skip
        db.add(row)
    row.text = text
    row.created_by_id = user.id
