"""Server-Timing on every response, and a log line for a slow one (docs/plans/11 OPS-8).

A plain ASGI middleware, not Starlette's BaseHTTPMiddleware, so the Assistant's
event stream passes through untouched: the time is taken when the headers go
out, which for a stream is when its first event is ready.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

SLOW_MS = 10_000  # a Game Plan tab past this should be warmed earlier (OPS-8)


class ServerTiming:
    def __init__(self, app, origins: list[str]):
        self.app = app
        # Lets the page read the timing through the Resource Timing API.
        self.allow = ", ".join(origins).encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()

        async def timed(message):
            if message["type"] == "http.response.start":
                ms = (time.perf_counter() - start) * 1000
                headers = [
                    *message.get("headers", []),
                    (b"server-timing", f"app;dur={ms:.1f}".encode()),
                ]
                if self.allow:
                    headers.append((b"timing-allow-origin", self.allow))
                message = {**message, "headers": headers}
                if ms > SLOW_MS:
                    logger.warning(
                        "slow request: %s %s %.0f ms", scope["method"], scope["path"], ms
                    )
            await send(message)

        await self.app(scope, receive, timed)
