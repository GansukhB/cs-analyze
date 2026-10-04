import uuid

import pytest
from fastapi import WebSocketDisconnect

from app.models import AnalysisJob, JobStatus, Team
from app.routers import jobs as jobs_router
from app.services import jobs

SCOUT = {
    "my_team": "Vitality",
    "opponent": "Spirit",
    "n_my_matches": 1,
    "n_opponent_matches": 1,
    "n_h2h_matches": 0,
    "download": True,
}


def stored(db, row: dict) -> AnalysisJob:
    return db.query(AnalysisJob).filter_by(public_id=uuid.UUID(row["public_id"])).one()


def create(client, auth, **overrides):
    return client.post("/jobs", json={**SCOUT, **overrides}, headers=auth)


@pytest.mark.parametrize(
    "overrides",
    [
        {"opponent": "vitality"},
        {"n_my_matches": 0, "n_opponent_matches": 0, "n_h2h_matches": 0},
        {"n_h2h_matches": 6},
        {"my_team": "   "},
    ],
)
def test_scout_form_rejects(client, auth, dispatched, overrides):
    assert create(client, auth, **overrides).status_code == 422
    assert dispatched == []


def test_create_dispatches_and_records_requester(client, auth, dispatched, db, user):
    response = create(client, auth)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued" and body["requested_by"] == "Bat"
    assert body["label"] == "Vitality vs Spirit" and body["windows"] == "1/1/0"

    job = db.query(AnalysisJob).one()
    assert dispatched == [job.id] and job.celery_task_id == "celery-1"
    assert job.requested_by_id == user.id


def test_only_one_job_in_flight(client, auth, dispatched, db):
    first = create(client, auth).json()
    second = create(client, auth, my_team="FaZe").json()
    assert len(dispatched) == 1

    waiting = stored(db, second)
    assert waiting.celery_task_id == ""

    # The first one finishing hands the slot to the one that waited.
    running = stored(db, first)
    jobs.finish(db, running, {})
    assert len(dispatched) == 2 and waiting.celery_task_id == "celery-2"


def test_cancel_queued_job_starts_the_next(client, auth, dispatched, db):
    first = create(client, auth).json()
    second = create(client, auth, my_team="FaZe").json()

    # Cancelling a job that already went to Celery only asks it to stop.
    status = client.post(f"/jobs/{first['public_id']}/cancel", headers=auth).json()
    # It is still QUEUED in the broker, so it is finalised right away.
    assert status["status"] == "cancelled" and status["finished"] is True
    assert len(dispatched) == 2
    assert stored(db, second).celery_task_id


def test_running_job_is_asked_to_stop(client, auth, dispatched, db):
    first = create(client, auth).json()
    job = stored(db, first)
    jobs.set_stage(db, job, "resolving", 5)

    status = client.post(f"/jobs/{first['public_id']}/cancel", headers=auth).json()
    assert status["status"] == "running"
    with pytest.raises(jobs.JobCancelled):
        jobs.check_cancelled(db, job)


def test_worker_start_fails_the_orphan_and_starts_the_next(client, auth, dispatched, db):
    first = create(client, auth).json()
    second = create(client, auth, my_team="FaZe").json()
    orphan = stored(db, first)
    jobs.set_stage(db, orphan, "fetching", 20)

    jobs.recover(db)
    assert orphan.status == JobStatus.FAILED and "тасарлаа" in orphan.error
    assert dispatched == [orphan.id, stored(db, second).id]


def test_worker_start_sends_a_dispatched_job_again(client, auth, dispatched, db):
    job = stored(db, create(client, auth).json())
    assert job.celery_task_id == "celery-1"

    jobs.recover(db)
    assert job.status == JobStatus.QUEUED and job.celery_task_id == "celery-2"


def test_stale_message_is_skipped(client, auth, dispatched, db):
    from app.tasks import _is_current

    job = stored(db, create(client, auth).json())
    jobs.recover(db)
    assert not _is_current(job, "celery-1") and _is_current(job, "celery-2")
    jobs.set_stage(db, job, "resolving", 5)
    assert not _is_current(job, "celery-2")


def test_detail_list_and_polling(client, auth, dispatched, db, published):
    created = create(client, auth).json()
    job = stored(db, created)
    jobs.set_stage(db, job, "resolving", 5, "Хайж байна")
    jobs.finish_stage(db, job, "resolving", "Vitality vs Spirit", {"teams": 2})

    detail = client.get(f"/jobs/{job.public_id}", headers=auth).json()
    assert detail["status"]["status"] == "running"
    ladder = {s["stage"]: s["state"] for s in detail["status"]["stages"]}
    assert ladder == {
        "resolving": "running",
        "fetching": "pending",
        "unpacking": "pending",
        "parsing": "pending",
    }
    assert detail["status"]["stages"][0]["counts"] == {"teams": 2}
    assert detail["words"]["stages"]["fetching"] == "Demo татаж байна"
    messages = [e["message"] for e in detail["events"]]
    assert messages[-1] == "Хайж байна" and detail["result"] is None

    last = detail["events"][-1]["id"]
    assert client.get(f"/jobs/{job.public_id}?after={last}", headers=auth).json()["events"] == []

    listing = client.get("/jobs", headers=auth).json()
    assert listing["counts"]["running"] == 1 and listing["jobs"][0]["stage"] == "resolving"
    assert {kind for _, kind, _ in published} >= {"event", "status"}


def test_home(client, auth, db):
    db.add_all([Team(name="Vitality", hltv_id=9565), Team(name="Unknown")])
    db.commit()
    home = client.get("/home", headers=auth).json()
    assert home["known_teams"] == ["Vitality"]
    assert home["defaults"] == {"matches": 1, "max_matches": 5}
    assert home["parsed_maps"] == 0 and home["recent_jobs"] == []


# -- the WebSocket -------------------------------------------------------------
@pytest.fixture
def fake_channel(monkeypatch):
    """Stands in for Redis pub/sub: yields these messages, then waits forever."""
    import asyncio
    from contextlib import asynccontextmanager

    queued = []

    @asynccontextmanager
    async def subscribe(public_id):
        async def messages():
            for message in queued:
                yield message
            await asyncio.Event().wait()

        yield messages()

    monkeypatch.setattr(jobs_router.live, "subscribe", subscribe)
    return queued


def test_socket_rejects_a_bad_token(client, auth, dispatched, fake_channel):
    job = create(client, auth).json()
    with client.websocket_connect(f"/ws/jobs/{job['public_id']}") as ws:
        ws.send_json({"token": "nope"})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 4401


def test_socket_sends_snapshot_then_relays(client, auth, dispatched, fake_channel):
    job = create(client, auth).json()
    fake_channel.append({"kind": "activity", "payload": {"text": "татаж байна"}})
    token = auth["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"/ws/jobs/{job['public_id']}") as ws:
        ws.send_json({"token": token})
        snapshot = ws.receive_json()
        assert snapshot["kind"] == "snapshot"
        assert snapshot["payload"]["status"] == JobStatus.QUEUED
        assert snapshot["payload"]["events"][0]["message"].startswith("Дараалалд орлоо")
        assert ws.receive_json() == {"kind": "activity", "payload": {"text": "татаж байна"}}


def test_socket_unknown_job(client, auth, fake_channel):
    token = auth["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect("/ws/jobs/00000000-0000-0000-0000-000000000000") as ws:
        ws.send_json({"token": token})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 4404
