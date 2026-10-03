import os

os.environ["JWT_SECRET"] = "test-only-secret-at-least-32-bytes-long"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import create_access_token, hash_password  # noqa: E402
from app.services import live  # noqa: E402


@pytest.fixture
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        # One shared connection: returning it to the pool must not roll back the
        # session that is still using it (jobs.check_cancelled opens a connection).
        pool_reset_on_return=None,
    )

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        # ON DELETE CASCADE / SET NULL only run on SQLite with this on.
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(engine) -> Session:
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture(autouse=True)
def published(monkeypatch) -> list:
    """Live messages the code under test published, instead of sending them to Redis."""
    sent = []
    monkeypatch.setattr(
        live,
        "publish",
        lambda public_id, kind, payload: sent.append((str(public_id), kind, payload)),
    )
    return sent


@pytest.fixture
def dispatched(monkeypatch) -> list:
    """Job ids handed to Celery, instead of a real broker."""
    from app import tasks
    from app.celery_app import celery_app

    sent = []

    class _Result:
        def __init__(self, n):
            self.id = f"celery-{n}"

    def delay(job_id):
        sent.append(job_id)
        return _Result(len(sent))

    monkeypatch.setattr(tasks.run_analysis, "delay", delay)
    monkeypatch.setattr(celery_app.control, "revoke", lambda *args, **kwargs: None)
    return sent


@pytest.fixture
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def user(db: Session) -> User:
    user = User(username="Bat", password_hash=hash_password("correct-horse"))
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def login(client: TestClient, username: str, password: str):
    return client.post("/auth/token", data={"username": username, "password": password})
