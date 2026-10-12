import datetime as dt
import threading

import pytest

from app.models import AnalysisJob, JobStage, JobStatus
from app.services import system
from tests.conftest import FakeRedis


@pytest.fixture(autouse=True)
def heartbeat_redis(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(system, "get_cache", lambda: fake)
    return fake


def _job(db, status: str, **fields) -> AnalysisJob:
    job = AnalysisJob(my_team_name="Vitality", opponent_name="MOUZ", status=status, **fields)
    db.add(job)
    db.commit()
    return job


def test_system_needs_a_login(client):
    assert client.get("/system").status_code == 401


def test_system_reports_the_host(client, auth):
    body = client.get("/system", headers=auth).json()
    host = body["host"]
    assert 0 <= host["cpu_percent"] <= 100
    assert host["cpus"] >= 1
    assert len(host["load"]) == 3
    for usage in (host["memory"], host["disk"]):
        assert 0 < usage["used"] <= usage["total"]
    assert host["uptime"] > 0
    assert body["worker"] is False
    assert body["scout"] is None
    assert body["queued"] == 0


def test_system_names_the_running_scout_and_counts_the_queue(client, auth, db):
    job = _job(
        db,
        JobStatus.RUNNING,
        stage=JobStage.PARSING,
        started_at=dt.datetime(2026, 10, 12, 9),
        stage_log=[{"stage": "parsing", "cycle": 2, "cycles": 5}],
    )
    _job(db, JobStatus.QUEUED)
    _job(db, JobStatus.QUEUED)
    _job(db, JobStatus.SUCCESS)

    body = client.get("/system", headers=auth).json()

    assert body["scout"]["public_id"] == str(job.public_id)
    assert body["scout"]["label"] == "Vitality vs MOUZ"
    assert body["scout"]["cycle"] == {"n": 2, "of": 5}
    assert body["queued"] == 2


def test_heartbeat_lights_the_worker_and_shutdown_puts_it_out(client, auth, heartbeat_redis):
    system.beat()
    assert client.get("/system", headers=auth).json()["worker"] is True

    system.stop_heartbeat()
    assert client.get("/system", headers=auth).json()["worker"] is False


def test_cpu_share_runs_from_the_last_reading_whichever_thread_asks(monkeypatch):
    # psutil.cpu_percent keeps its baseline per thread, so on the API's threadpool
    # it read 0.0; ours is the process's.
    readings = iter([(0.0, 0.0), (5.0, 10.0), (8.0, 20.0)])
    monkeypatch.setattr(system, "_cpu_times", lambda: next(readings))
    monkeypatch.setattr(system, "CPU_SAMPLE_SECONDS", 0)
    monkeypatch.setattr(system, "CPU_REUSE_SECONDS", 0)
    monkeypatch.setattr(system, "_cpu", {"at": 0.0, "times": None, "percent": 0.0})

    assert system._cpu_percent() == 50.0
    seen = []
    worker = threading.Thread(target=lambda: seen.append(system._cpu_percent()))
    worker.start()
    worker.join()
    assert seen == [30.0]
