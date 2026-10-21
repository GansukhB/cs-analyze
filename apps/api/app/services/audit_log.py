"""Writing and reading a Workspace's audit log (docs/plans/01 WS-7).

:func:`record` adds a line in the caller's transaction (its commit keeps it,
its rollback drops it). Lines say what was done to what, never a secret: an
invite's token, a password or a key never goes in ``detail``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, User

LIMIT = 200


def record(
    db: Session, actor: User | None, action: str, subject: str = "", *,
    workspace_id: int | None = None, **detail,
) -> AuditEvent:  # fmt: skip
    """One line: ``actor`` (None for the server CLI) did ``action`` to ``subject``."""
    row = AuditEvent(
        workspace_id=workspace_id
        if workspace_id is not None
        else getattr(actor, "workspace_id", None),
        actor_id=actor.id if actor is not None else None,
        action=action,
        subject=subject[:160],
        detail=detail,
    )
    db.add(row)
    return row


def recent(db: Session, workspace_id: int, limit: int = LIMIT) -> list[dict]:
    """The Workspace's latest lines, newest first, with who did them."""
    rows = db.execute(
        select(AuditEvent, User.username)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(AuditEvent.workspace_id == workspace_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": e.id,
            "at": e.created_at,
            "actor": name or ("server" if e.actor_id is None else "?"),
            "action": e.action,
            "subject": e.subject,
            "detail": e.detail or {},
        }
        for e, name in rows
    ]
