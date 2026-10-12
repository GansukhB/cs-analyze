"""What the footer says about the machine: the host's load and the worker's pulse.

The numbers are the whole host's (cs.bizon.mn runs cstat, MySQL, Redis and the
Scout's Chromium beside us, docs/adr/0004), since that is what decides whether
the next Scout fits. Read with psutil on every request; nothing is stored.

The worker can't be asked cheaply: ``inspect`` is a broadcast that waits its
whole timeout when nobody answers. So the worker says it is alive instead, a
Redis key it rewrites every few seconds and that lapses shortly after it stops.
"""

import contextlib
import threading
import time
from pathlib import Path

import psutil

from app.cache import get_cache
from app.config import get_settings

HEARTBEAT_KEY = "system:worker"
BEAT_SECONDS = 10
BEAT_TTL = 30

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
_beater: threading.Thread | None = None


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


def _beat_loop() -> None:
    while True:
        beat()
        if _stop.wait(BEAT_SECONDS):
            return


def start_heartbeat() -> None:
    """Called once on the worker's start (`tasks._heartbeat`)."""
    global _beater
    _stop.clear()
    _beater = threading.Thread(target=_beat_loop, name="heartbeat", daemon=True)
    _beater.start()


def stop_heartbeat() -> None:
    """On the worker's shutdown: the light goes out now, not when the key lapses."""
    _stop.set()
    if _beater is not None:
        _beater.join(timeout=2)
    with contextlib.suppress(Exception):
        get_cache().delete(HEARTBEAT_KEY)
