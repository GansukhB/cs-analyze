"""A Workspace's people (docs/plans/01 WS-3): Staff invite them by a one-time
link, tie a Player login to its Player, change roles, deactivate, and send a
reset link for a forgotten password. Only a token's SHA-256 is stored; a link
works once, for :data:`INVITE_DAYS` days. No Workspace is ever left without an
active Staff member, and nobody deactivates themself.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Invite, Player, User, UserRole
from app.models.base import utcnow
from app.security import hash_password

INVITE_DAYS = 7
MIN_PASSWORD_LENGTH = 6
USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


class MemberError(ValueError):
    """Something a person can fix; its text says what."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def invite(
    db: Session,
    by: User,
    *,
    role: str,
    player_steamid: str | None = None,
    user_id: int | None = None,
) -> tuple[Invite, str]:
    """A new link: ``(row, token)``. The token is shown once and never stored."""
    player = None
    if user_id is not None:
        target = db.get(User, user_id)
        if target is None or target.workspace_id != by.workspace_id:
            raise MemberError("Ийм гишүүн алга.")
        role = target.role
    elif role == UserRole.PLAYER:
        if not player_steamid:
            raise MemberError("Тоглогчийн урилгад Player сонгоно уу.")
        player = db.scalar(select(Player).where(Player.steamid == int(player_steamid)))
        if player is None:
            raise MemberError("Ийм тоглогч алга.")
    elif role != UserRole.STAFF:
        raise MemberError("Role нь staff эсвэл player.")
    token = secrets.token_urlsafe(24)
    row = Invite(
        workspace_id=by.workspace_id,
        token_hash=_hash(token),
        role=role,
        player_id=player.id if player else None,
        user_id=user_id,
        created_by_id=by.id,
        expires_at=utcnow() + timedelta(days=INVITE_DAYS),
    )
    db.add(row)
    db.commit()
    return row, token


def find(db: Session, token: str) -> Invite | None:
    """The invite for ``token``, if it is still usable."""
    row = db.scalar(select(Invite).where(Invite.token_hash == _hash(token)))
    if row is None or row.used_at is not None or row.expires_at < utcnow():
        return None
    return row


def accept(db: Session, token: str, username: str, password: str) -> User:
    """Use the link: make the User (or set the reset User's password)."""
    row = find(db, token)
    if row is None:
        raise MemberError("Урилга хүчингүй эсвэл хугацаа нь дууссан.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise MemberError(f"Нууц үг дор хаяж {MIN_PASSWORD_LENGTH} тэмдэгт.")
    if row.user_id is not None:
        user = db.get(User, row.user_id)
        if user is None:
            raise MemberError("Энэ гишүүн устгагдсан.")
        user.password_hash = hash_password(password)
    else:
        if not USERNAME.match(username):
            raise MemberError("Username 3–32 тэмдэгт: үсэг, тоо, _ . -")
        if db.scalar(select(User.id).where(User.username == username)) is not None:
            raise MemberError("Энэ username аль хэдийн байна.")
        user = User(
            username=username,
            password_hash=hash_password(password),
            workspace_id=row.workspace_id,
            role=row.role,
            player_id=row.player_id,
        )
        db.add(user)
        db.flush()
    row.used_at = utcnow()
    row.used_by_id = user.id
    user.last_login_at = utcnow()
    db.commit()
    return user


def _active_staff(db: Session, workspace_id: int) -> int:
    return db.scalar(
        select(func.count(User.id)).where(
            User.workspace_id == workspace_id,
            User.role == UserRole.STAFF,
            User.is_active.is_(True),
        )
    )


def change(
    db: Session,
    by: User,
    member: User,
    *,
    is_active: bool | None = None,
    role: str | None = None,
    player_steamid: str | None = None,
) -> User:
    """Deactivate or reactivate, change role, tie to a Player ("" unties)."""
    if member.workspace_id != by.workspace_id:
        raise MemberError("Ийм гишүүн алга.")
    leaves_staff = (is_active is False and member.is_active) or (
        role == UserRole.PLAYER and member.role == UserRole.STAFF
    )
    if leaves_staff and member.id == by.id:
        raise MemberError("Өөрийгөө идэвхгүй болгох эсвэл Staff-аас гаргах боломжгүй.")
    if leaves_staff and member.role == UserRole.STAFF and _active_staff(db, by.workspace_id) <= 1:
        raise MemberError("Workspace-д дор хаяж нэг идэвхтэй Staff үлдэх ёстой.")
    if role is not None:
        if role not in (UserRole.STAFF, UserRole.PLAYER):
            raise MemberError("Role нь staff эсвэл player.")
        member.role = role
    if player_steamid is not None:
        if player_steamid == "":
            member.player_id = None
        else:
            player = db.scalar(select(Player).where(Player.steamid == int(player_steamid)))
            if player is None:
                raise MemberError("Ийм тоглогч алга.")
            member.player_id = player.id
    if member.role == UserRole.PLAYER and member.player_id is None:
        raise MemberError("Тоглогчийн эрхтэй гишүүнийг Player-тай холбоно уу.")
    if is_active is not None:
        member.is_active = is_active
    db.commit()
    return member
