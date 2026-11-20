"""Alerts and the every-5-minutes checks (docs/plans/11 OPS-5)."""

from datetime import timedelta

from pydantic import SecretStr

import app.cache
from app.config import get_settings
from app.models import AnalysisJob, JobStatus
from app.models.base import utcnow
from app.services import alerts, system


class FakeRedis:
    def __init__(self):
        self.store: dict = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def get(self, key):
        return self.store.get(key)

    def incr(self, key):
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    def delete(self, key):
        self.store.pop(key, None)


def test_an_alert_is_sent_once_an_hour_and_to_telegram_when_set(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(app.cache, "get_cache", lambda: redis)
    sent = []
    monkeypatch.setattr(alerts, "_telegram", sent.append)
    assert alerts.send("disk", "full") is True and sent == []  # no Telegram: the log only
    settings = get_settings()
    monkeypatch.setattr(settings, "telegram_bot_token", SecretStr("t"))
    monkeypatch.setattr(settings, "telegram_chat_id", "42")
    assert alerts.send("disk", "full") is False  # said in the last hour
    assert alerts.send("worker", "down") is True and sent == ["cs-analyze: down"]


def test_the_checks_name_what_is_wrong(db, monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(app.cache, "get_cache", lambda: redis)
    monkeypatch.setattr(system, "worker_alive", lambda: True)
    monkeypatch.setattr(get_settings(), "alert_disk_percent", 101.0)
    assert alerts.checks(db) == []
    long_ago = (utcnow() - timedelta(minutes=50)).isoformat() + "+00:00"
    log = [{"stage": "parsing", "started_at": long_ago}]
    db.add(AnalysisJob(my_team_name="A", opponent_name="B", status=JobStatus.RUNNING,
                       stage="parsing", stage_log=log))  # fmt: skip
    db.commit()
    for _ in range(3):
        alerts.hltv_blocked()
    monkeypatch.setattr(system, "worker_alive", lambda: False)
    keys = [k.split(":")[0] for k, _t in alerts.checks(db)]
    assert keys == ["worker", "stage", "hltv-blocked"]
    alerts.hltv_through()
    assert "hltv-blocked" not in [k for k, _t in alerts.checks(db)]


class ListRedis(FakeRedis):
    """With the lists the pages' copy of the alerts is kept in."""

    def rpush(self, key, value):
        self.store.setdefault(key, []).append(value)

    def ltrim(self, key, start, end):
        self.store[key] = self.store.get(key, [])[start : (None if end == -1 else end + 1)]

    def expire(self, key, seconds):
        pass

    def lrange(self, key, start, end):
        return list(self.store.get(key, []))


def test_staff_see_what_stands_and_what_was_said_today(monkeypatch):
    redis = ListRedis()
    monkeypatch.setattr(app.cache, "get_cache", lambda: redis)
    alerts.send("unit:cs2-backup.service", "cs2-backup.service failed")
    alerts.set_active([("disk", "the data disk is 91% full")])
    shown = alerts.shown()
    assert [(a["key"], a["active"]) for a in shown] == [
        ("disk", True), ("unit:cs2-backup.service", False),
    ]  # fmt: skip
    assert shown[0]["title"] == "Диск дүүрч байна"
    assert shown[1]["title"] == "Шөнийн backup амжилтгүй болсон" and shown[1]["at"]


def test_a_silent_warm_up_is_said_after_half_an_hour(monkeypatch):
    from app.services import warmer

    redis = ListRedis()
    monkeypatch.setattr(app.cache, "get_cache", lambda: redis)
    monkeypatch.setattr(system, "worker_alive", lambda: True)
    monkeypatch.setattr(warmer, "status", lambda: None)
    assert alerts._warm_silent() is None  # first miss: one long page writes nothing
    redis.store[alerts.WARM_SILENT_KEY] = (utcnow() - timedelta(minutes=40)).isoformat()
    assert alerts._warm_silent() == 40
    monkeypatch.setattr(warmer, "status", lambda: {"state": "working"})
    assert alerts._warm_silent() is None and alerts.WARM_SILENT_KEY not in redis.store
