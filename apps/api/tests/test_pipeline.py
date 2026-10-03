"""The scout pipeline end to end, with HLTV and awpy faked.

The archive is real (a tar, which bsdtar reads exactly like HLTV's RAR5), so
unpacking runs for real; resolving, fetching and parsing talk to fakes. The run
goes match by match and must leave nothing behind in its scratch folder.
"""

import datetime as dt
import io
import tarfile

import pytest

from app import tasks
from app.config import get_settings
from app.models import AnalysisJob, Demo, MapRoster, Match, MatchMap, Team, TickDataset
from app.models.base import utcnow
from app.services import analysis_store, browser, client, demo_parser, jobs, tickdata

VITALITY = client.Team(id=9565, name="Vitality", slug="vitality")
SPIRIT = client.Team(id=7020, name="Spirit", slug="spirit")


def scraped(match_id: int, team1: str, team2: str) -> client.Match:
    return client.Match(
        id=match_id,
        slug=f"{team1}-vs-{team2}".lower(),
        team1=team1,
        team2=team2,
        score="2 - 0",
        event="Major 2026",
        played_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
    )


RESULTS = {
    VITALITY.id: [scraped(101, "Vitality", "FaZe"), scraped(102, "Vitality", "NAVI")],
    SPIRIT.id: [scraped(201, "Spirit", "G2")],
}


class FakeBrowser:
    downloads: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def is_connected(self):
        return True

    def download(self, url, dest, on_progress=None):
        """Write an archive holding one map demo, the way HLTV names them."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(dest, "w") as archive:
            data = b"not really a demo"
            member = tarfile.TarInfo(f"{dest.stem.split('-', 1)[1]}-m1-de_anubis.dem")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        if on_progress:
            on_progress(10, 20, 0.5)
        FakeBrowser.downloads.append(url)
        return dest


class FakeClient:
    def __init__(self, _browser):
        pass

    def resolve_team(self, term):
        return {"vitality": VITALITY, "spirit": SPIRIT}.get(term.lower())

    def latest_matches(self, team, limit):
        return RESULTS[team.id][:limit]

    def demo_link(self, match):
        return f"/download/demo/{match.id}"


class FakeParsed:
    map_name = "de_anubis"
    n_rounds = 21


INGESTED: list = []


def fake_ingest(db, demo, parsed, *, bundle=None, on_step=None):
    """What ingest leaves behind that the job reads back: a parsed map with a roster,
    and its Tick Data."""
    if on_step:
        on_step("roster")
    INGESTED.append((demo.map, bundle))
    db.query(MatchMap).filter_by(match_id=demo.match_id, map_number=demo.map_number).delete()
    match = demo.match
    match_map = MatchMap(
        match_id=match.id,
        demo_id=demo.id,
        map_number=demo.map_number,
        n_rounds=21,
        team1_score=13,
        team2_score=8,
        parsed_at=utcnow(),
        schema_version=analysis_store.CURRENT_SCHEMA_VERSION,
    )
    db.add(match_map)
    db.flush()
    db.add(MapRoster(match_map_id=match_map.id, player_id=_player(db).id, team_id=match.team1_id))
    if bundle is not None:
        db.add(TickDataset(match_map_id=match_map.id, bundle=bundle, size_bytes=len(bundle),
                           tables=["ticks", *tickdata.EXTRA_TABLES]))  # fmt: skip
    db.commit()
    return match_map


def _player(db):
    from app.models import Player

    player = db.query(Player).first()
    if player is None:
        player = Player(steamid=1, name="ZywOo")
        db.add(player)
        db.flush()
    return player


@pytest.fixture
def pipeline(monkeypatch, tmp_path, db, user):
    monkeypatch.setattr(get_settings(), "hltv_data_dir", tmp_path)
    monkeypatch.setattr(browser, "HltvBrowser", FakeBrowser)
    monkeypatch.setattr(client, "HltvClient", FakeClient)
    monkeypatch.setattr(demo_parser, "parse_map", lambda path: FakeParsed())
    monkeypatch.setattr(analysis_store, "ingest_map", fake_ingest)
    monkeypatch.setattr(tickdata, "pack", lambda parsed, scratch: b"tick data")
    FakeBrowser.downloads = []
    INGESTED.clear()

    def run(**fields):
        job = AnalysisJob(
            my_team_name="Vitality",
            opponent_name="Spirit",
            n_my_matches=2,
            n_opponent_matches=1,
            n_h2h_matches=0,
            requested_by_id=user.id,
            **fields,
        )
        db.add(job)
        db.commit()
        tasks.run_pipeline(db, db, job)
        return job

    return run


def test_downloads_unpacks_and_parses(pipeline, db, tmp_path, published):
    job = pipeline()

    assert job.status == "success" and job.stage == "done" and job.progress == 100
    assert [s["state"] for s in jobs.stage_ladder(job)] == ["done"] * 4
    assert job.my_team.hltv_id == VITALITY.id and job.opponent.hltv_id == SPIRIT.id
    assert len(FakeBrowser.downloads) == 3

    archive = db.query(Demo).filter_by(map="").all()
    assert len(archive) == 3 and all(d.is_processed for d in archive)
    map_demos = db.query(Demo).filter(Demo.map != "").all()
    assert {d.map for d in map_demos} == {"anubis"} and all(d.is_processed for d in map_demos)
    # Parsed from the Demo, stored with its Tick Data, and every file gone.
    assert INGESTED == [("anubis", b"tick data")] * 3
    assert all(not d.path for d in db.query(Demo).all())
    assert not any((tmp_path / "tmp").rglob("*"))

    result = job.result
    assert result["totals"]["fetching"] == {
        "downloaded": 3,
        "skipped": 0,
        "missing": 0,
        "failed": 0,
    }
    assert result["totals"]["unpacking"] == {"archives": 3, "maps": 3, "failed": 0}
    assert result["totals"]["parsing"] == {"parsed": 3, "rounds": 63, "failed": 0}
    assert result["totals"]["reparsing"] == {"parsed": 0, "rounds": 0, "failed": 0, "stuck": 0}
    assert [m["hltv_id"] for m in result["windows"]["mine"]] == [101, 102]
    assert [m["hltv_id"] for m in result["windows"]["theirs"]] == [201]
    assert result["windows"]["mine"][0]["maps"][0] == {
        "map": "?",
        "map_number": 1,
        "scoreline": "13-8",
        "rounds": 21,
        "parsed": True,
    }
    assert result["windows"]["mine"][0]["demo"] == "processed"
    assert {m["hltv_id"] for m in result["parsed_matches"]} == {101, 102, 201}
    assert {m.hltv_id for m in job.matches} == {101, 102, 201}

    stepped = [e for e in job.events if e.payload.get("steps")]
    assert stepped and stepped[0].payload == {"match": 101, "step": 1, "steps": 3}
    assert any(kind == "activity" for _, kind, _ in published)


def test_second_run_skips_everything(pipeline, db):
    pipeline()
    again = pipeline()
    assert again.status == "success"
    assert [s["state"] for s in jobs.stage_ladder(again)] == ["done"] * 4
    assert again.result["totals"]["fetching"]["skipped"] == 3
    assert again.result["totals"]["unpacking"] == {"archives": 0, "maps": 0, "failed": 0}
    assert again.result["totals"]["parsing"] == {"parsed": 0, "rounds": 0, "failed": 0}
    assert len(FakeBrowser.downloads) == 3


def test_offline_run_needs_a_known_team(pipeline, db):
    with pytest.raises(ValueError, match="татах хэсэг нь хаалттай"):
        pipeline(download=False)


def test_offline_run_uses_what_is_stored(pipeline, db):
    pipeline()
    offline = pipeline(download=False)
    assert offline.status == "success" and offline.result["windows"] is None
    assert len(offline.result["parsed_matches"]) == 3
    assert [s["state"] for s in jobs.stage_ladder(offline)] == ["done"] * 4


def test_stale_maps_reparse_from_stored_tick_data(pipeline, db, monkeypatch):
    pipeline()
    db.query(MatchMap).update({"schema_version": analysis_store.CURRENT_SCHEMA_VERSION - 1})
    db.commit()
    read_back = []
    monkeypatch.setattr(
        tickdata,
        "parsed_map",
        lambda blob, label, version="": read_back.append(blob) or FakeParsed(),
    )
    INGESTED.clear()
    offline = pipeline(download=False)
    assert offline.result["totals"]["reparsing"] == {
        "parsed": 3,
        "rounds": 63,
        "failed": 0,
        "stuck": 0,
    }
    # No Demo was on disk: each map was read back from its own Tick Data.
    assert read_back == [b"tick data"] * 3 and INGESTED == [("anubis", b"tick data")] * 3
    assert len(FakeBrowser.downloads) == 3


def test_tick_data_without_the_economy_is_downloaded_again(pipeline, db, monkeypatch):
    pipeline()
    db.query(MatchMap).update({"schema_version": analysis_store.CURRENT_SCHEMA_VERSION - 1})
    for dataset in db.query(TickDataset):
        dataset.tables = ["ticks", *tickdata.DETONATION_TABLES]
    db.commit()
    monkeypatch.setattr(tickdata, "parsed_map", lambda *a, **k: pytest.fail("re-parsed"))

    offline = pipeline(download=False)
    assert offline.result["totals"]["reparsing"]["stuck"] == 3
    again = pipeline()
    assert again.result["totals"]["fetching"]["downloaded"] == 3
    assert again.result["totals"]["parsing"]["parsed"] == 3
    assert again.result["totals"]["reparsing"]["stuck"] == 0
    assert any("эдийн засаг байхгүй" in e.message for e in again.events)


def test_a_map_that_never_parsed_is_downloaded_again(pipeline, db, monkeypatch):
    calls = {"n": 0}

    def flaky(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise demo_parser.DemoParseError("corrupt demo")
        return FakeParsed()

    monkeypatch.setattr(demo_parser, "parse_map", flaky)
    first = pipeline()
    assert first.result["totals"]["parsing"]["failed"] == 1
    assert first.result["totals"]["reparsing"]["stuck"] == 1
    again = pipeline()
    # The archive was unpacked, but its one map has neither a Demo nor Tick Data.
    assert len(FakeBrowser.downloads) == 4
    assert again.result["totals"]["fetching"]["downloaded"] == 1
    assert again.result["totals"]["parsing"]["parsed"] == 1


def test_stop_before_start(pipeline, db, monkeypatch):
    def cancelled_already(job_db, job):
        raise jobs.JobCancelled()

    monkeypatch.setattr(jobs, "check_cancelled", cancelled_already)
    with pytest.raises(jobs.JobCancelled):
        pipeline()
    assert db.query(Team).count() == 0 and db.query(Match).count() == 0
