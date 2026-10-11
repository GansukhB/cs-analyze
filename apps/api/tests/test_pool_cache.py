import json

from redis.exceptions import RedisError

from app.services import pool_cache


def test_computed_once_and_shaped_by_json(pool_redis):
    calls = []

    def compute():
        calls.append(1)
        return {"pair": (1, 2), 3: "three"}

    first = pool_cache.remember("k", compute)
    second = pool_cache.remember("k", compute)
    # Computed here or read back, the caller sees what JSON gives back.
    assert first == second == {"pair": [1, 2], "3": "three"}
    assert len(calls) == 1
    assert "k:lock" not in pool_redis.store


def test_waits_for_the_process_computing_it(pool_redis, monkeypatch):
    pool_redis.store["k:lock"] = "1"

    def theirs_lands(_seconds):
        pool_redis.store["k"] = json.dumps([7])
        del pool_redis.store["k:lock"]

    monkeypatch.setattr(pool_cache.time, "sleep", theirs_lands)
    assert pool_cache.remember("k", lambda: [0]) == [7]


def test_a_dead_holder_is_waited_out(pool_redis, monkeypatch):
    pool_redis.store["k:lock"] = "1"
    clock = iter(range(0, 10_000, 60))
    monkeypatch.setattr(pool_cache.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(pool_cache.time, "sleep", lambda _s: None)
    assert pool_cache.remember("k", lambda: [1]) == [1]
    # It was not ours to release.
    assert pool_redis.store["k:lock"] == "1"


def test_without_redis_it_is_computed(monkeypatch):
    def down():
        raise RedisError("down")

    monkeypatch.setattr(pool_cache, "get_cache", down)
    assert pool_cache.remember("k", lambda: (1,)) == [1]
