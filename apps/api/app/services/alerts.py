"""Telling someone when the platform needs a hand (docs/plans/11 OPS-5).

An alert is a line in the log and, when ``TELEGRAM_BOT_TOKEN`` and
``TELEGRAM_CHAT_ID`` are set, a Telegram message. Each has a key, and one key
is sent at most once in its ``every`` seconds (a Redis key), so a worker that
stays down is said once an hour, not every five minutes.

:func:`checks` is what ``python -m app.cli watch`` looks at every 5 minutes
(a systemd timer): the worker's heartbeat, a Scout stage running too long, the
disk, HLTV refusing the browser several times in a row, the warm-up gone silent,
and requests queued behind a MySQL metadata lock. Other alerts are sent where
they happen: a failed backup or canary (their units' OnFailure), and a User
reaching the Assistant's daily cost limit.

Without Telegram nobody hears them, so they are also shown to Staff on every
page (:func:`shown`, through ``GET /system``): what the last check found, while
it still stands, and every alert said in the last day.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import timedelta

import psutil
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AnalysisJob, JobStatus
from app.models.base import utcnow

logger = logging.getLogger(__name__)

HOUR = 3600
BLOCKED_KEY = "hltv:blocked_in_a_row"
# What the last check found; gone when the checks stop (the timer is down).
ACTIVE_KEY = "alerts:active"
ACTIVE_TTL = 15 * 60
# Every alert said lately, newest last.
RECENT_KEY = "alerts:recent"
RECENT_SECONDS = 24 * HOUR
RECENT_KEEP = 20
# When the warm-up's status was first found missing while the worker is up.
WARM_SILENT_KEY = "alerts:warm_silent_since"
WARM_SILENT_MINUTES = 30
LOCK_WAIT_SECONDS = 300


def configured() -> bool:
    s = get_settings()
    return bool(s.telegram_bot_token.get_secret_value() and s.telegram_chat_id)


def _telegram(text: str) -> None:
    s = get_settings()
    url = f"https://api.telegram.org/bot{s.telegram_bot_token.get_secret_value()}/sendMessage"
    body = json.dumps({"chat_id": s.telegram_chat_id, "text": text}).encode()
    request = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10):  # noqa: S310 (a fixed https URL)
        pass


def send(key: str, text: str, every: int = HOUR) -> bool:
    """Say ``text`` unless ``key`` was said in the last ``every`` seconds. Never raises."""
    from app.cache import get_cache

    try:
        if not get_cache().set(f"alert:{key}", "1", nx=True, ex=every):
            return False
    except (RedisError, RuntimeError):
        pass  # no Redis: better twice than never
    logger.warning("ALERT %s: %s", key, text)
    _remember(key, text)
    if not configured():
        return True
    try:
        _telegram(f"cs-analyze: {text}")
    except Exception:
        logger.exception("could not send the alert to Telegram")
    return True


def _remember(key: str, text: str) -> None:
    from app.cache import get_cache

    entry = json.dumps({"key": key, "text": text, "at": utcnow().isoformat() + "Z"})
    try:
        cache = get_cache()
        cache.rpush(RECENT_KEY, entry)
        cache.ltrim(RECENT_KEY, -RECENT_KEEP, -1)
        cache.expire(RECENT_KEY, RECENT_SECONDS)
    except Exception:  # noqa: BLE001 (showing an alert must never stop sending it)
        logger.warning("could not keep the alert for the pages")


def set_active(found: list[tuple[str, str]]) -> None:
    """What the latest check found, for the pages, while the checks keep running."""
    from app.cache import get_cache

    body = json.dumps([{"key": k, "text": t} for k, t in found])
    try:
        get_cache().set(ACTIVE_KEY, body, ex=ACTIVE_TTL)
    except Exception:  # noqa: BLE001
        logger.warning("could not keep the checks' findings for the pages")


def shown() -> list[dict]:
    """What Staff see on every page: what still stands first, then what was said in
    the last day, newest first; each with its Mongolian title (`mn.ALERTS`)."""
    from datetime import datetime

    from app.cache import get_cache
    from app.services import mn

    try:
        cache = get_cache()
        active = json.loads(cache.get(ACTIVE_KEY) or "[]")
        recent = [json.loads(x) for x in cache.lrange(RECENT_KEY, 0, -1)]
    except Exception:  # noqa: BLE001
        return []
    cutoff = utcnow() - timedelta(seconds=RECENT_SECONDS)
    out, seen = [], set()
    for a in active:
        out.append({**a, "at": None, "active": True})
        seen.add(a["key"])
    for a in reversed(recent):
        try:
            at = datetime.fromisoformat(a["at"].rstrip("Z"))
        except (KeyError, ValueError, AttributeError):
            continue
        if a.get("key") in seen or at < cutoff:
            continue
        seen.add(a["key"])
        out.append({**a, "active": False})
    for a in out:
        a["title"] = mn.alert_title(a["key"])
    return out[:6]


# -- HLTV refusing the browser -------------------------------------------------
def hltv_blocked() -> None:
    """A page Cloudflare never let through: counted until one gets through."""
    from app.cache import get_cache

    try:
        get_cache().incr(BLOCKED_KEY)
    except (RedisError, RuntimeError):
        pass


def hltv_through() -> None:
    from app.cache import get_cache

    try:
        get_cache().delete(BLOCKED_KEY)
    except (RedisError, RuntimeError):
        pass


# -- the periodic checks ---------------------------------------------------------
def checks(db: Session) -> list[tuple[str, str]]:
    """``(key, text)`` for each thing wrong now."""
    from app.cache import get_cache
    from app.services import jobs, system

    s = get_settings()
    out = []
    if not system.worker_alive():
        out.append(("worker", "the worker's heartbeat is gone: Scouts and Review refreshes wait"))
    running = db.scalar(select(AnalysisJob).where(AnalysisJob.status == JobStatus.RUNNING))
    if running is not None and running.stage_log:
        started = running.stage_log[-1].get("started_at")
        if started:
            begun = _naive(started)
            if begun and utcnow() - begun > timedelta(minutes=s.alert_stage_minutes):
                label = jobs.STAGE_LABELS.get(running.stage, running.stage)
                out.append((f"stage:{running.public_id}:{running.stage}",
                            f"Scout {running.label!r} has been at {label} for over "
                            f"{s.alert_stage_minutes} minutes"))  # fmt: skip
    disk = psutil.disk_usage(str(system._existing(s.hltv_data_dir)))
    used = 100 * disk.used / max(disk.used + disk.free, 1)
    if used >= s.alert_disk_percent:
        out.append(("disk", f"the data disk is {used:.0f}% full"))
    try:
        blocked = int(get_cache().get(BLOCKED_KEY) or 0)
    except (RedisError, RuntimeError, ValueError):
        blocked = 0
    if blocked >= s.alert_blocked_in_a_row:
        out.append(("hltv-blocked", f"HLTV refused the browser {blocked} times in a row"))
    if (silent := _warm_silent()) is not None:
        out.append(("warmup", f"the warm-up has said nothing for {silent} minutes: "
                              "pages are not computed ahead"))  # fmt: skip
    if waiting := _lock_waits(db):
        out.append(("mysql-lock", f"{waiting} queries have waited over {LOCK_WAIT_SECONDS // 60} "
                                  "minutes on a MySQL metadata lock"))  # fmt: skip
    return out


def _warm_silent() -> int | None:
    """Minutes the warm-up's status has been missing while the worker is up, once
    past :data:`WARM_SILENT_MINUTES` (one long page or a round's plan writes nothing
    for a while, so a single miss is not one)."""
    from datetime import datetime

    from app.cache import get_cache
    from app.services import system, warmer

    try:
        cache = get_cache()
        if warmer.status() is not None or not system.worker_alive():
            cache.delete(WARM_SILENT_KEY)
            return None
        now = utcnow()
        cache.set(WARM_SILENT_KEY, now.isoformat(), nx=True, ex=24 * HOUR)
        since = datetime.fromisoformat(cache.get(WARM_SILENT_KEY) or now.isoformat())
    except Exception:  # noqa: BLE001
        return None
    minutes = int((now - since).total_seconds() // 60)
    return minutes if minutes >= WARM_SILENT_MINUTES else None


def _lock_waits(db: Session) -> int:
    """Queries waiting past :data:`LOCK_WAIT_SECONDS` on a metadata lock (MySQL only):
    on 2026-11-20 a migration's ALTER waited on an idle transaction, and every page
    reading that table queued behind it."""
    bind = db.get_bind()
    if bind.dialect.name != "mysql":
        return 0
    from sqlalchemy import text

    try:
        with bind.connect() as conn:
            return int(conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.processlist "
                "WHERE state = 'Waiting for table metadata lock' AND time > :s"
            ), {"s": LOCK_WAIT_SECONDS}).scalar() or 0)  # fmt: skip
    except Exception:  # noqa: BLE001 (no PROCESS privilege: it sees its own only)
        return 0


def _naive(iso: str):
    from datetime import datetime

    try:
        return datetime.fromisoformat(iso).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None
