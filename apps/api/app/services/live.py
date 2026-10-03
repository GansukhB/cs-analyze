"""Live job updates: the worker publishes, the API's WebSocket relays.

One Redis pub/sub channel per job (``job.<public_id>``). Publishing is a plain
synchronous Redis call, so it works from any worker thread -- including one
inside a Playwright session, whose running event loop is what forced cstat's
channel-layer publisher onto a thread of its own. A dropped message costs
nothing: every page reads the same rows back on load, and the socket sends a
fresh snapshot on connect.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis

from app.cache import get_cache
from app.config import get_settings

logger = logging.getLogger(__name__)


def channel(public_id) -> str:
    return f"job.{public_id}"


def publish(public_id, kind: str, payload: dict) -> None:
    """Push one message to the job's channel. Never raises -- Redis being down
    must degrade the live view, not kill the run."""
    try:
        message = json.dumps({"kind": kind, "payload": payload}, default=str)
        get_cache().publish(channel(public_id), message)
    except Exception:
        logger.warning("could not publish %s for job %s", kind, public_id, exc_info=True)


@asynccontextmanager
async def subscribe(public_id) -> AsyncIterator[AsyncIterator[dict]]:
    """Messages published for one job, as an async iterator of ``{kind, payload}``."""
    client = aioredis.from_url(get_settings().redis_cache_url, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel(public_id))

    async def messages() -> AsyncIterator[dict]:
        async for message in pubsub.listen():
            if message.get("type") == "message":
                yield json.loads(message["data"])

    try:
        yield messages()
    finally:
        await pubsub.unsubscribe()
        await pubsub.aclose()
        await client.aclose()
