"""A Workspace's people (docs/plans/01 WS-3): Staff list and change members and
make invite links; anyone with a link opens and uses it without signing in."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.deps import DbSession, StaffUser
from app.models import Invite, Player, User, Workspace
from app.models.base import utcnow
from app.routers.auth import FAILURE_WINDOW_SECONDS, FAILURES_PER_ADDRESS, client_address
from app.schemas import (
    InviteAccept,
    InviteCreate,
    InvitePublic,
    InviteRead,
    MemberPatch,
    MemberPlayer,
    MemberRead,
    Token,
    WorkspaceMembers,
)
from app.security import create_access_token
from app.services import members, ratelimit

router = APIRouter(tags=["workspace"])


def _player(db, player_id: int | None) -> MemberPlayer | None:
    player = db.get(Player, player_id) if player_id else None
    return MemberPlayer(steamid=str(player.steamid), name=player.name) if player else None


def _member(db, user: User) -> MemberRead:
    return MemberRead(
        id=user.id,
        username=user.username,
        role=user.role,
        player=_player(db, user.player_id),
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def _invite(db, row: Invite, token: str = "") -> InviteRead:
    target = db.get(User, row.user_id) if row.user_id else None
    return InviteRead(
        id=row.id,
        role=row.role,
        player=_player(db, row.player_id),
        username=target.username if target else "",
        created_at=row.created_at,
        expires_at=row.expires_at,
        used_at=row.used_at,
        token=token,
    )


def _fail(exc: members.MemberError):
    raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None


@router.get("/workspace/members")
def list_members(db: DbSession, user: StaffUser) -> WorkspaceMembers:
    """Everyone in the Workspace, and the invites still open."""
    people = db.scalars(
        select(User).where(User.workspace_id == user.workspace_id).order_by(User.username)
    ).all()
    open_invites = db.scalars(
        select(Invite)
        .where(
            Invite.workspace_id == user.workspace_id,
            Invite.used_at.is_(None),
            Invite.expires_at >= utcnow(),
        )
        .order_by(Invite.created_at.desc())
    ).all()
    return WorkspaceMembers(
        members=[_member(db, u) for u in people],
        invites=[_invite(db, i) for i in open_invites],
    )


@router.patch("/workspace/members/{member_id}")
def change_member(member_id: int, body: MemberPatch, db: DbSession, user: StaffUser) -> MemberRead:
    member = db.get(User, member_id)
    if member is None or member.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such member")
    try:
        members.change(db, user, member, **body.model_dump(exclude_unset=True))
    except members.MemberError as exc:
        _fail(exc)
    return _member(db, member)


@router.post("/workspace/invites", status_code=status.HTTP_201_CREATED)
def create_invite(body: InviteCreate, db: DbSession, user: StaffUser) -> InviteRead:
    """A one-time link. Its token is in this answer only: the page builds the URL."""
    try:
        row, token = members.invite(db, user, **body.model_dump())
    except members.MemberError as exc:
        _fail(exc)
    return _invite(db, row, token)


@router.delete("/workspace/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(invite_id: int, db: DbSession, user: StaffUser) -> None:
    row = db.get(Invite, invite_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such invite")
    db.delete(row)
    db.commit()


@router.get("/invites/{token}")
def open_invite(token: str, db: DbSession) -> InvitePublic:
    row = members.find(db, token)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This invite is used, expired or unknown")
    target = db.get(User, row.user_id) if row.user_id else None
    player = _player(db, row.player_id)
    return InvitePublic(
        workspace=db.get(Workspace, row.workspace_id).name,
        role=row.role,
        player=player.name if player else "",
        username=target.username if target else "",
    )


@router.post("/invites/{token}/accept")
def accept_invite(token: str, body: InviteAccept, request: Request, db: DbSession) -> Token:
    """Make the User (or set the reset password) and sign them in."""
    key = f"rl:invite:ip:{client_address(request)}"
    if ratelimit.count(key) >= FAILURES_PER_ADDRESS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many tries; wait 15 minutes")
    try:
        user = members.accept(db, token, body.username, body.password)
    except members.MemberError as exc:
        ratelimit.record(key, FAILURE_WINDOW_SECONDS)
        _fail(exc)
    return Token(access_token=create_access_token(user.id))
