from functools import lru_cache

from redis import Redis

from app.config import get_settings


@lru_cache
def get_cache() -> Redis:
    """Redis client for application caching and job pub/sub (its own logical DB)."""
    return Redis.from_url(
        get_settings().redis_cache_url, decode_responses=True, socket_connect_timeout=2
    )
