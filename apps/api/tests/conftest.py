import os

os.environ["JWT_SECRET"] = "test-only-secret-at-least-32-bytes-long"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import db as database  # noqa: E402
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, Workspace  # noqa: E402
from app.security import create_access_token, hash_password  # noqa: E402
from app.services import heavy, live, pool_cache, ratelimit, review_pool  # noqa: E402


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


class FakeRedis:
    """What `pool_cache` asks of Redis: get, set (nx, ex) and delete."""

    def __init__(self):
        self.store: dict = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def delete(self, key):
        self.store.pop(key, None)

    def incr(self, key):
        self.store[key] = int(self.store.get(key) or 0) + 1
        return self.store[key]

    def expire(self, key, seconds):
        return key in self.store


@pytest.fixture(autouse=True)
def pool_redis(monkeypatch) -> FakeRedis:
    """The Pool's Redis as a dict, empty for every test."""
    fake = FakeRedis()
    monkeypatch.setattr(pool_cache, "get_cache", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def heavy_redis(monkeypatch) -> FakeRedis:
    """The heavy permit's Redis as a dict, empty for every test."""
    fake = FakeRedis()
    monkeypatch.setattr(heavy, "get_cache", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def limits_redis(monkeypatch) -> FakeRedis:
    """The rate limits' Redis as a dict, empty for every test."""
    fake = FakeRedis()
    monkeypatch.setattr(ratelimit, "get_cache", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def review_refreshes(monkeypatch) -> list:
    """Review refreshes the code under test asked for, instead of a real broker;
    and no tallies cut in one test leak into the next."""
    asked = []
    monkeypatch.setattr(review_pool, "request_refresh", lambda **kw: asked.append(kw) or True)
    review_pool._cached.clear()
    yield asked
    review_pool._cached.clear()


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
def client(db: Session, engine, monkeypatch) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    # Code that opens its own short sessions (the job socket) gets the test database too.
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def workspace(db: Session) -> Workspace:
    workspace = Workspace(name="The Huns")
    db.add(workspace)
    db.commit()
    return workspace


@pytest.fixture
def user(db: Session, workspace: Workspace) -> User:
    user = User(username="Bat", password_hash=hash_password("correct-horse"), workspace=workspace)
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def login(client: TestClient, username: str, password: str):
    return client.post("/auth/token", data={"username": username, "password": password})
