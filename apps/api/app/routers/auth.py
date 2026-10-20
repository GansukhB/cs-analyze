from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import User
from app.models.base import utcnow
from app.schemas import Token, UserRead
from app.security import create_access_token, verify_password
from app.services import ratelimit

router = APIRouter(prefix="/auth", tags=["auth"])


# Failed sign-ins allowed per Username and per address in a window. Every attempt
# costs an argon2 hash, and Players sign in from their own machines now.
FAILURES_PER_USERNAME = 10
FAILURES_PER_ADDRESS = 30
FAILURE_WINDOW_SECONDS = 15 * 60


def client_address(request: Request) -> str:
    """The caller's address: behind Cloudflare and nginx the socket's peer is a proxy."""
    forwarded = request.headers.get("cf-connecting-ip") or request.headers.get("x-real-ip")
    return forwarded or (request.client.host if request.client else "unknown")


@router.post("/token")
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], request: Request, db: DbSession
) -> Token:
    keys = (
        (f"rl:login:user:{form.username}", FAILURES_PER_USERNAME),
        (f"rl:login:ip:{client_address(request)}", FAILURES_PER_ADDRESS),
    )
    if any(ratelimit.count(key) >= limit for key, limit in keys):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-ins; try again in 15 minutes",
            headers={"Retry-After": str(FAILURE_WINDOW_SECONDS)},
        )
    user = db.scalar(select(User).where(User.username == form.username))
    password_ok = verify_password(form.password, user.password_hash if user else None)
    if user is None or not password_ok or not user.is_active:
        for key, _ in keys:
            ratelimit.record(key, FAILURE_WINDOW_SECONDS)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    ratelimit.clear(keys[0][0])
    user.last_login_at = utcnow()
    db.commit()
    return Token(access_token=create_access_token(user.id))


@router.get("/me")
def me(user: CurrentUser) -> UserRead:
    return UserRead.of(user)
