from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import decode_access_token
from app.services import scope

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

DbSession = Annotated[Session, Depends(get_db)]


def user_from_token(db: Session, token: str | None) -> User | None:
    """The active User a token belongs to, or None.

    Reloaded on every call: this is what cuts off a Deactivated User's still-valid
    token. Shared by the HTTP dependency and the WebSocket handshake.
    """
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    user = user_from_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Everything this request reads sees the User's Workspace and no other's
    # private Matches, and no Scrims unless its page asks (docs/adr/0010, 0011).
    scope.bind(db, user.workspace_id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_staff_user(user: CurrentUser) -> User:
    """Staff only (CONTEXT.md). A Player login sees their own numbers and what Staff
    shared, through the endpoints made for it; everything else is Staff's."""
    if not user.is_staff:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff only")
    return user


StaffUser = Annotated[User, Depends(get_staff_user)]


def can_see_match(db: Session, user: User, match_id: int) -> bool:
    """Staff see every Match their scope does; a Player login, the ones they played
    (docs/plans WS-4) and the ones in a Playlist Staff shared (RV-7)."""
    if user.is_staff:
        return True
    if user.player_id is None:
        return False
    from sqlalchemy import select

    from app.models import MapRoster, MatchMap, Playlist

    played = db.scalar(
        select(MapRoster.id)
        .join(MatchMap, MatchMap.id == MapRoster.match_map_id)
        .where(MatchMap.match_id == match_id, MapRoster.player_id == user.player_id)
        .limit(1)
    )
    if played is not None:
        return True
    shared = db.scalars(
        select(Playlist.items).where(
            Playlist.workspace_id == user.workspace_id, Playlist.shared.is_(True)
        )
    )
    return any(i.get("match_id") == match_id for items in shared for i in items or [])
