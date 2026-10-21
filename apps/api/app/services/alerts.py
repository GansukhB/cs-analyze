"""Telling someone when the platform needs a hand (docs/plans/11 OPS-5).

An alert is a line in the log and, when ``TELEGRAM_BOT_TOKEN`` and
``TELEGRAM_CHAT_ID`` are set, a Telegram message. Each has a key, and one key
is sent at most once in its ``every`` seconds (a Redis key), so a worker that
stays down is said once an hour, not every five minutes.

:func:`checks` is what ``python -m app.cli watch`` looks at every 5 minutes
(a systemd timer): the worker's heartbeat, a Scout stage running too long, the
disk, and HLTV refusing the browser several times in a row. Other alerts are
sent where they happen: a failed backup or canary (their units' OnFailure), and
a User reaching the Assistant's daily cost limit.
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
    if not configured():
        return True
    try:
        _telegram(f"cs-analyze: {text}")
    except Exception:
        logger.exception("could not send the alert to Telegram")
    return True


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
    return out


def _naive(iso: str):
    from datetime import datetime

    try:
        return datetime.fromisoformat(iso).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None
