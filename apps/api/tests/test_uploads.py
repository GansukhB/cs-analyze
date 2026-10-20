# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""A Workspace's own Demos (DATA-1) and what each scope sees of them (WS-2,
docs/adr/0010, 0011)."""

import datetime as dt

import polars as pl
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import tasks
from app.models import (
    AnalysisJob,
    GameMap,
    JobKind,
    MapRoster,
    Match,
    MatchKind,
    MatchMap,
    MatchSource,
    TickDataset,
    Upload,
    UploadStatus,
    Workspace,
    WorkspaceTeam,
)
from app.models.base import utcnow
from app.services import (
    analysis_store,
    dbctx,
    gameplan,
    mapstrategy,
    pool_cache,
    roles,
    scope,
    tickdata,
    uploads,
)
from tests.test_gameplan import _map, league, memory_cache  # noqa: F401


def _private(db, workspace, kind, home, away, players, day=4):
    match = Match(
        hltv_id=None, workspace_id=workspace.id, kind=kind, source=MatchSource.UPLOAD,
        team1=home, team2=away, played_at=dt.datetime(2026, 9, day),
    )  # fmt: skip
    db.add(match)
    db.flush()
    mirage = db.scalar(select(GameMap).where(GameMap.name == "de_mirage"))
    _map(db, match, 1, mirage, home, away, players=players)
    db.commit()
    return match


def _unscoped(db):
    """The client's requests share this session in tests and bind their scope on it."""
    db.info.pop(scope.KEY, None)
    db.expire_all()
    return db


def _count(db, entity) -> int:
    return db.scalar(select(func.count()).select_from(entity))


def test_each_scope_sees_its_own(db, league, workspace):
    other = Workspace(name="Other club")
    db.add(other)
    db.commit()
    a, b, p = league["a"], league["b"], league["players"]
    _private(db, workspace, MatchKind.SCRIM, a, b, p)
    _private(db, other, MatchKind.OFFICIAL, a, b, p, day=5)

    assert _count(db, Match) == 5  # nothing bound: the worker sees every row
    scope.bind(db, workspace.id)
    assert _count(db, Match) == 3 and _count(db, MatchMap) == 3  # no Scrim, not theirs
    scope.allow_scrims(db)
    assert _count(db, Match) == 4 and _count(db, MatchMap) == 4
    scope.bind(db, other.id)
    assert _count(db, Match) == 4 and _count(db, MatchMap) == 4
    scope.bind(db, None)
    assert _count(db, Match) == 3


def test_a_scrim_leaves_the_pool_and_habits_alone(db, engine, league, workspace):
    a, b, p = league["a"], league["b"], league["players"]
    fresh = sessionmaker(bind=engine, expire_on_commit=False)

    def pool(workspace_id):
        # A new session each time: dbctx.memo keeps a request's reads on its session.
        with fresh() as session, dbctx.using(session):
            scope.bind(session, workspace_id)
            maps = gameplan.parsed_maps()
            return (
                roles._pool_key(maps),
                pool_cache.parse_stamp(),
                [m.id for m in mapstrategy.maps_in_window(session.merge(a))],
                gameplan.build(session.merge(a), session.merge(b))["lede"],
                scope.cache_part(session),
            )

    before = pool(workspace.id)
    _private(db, workspace, MatchKind.SCRIM, a, b, p)
    assert pool(workspace.id) == before

    # An official upload counts, but only inside its Workspace (docs/adr/0011).
    _private(db, workspace, MatchKind.OFFICIAL, a, b, p, day=6)
    after = pool(workspace.id)
    assert after[0] != before[0] and len(after[2]) == len(before[2]) + 1
    assert after[4] == f":ws{workspace.id}"
    assert pool(None) == (*before[:4], "")


@pytest.fixture
def staffed(db, league, workspace, user):
    db.add(WorkspaceTeam(workspace=workspace, team=league["a"]))
    db.commit()
    return league


@pytest.fixture
def sent(monkeypatch) -> list:
    out: list = []
    monkeypatch.setattr(uploads, "dispatch", lambda db, job: out.append(job.id))
    return out


def _describe(client, auth, team_id, **extra):
    body = {
        "kind": "scrim",
        "played_on": "2026-10-20",
        "my_team_id": team_id,
        "opponent_name": "Partner Five",
        "filename": "scrim-mirage.dem",
        "size": 10,
        **extra,
    }
    return client.post("/uploads", json=body, headers=auth)


def test_an_upload_arrives_in_parts_and_queues_its_parse(client, db, auth, staffed, sent):
    made = _describe(client, auth, staffed["a"].id)
    assert made.status_code == 201, made.text
    up = made.json()
    assert up["parts_total"] == 1 and up["status"] == "receiving"

    early = client.post(f"/uploads/{up['id']}/complete", headers=auth)
    assert early.status_code == 400

    part = client.put(
        f"/uploads/{up['id']}/parts/0", files={"data": ("p0", b"0123456789")}, headers=auth
    )
    assert part.json() == {"received": 1, "parts_total": 1}
    done = client.post(f"/uploads/{up['id']}/complete", headers=auth).json()
    assert done["status"] == "queued" and done["job_id"]
    job = db.scalar(select(AnalysisJob).where(AnalysisJob.id == sent[0]))
    assert job.kind == JobKind.UPLOAD
    assert [u["id"] for u in client.get("/uploads", headers=auth).json()["uploads"]] == [up["id"]]


def test_my_team_must_be_the_workspaces(client, auth, staffed, sent):
    out = _describe(client, auth, staffed["b"].id)
    assert out.status_code == 400 and "my team" in out.json()["detail"]
    assert _describe(client, auth, staffed["a"].id, filename="notes.txt").status_code == 400


def _sides_frame(first: list[int], second: list[int]) -> pl.DataFrame:
    rows = []
    for n in range(1, 13):
        ct, t = (first, second) if n <= 6 else (second, first)
        rows += [{"round_num": n, "steamid": s, "side": "ct"} for s in ct]
        rows += [{"round_num": n, "steamid": s, "side": "t"} for s in t]
    return pl.DataFrame(rows)


class FakeParsed:
    map_name = "de_mirage"
    n_rounds = 12
    awpy_version = "2.0.2"

    def __init__(self, first, second):
        self.player_sides = _sides_frame(first, second)
        self.roster = pl.DataFrame(
            [{"steamid": s, "name": f"p{s}", "clan_name": ""} for s in first + second]
        )


def test_side_groups_follow_the_half_swap():
    parsed = FakeParsed([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
    assert uploads.side_groups(parsed) == [[1, 2, 3, 4, 5], [6, 7, 8, 9, 10]]
    assert uploads.pick_mine([[1, 2, 3], [4, 5, 6]], mine={4, 5}, theirs=set()) == 1
    assert uploads.pick_mine([[1, 2, 3], [4, 5, 6]], mine={4}, theirs=set()) is None
    assert uploads.pick_mine([[1, 2, 3], [4, 5, 6]], mine=set(), theirs={1, 2}) == 1


@pytest.fixture
def worker(monkeypatch, db, engine, tmp_path):
    """The upload task on the test database, with the parse and ingest faked."""
    calls: list = []
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(tasks, "SessionLocal", factory)
    monkeypatch.setattr(tasks.jobs.live, "publish", lambda *a, **k: None)

    def fake_ingest(session, demo, parsed, *, bundle=None, on_step=None, sides=None):
        calls.append(sides)
        for stale in [o for o in session.identity_map.values() if isinstance(o, TickDataset)]:
            session.expunge(stale)
        session.query(MatchMap).filter_by(
            match_id=demo.match_id, map_number=demo.map_number
        ).delete()
        match = demo.match
        mm = MatchMap(
            match_id=match.id, demo_id=demo.id, map_number=demo.map_number, n_rounds=12,
            parsed_at=utcnow(), schema_version=analysis_store.CURRENT_SCHEMA_VERSION,
        )  # fmt: skip
        if sides:
            mm.team1_id, mm.team2_id = match.team1_id, match.team2_id
        session.add(mm)
        session.flush()
        session.add(TickDataset(match_map_id=mm.id, bundle=b"x", size_bytes=1, tables=["ticks"]))
        session.commit()
        return mm

    monkeypatch.setattr(analysis_store, "ingest_map", fake_ingest)
    monkeypatch.setattr(analysis_store, "rebuild_player_match", lambda *a, **k: None)
    return calls


def _received(db, client, auth, team_id, first, second, monkeypatch):
    up = _describe(client, auth, team_id).json()
    client.put(f"/uploads/{up['id']}/parts/0", files={"data": ("p0", b"0123456789")}, headers=auth)
    parsed = FakeParsed(first, second)
    monkeypatch.setattr(
        tickdata, "parse_parts", lambda *a, **k: tickdata.Parse(parsed=parsed, bundle=b"x")
    )
    monkeypatch.setattr(tickdata, "parsed_map", lambda *a, **k: parsed)
    client.post(f"/uploads/{up['id']}/complete", headers=auth)
    return db.scalar(select(Upload).where(Upload.filename == "scrim-mirage.dem"))


def test_the_job_knows_our_five_from_their_maps(
    client, db, auth, staffed, sent, worker, monkeypatch
):
    ours = [p.steamid for p in staffed["players"][staffed["a"].id]]
    upload = _received(
        db, client, auth, staffed["a"].id, [901, 902, 903, 904, 905], ours, monkeypatch
    )
    tasks.ingest_upload.run(upload.job_id)
    upload = _unscoped(db).get(Upload, upload.id)
    assert upload.status == UploadStatus.DONE, upload.error
    assert worker[0] == {**dict.fromkeys(ours, staffed["a"].id), **{
        s: db.get(Match, upload.match_id).team2_id for s in (901, 902, 903, 904, 905)
    }}  # fmt: skip
    assert upload.maps[0]["mine"] == 1 and upload.maps[0]["assigned"] is True
    match = db.get(Match, upload.match_id)
    assert match.kind == MatchKind.SCRIM and match.hltv_id is None and match.workspace_id
    assert _count(db, MapRoster) >= 0  # the fake ingest writes no roster


def test_unknown_players_wait_for_staff_then_go_in(
    client, db, auth, staffed, sent, worker, monkeypatch
):
    upload = _received(
        db, client, auth, staffed["a"].id, [1, 2, 3, 4, 5], [6, 7, 8, 9, 10], monkeypatch
    )
    tasks.ingest_upload.run(upload.job_id)
    upload = _unscoped(db).get(Upload, upload.id)
    assert upload.status == UploadStatus.NEEDS_SIDES and worker == [None]
    read = client.get(f"/uploads/{upload.public_id}", headers=auth).json()
    assert read["maps"][0]["mine"] is None and len(read["maps"][0]["groups"]) == 2

    answered = client.post(
        f"/uploads/{upload.public_id}/sides", json={"map_number": 1, "mine": 0}, headers=auth
    ).json()
    assert answered["status"] == "queued"
    tasks.ingest_upload.run(_unscoped(db).get(Upload, upload.id).job_id)
    upload = _unscoped(db).get(Upload, upload.id)
    assert upload.status == UploadStatus.DONE, upload.error
    assert worker[1][1] == staffed["a"].id and upload.maps[0]["assigned"] is True


def test_another_workspace_cannot_see_an_upload(client, db, auth, staffed, sent):
    up = _describe(client, auth, staffed["a"].id).json()
    other = Workspace(name="Other club")
    db.add(other)
    db.commit()
    upload = _unscoped(db).scalar(select(Upload))
    upload.workspace_id = other.id
    db.commit()
    assert client.get(f"/uploads/{up['id']}", headers=auth).status_code == 404


def test_a_scrims_page_is_its_workspaces_alone(client, db, auth, league, workspace):
    a, b, p = league["a"], league["b"], league["players"]
    ours = _private(db, workspace, MatchKind.SCRIM, a, b, p)
    other = Workspace(name="Other club")
    db.add(other)
    db.commit()
    theirs = _private(db, other, MatchKind.SCRIM, a, b, p, day=5)
    page = client.get(f"/matches/{ours.id}", headers=auth)
    assert page.status_code == 200 and page.json()["kind"] == "scrim"
    assert page.json()["hltv_url"] == ""
    assert client.get(f"/matches/{theirs.id}", headers=auth).status_code == 404
    # Scrims never reach the Team's page, even the Workspace's own.
    results = client.get(f"/teams/{a.id}", headers=auth).json()["results"]
    assert ours.id not in {r.get("match_id") for r in results}


def test_the_scrim_log_lists_my_teams_scrims_only(client, db, auth, staffed, workspace):
    a, b, p = staffed["a"], staffed["b"], staffed["players"]
    ours = _private(db, workspace, MatchKind.SCRIM, a, b, p)
    other = Workspace(name="Other club")
    db.add(other)
    db.commit()
    _private(db, other, MatchKind.SCRIM, a, b, p, day=5)
    _unscoped(db)
    log = client.get("/scrims", headers=auth).json()
    assert log["team"]["id"] == a.id and [s["match_id"] for s in log["scrims"]] == [ours.id]
    assert log["scrims"][0]["partner"] == "Bravo" and log["scrims"][0]["maps"][0]["label"]
    assert client.get(f"/scrims?team_id={b.id}", headers=auth).status_code == 404


def test_a_players_scrims_show_in_his_form_and_not_his_partners(
    client, db, auth, staffed, workspace
):
    a, b, p = staffed["a"], staffed["b"], staffed["players"]
    _private(db, workspace, MatchKind.SCRIM, a, b, p, day=7)
    _unscoped(db)
    ours, theirs = p[a.id][0], p[b.id][0]
    form = client.get(f"/players/{ours.steamid}", headers=auth).json()["form"]
    assert [r["scrim"] for r in form].count(True) == 1 and len(form) == 3
    partner = client.get(f"/players/{theirs.steamid}", headers=auth).json()["form"]
    assert not any(r["scrim"] for r in partner)
