"""The worker's pulse, beaten from a process of its own (`system.start_heartbeat`).

A thread of the worker can't keep time: a demo's parse holds the GIL for
seconds at a time, long enough on the 2-CPU host for the key to lapse while the
worker was fine. This process does nothing but write the key every
``system.BEAT_SECONDS`` while the worker that started it lives. When the worker
is gone (killed, so nobody stopped us), our parent changes, we exit, and the key
lapses ``system.BEAT_TTL`` later, which is what the watch's alert waits for.

Run as ``python -m app.services.heartbeat`` from apps/api; the worker starts it
and terminates it on shutdown.
"""

import os
import signal
import sys
import time

from app.services import system

# How often we look whether the worker is still there, between beats.
CHECK_SECONDS = 1.0


def beat_while_parent_lives(parent: int) -> None:
    last = None
    while os.getppid() == parent:
        now = time.monotonic()
        if last is None or now - last >= system.BEAT_SECONDS:
            system.beat()
            last = now
        time.sleep(CHECK_SECONDS)


def main() -> None:
    parent = os.getppid()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    # Ctrl-C in a dev terminal reaches the whole group; the worker stops us itself.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    beat_while_parent_lives(parent)


if __name__ == "__main__":
    main()
