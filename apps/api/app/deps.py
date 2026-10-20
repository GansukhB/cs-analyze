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
