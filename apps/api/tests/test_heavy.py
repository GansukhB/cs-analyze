"""One heavy job at a time on the host (OPS-6)."""

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.services import heavy


def test_the_permit_is_held_inside_and_released_after(heavy_redis):
    with heavy.permit("job:a"):
        assert heavy.holder() == "job:a"
    assert heavy.holder() is None


def test_a_second_parse_waits_and_can_be_stopped(heavy_redis):
    told = []
    with heavy.permit("job:a"):
        with pytest.raises(heavy.Cancelled):
            with heavy.permit("job:b", on_wait=told.append, cancelled=lambda: True, poll=0):
                pass
    assert told == ["job:a"]
    assert heavy.holder() is None


def test_a_permit_is_never_released_by_someone_else(heavy_redis):
    with heavy.permit("job:a"):
        heavy._release("job:b|whatever")
        assert heavy.holder() == "job:a"


def test_without_redis_the_work_goes_ahead(monkeypatch):
    class Down:
        def set(self, *a, **k):
            raise RedisConnectionError("down")

        def get(self, *a, **k):
            raise RedisConnectionError("down")

        def delete(self, *a, **k):
            raise RedisConnectionError("down")

    monkeypatch.setattr(heavy, "get_cache", lambda: Down())
    ran = []
    with heavy.permit("job:a"):
        ran.append(True)
    assert ran == [True]
