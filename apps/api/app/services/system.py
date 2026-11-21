"""What the footer says about the machine: the host's load and the worker's pulse.

The numbers are the whole host's (cs.bizon.mn runs cstat, MySQL, Redis and the
Scout's Chromium beside us, docs/adr/0004), since that is what decides whether
the next Scout fits. Read with psutil on every request; nothing is stored.

The worker can't be asked cheaply: ``inspect`` is a broadcast that waits its
whole timeout when nobody answers. So the worker says it is alive instead, a
Redis key it rewrites every few seconds and that lapses shortly after it stops.

The key is written by a small child process (`app/services/heartbeat.py`), not
by a thread of the worker. A demo's parse holds the GIL for seconds at a time,
and on the 2-CPU host a thread went 30 s without a turn during a big Map's
parse: on 2026-11-21 three "heartbeat is gone" alerts came in one afternoon,
each mid-parse, while the worker was fine. The child beats while the worker
lives and stops when it goes.
"""

import contextlib
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

from app.cache import get_cache
from app.config import get_settings

logger = logging.getLogger(__name__)

HEARTBEAT_KEY = "system:worker"
BEAT_SECONDS = 10
BEAT_TTL = 30
# Where `python -m app.services.heartbeat` resolves (apps/api).
APP_ROOT = Path(__file__).resolve().parents[2]

# CPU % is the busy share of CPU time between two readings. Polls closer than
# this reuse the last figure; after a long gap the first poll samples afresh
# instead of reporting the average since the previous viewer left. The baseline
# is ours, per process: psutil.cpu_percent keeps one per thread, and every
# request lands on another threadpool thread, where it reads 0.0.
CPU_REUSE_SECONDS = 1.0
CPU_STALE_SECONDS = 30.0
CPU_SAMPLE_SECONDS = 0.3

_cpu_lock = threading.Lock()
_cpu: dict = {"at": 0.0, "times": None, "percent": 0.0}
_stop = threading.Event()
_keeper: threading.Thread | None = None
_child: subprocess.Popen | None = None
_child_lock = threading.Lock()


def _cpu_times() -> tuple[float, float]:
    """(busy, total) CPU seconds, counted the way psutil.cpu_percent counts them."""
    t = psutil.cpu_times()
    # Linux counts guest time inside user and nice already.
    total = sum(t) - getattr(t, "guest", 0.0) - getattr(t, "guest_nice", 0.0)
    return total - t.idle - getattr(t, "iowait", 0.0), total


def _cpu_percent() -> float:
    with _cpu_lock:
        age = time.monotonic() - _cpu["at"]
        if age < CPU_REUSE_SECONDS:
            return _cpu["percent"]
        if _cpu["times"] is None or age >= CPU_STALE_SECONDS:
            _cpu["times"] = _cpu_times()
            time.sleep(CPU_SAMPLE_SECONDS)
        (busy0, total0), (busy1, total1) = _cpu["times"], _cpu_times()
        span = total1 - total0
        _cpu["percent"] = (
            round(min(max(busy1 - busy0, 0.0) / span, 1.0) * 100, 1) if span > 0 else 0.0
        )
        _cpu["times"] = busy1, total1
        _cpu["at"] = time.monotonic()
        return _cpu["percent"]


def _existing(path: Path) -> Path:
    """The nearest folder that exists: the data folder appears with the first job."""
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def host() -> dict:
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    # The disk the Scouts download onto. Its total is what we can fill (used +
    # free), so a full disk reads 100% even with root's reserved blocks left.
    disk = psutil.disk_usage(str(_existing(get_settings().hltv_data_dir)))
    return {
        "cpu_percent": _cpu_percent(),
        "cpus": psutil.cpu_count() or 1,
        "load": list(psutil.getloadavg()),
        "memory": {"used": memory.total - memory.available, "total": memory.total},
        "swap": {"used": swap.used, "total": swap.total},
        "disk": {"used": disk.used, "total": disk.used + disk.free},
        "uptime": time.time() - psutil.boot_time(),
    }


def worker_alive() -> bool:
    try:
        return get_cache().get(HEARTBEAT_KEY) is not None
    except Exception:  # Redis down: no worker can take a job either
        return False


def beat() -> None:
    with contextlib.suppress(Exception):  # Redis down: the light goes out, the worker goes on
        get_cache().set(HEARTBEAT_KEY, str(time.time()), ex=BEAT_TTL)


def _spawn() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "app.services.heartbeat"], cwd=APP_ROOT, stdin=subprocess.DEVNULL
    )


def _keep() -> None:
    """Start the beating child, and start it again if it dies while the worker lives.
    Waiting on it needs no GIL, so a parse doesn't hold this up either."""
    global _child
    while not _stop.is_set():
        try:
            with _child_lock:
                if _stop.is_set():
                    return
                _child = _spawn()
            code = _child.wait()
        except Exception:  # noqa: BLE001 - a light that can't start must not stop the worker
            logger.exception("heartbeat process could not start")
            code = None
        if _stop.wait(BEAT_SECONDS):  # stopped on purpose
            return
        logger.warning("heartbeat process exited (%s); starting it again", code)


def start_heartbeat() -> None:
    """Called once on the worker's start (`tasks._heartbeat`)."""
    global _keeper
    _stop.clear()
    _keeper = threading.Thread(target=_keep, name="heartbeat", daemon=True)
    _keeper.start()


def stop_heartbeat() -> None:
    """On the worker's shutdown: the light goes out now, not when the key lapses."""
    _stop.set()
    with _child_lock:
        child = _child
    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=2)
    if _keeper is not None:
        _keeper.join(timeout=2)
    # After the child is gone, so no last beat lands behind it.
    with contextlib.suppress(Exception):
        get_cache().delete(HEARTBEAT_KEY)
