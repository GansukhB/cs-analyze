"""Importing cstat: a hand-built cstat database and demo folder, with awpy faked."""

import sqlite3

import pytest
from sqlalchemy import func, select

from app.models import Demo, Match, MatchMap, Team, TeamAlias, TickDataset, Tournament
from app.models.base import utcnow
from app.services import analysis_store, cstat_import, demo_parser, tickdata

SCHEMA = """
CREATE TABLE hltv_team (id INTEGER PRIMARY KEY, hltv_id INTEGER, name TEXT, slug TEXT);
CREATE TABLE hltv_teamalias (id INTEGER PRIMARY KEY, clan_name TEXT, note TEXT, team_id INTEGER);
CREATE TABLE hltv_event (id INTEGER PRIMARY KEY, hltv_id INTEGER, name TEXT, slug TEXT);
CREATE TABLE hltv_match (id INTEGER PRIMARY KEY, hltv_id INTEGER, slug TEXT, score TEXT,
  team1_score INTEGER, team2_score INTEGER, played_at TEXT, demo_url TEXT, demo_checked_at TEXT,
  event_id INTEGER, team1_id INTEGER, team2_id INTEGER);
CREATE TABLE hltv_demo (id INTEGER PRIMARY KEY, url TEXT, filename TEXT, path TEXT,
  size_bytes INTEGER, error TEXT, downloaded_at TEXT, match_id INTEGER, is_downloaded INTEGER,
  is_processed INTEGER, map TEXT, map_number INTEGER, processed_at TEXT);
"""


@pytest.fixture
def cstat(tmp_path):
    """Two teams, one match on Anubis and Nuke; Nuke's .dem has been deleted."""
    folder = tmp_path / "data" / "maps" / "100-alpha-vs-bravo-cup"
    folder.mkdir(parents=True)
    (folder / "alpha-vs-bravo-m1-anubis.dem").write_bytes(b"demo")
    con = sqlite3.connect(tmp_path / "db.sqlite3")
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO hltv_team VALUES (?, ?, ?, ?)",
                    [(1, 501, "Alpha", "alpha"), (2, None, "Bravo", "")])  # fmt: skip
    con.execute("INSERT INTO hltv_teamalias VALUES (1, 'ALPHA esports', '', 1)")
    con.execute("INSERT INTO hltv_event VALUES (1, 77, 'Cup 2026', 'cup-2026')")
    con.execute(
        "INSERT INTO hltv_match VALUES (1, 100, 'alpha-vs-bravo-cup', '2 - 0', 2, 0, "
        "'2026-08-27 11:08:13', '/download/demo/9', NULL, 1, 1, 2)"
    )
    con.executemany(
        "INSERT INTO hltv_demo VALUES "
        "(?, '', ?, ?, 10, '', '2026-08-28 10:00:00', 1, 1, 1, ?, ?, NULL)",
        [(1, "alpha-vs-bravo-cup.rar", "/gone/x.rar", "", None),
         (2, "alpha-vs-bravo-m1-anubis.dem", "/gone/elsewhere.dem", "anubis", 1),
         (3, "alpha-vs-bravo-m2-nuke.dem", "", "nuke", 2)],
    )  # fmt: skip
    con.commit()
    con.close()
    return tmp_path


@pytest.fixture
def parsed_paths(monkeypatch, tmp_path):
    seen = []

    def fake_ingest(db, demo, parsed, *, bundle=None, on_step=None):
        match_map = MatchMap(match_id=demo.match_id, demo_id=demo.id, map_number=demo.map_number,
                             n_rounds=21, parsed_at=utcnow(),
                             schema_version=analysis_store.CURRENT_SCHEMA_VERSION)  # fmt: skip
        db.add(match_map)
        db.flush()
        db.add(TickDataset(match_map_id=match_map.id, bundle=bundle, size_bytes=len(bundle),
                           tables=["ticks", *tickdata.EXTRA_TABLES]))  # fmt: skip
        db.commit()
        return match_map

    class Parsed:
        n_rounds = 21
        awpy_version = "2.0.2"

    monkeypatch.setattr(demo_parser, "parse_map", lambda path: seen.append(path.name) or Parsed())
    monkeypatch.setattr(tickdata, "pack", lambda parsed, scratch: b"tick data")
    monkeypatch.setattr(analysis_store, "ingest_map", fake_ingest)
    monkeypatch.setattr(
        cstat_import, "get_settings", lambda: type("S", (), {"hltv_data_dir": tmp_path})
    )
    return seen


def test_imports_rows_and_parses_what_is_on_disk(db, cstat, parsed_paths):
    totals = cstat_import.run(db, cstat, log=lambda _line: None)
    assert totals == {"maps": 2, "parsed": 1, "current": 0, "missing": 1, "failed": 0}
    # The recorded path is gone; the file was found by name under data/maps.
    assert parsed_paths == ["alpha-vs-bravo-m1-anubis.dem"]
    match = db.scalar(select(Match).where(Match.hltv_id == 100))
    assert match.team1.name == "Alpha" and match.team1.hltv_id == 501
    assert match.team2.name == "Bravo" and match.team2.hltv_id is None
    assert match.tournament.name == "Cup 2026" and match.score == "2 - 0"
    assert db.scalar(select(TeamAlias.team_id).where(TeamAlias.clan_name == "ALPHA esports")) == (
        match.team1_id
    )
    demos = {d.map: d for d in db.scalars(select(Demo).where(Demo.match_id == match.id))}
    assert demos[""].is_processed and demos["anubis"].is_processed
    assert not demos["nuke"].is_processed and demos["nuke"].path == ""

    # A second run finds the map current and parses nothing.
    again = cstat_import.run(db, cstat, log=lambda _line: None)
    assert again["current"] == 1 and again["parsed"] == 0 and len(parsed_paths) == 1
    assert db.scalar(select(func.count()).select_from(Team)) == 2

    # Tick Data read before the Loadout was is stale here: only the Demo adds it.
    dataset = db.scalar(select(TickDataset))
    dataset.tables = ["ticks", *tickdata.DETONATION_TABLES, tickdata.ECONOMY_TABLE]
    db.commit()
    assert not cstat_import._current(demos["anubis"])


def test_what_cs_analyze_holds_wins(db, cstat, parsed_paths):
    mine = Team(name="Alpha Esports", hltv_id=501, slug="")
    db.add(mine)
    db.add(Tournament(name="Cup 2026"))
    db.add(Match(hltv_id=100, team1=mine, score="1 - 2"))
    db.commit()
    cstat_import.run(db, cstat, parse=False, log=lambda _line: None)
    match = db.scalar(select(Match).where(Match.hltv_id == 100))
    assert match.score == "1 - 2" and match.team1.name == "Alpha Esports"
    assert match.team1.slug == "alpha" and match.team2.name == "Bravo"
    assert match.played_at is not None and match.tournament.hltv_id == 77
    assert parsed_paths == []


def test_no_database_is_a_clear_error(db, tmp_path):
    with pytest.raises(FileNotFoundError, match="No cstat database"):
        cstat_import.run(db, tmp_path)


def test_demo_parts_kept_as_stems_are_merged(db, cstat, parsed_paths, monkeypatch):
    """cstat kept a Demo part's whole stem as its map, with no map number."""
    import polars as pl

    folder = cstat / "data" / "maps" / "100-alpha-vs-bravo-cup"
    con = sqlite3.connect(cstat / "db.sqlite3")
    for n, part in ((4, "p1"), (5, "p2")):
        name = f"alpha-vs-bravo-m2-nuke-{part}"
        (folder / f"{name}.dem").write_bytes(b"demo")
        con.execute(
            "INSERT INTO hltv_demo VALUES (?, '', ?, '', 10, '', NULL, 1, 1, 1, ?, NULL, NULL)",
            (n, f"{name}.dem", name),
        )
    con.execute("DELETE FROM hltv_demo WHERE id = 3")
    con.commit()
    con.close()
    numbers = pl.DataFrame({"round_num": [1], "number": [1]})
    monkeypatch.setattr(demo_parser, "round_numbers", lambda parsed: numbers)
    merged = []
    monkeypatch.setattr(tickdata, "merge", lambda parts: merged.append(len(parts)) or (b"m", []))
    one = type("Parsed", (), {"n_rounds": 30})()
    monkeypatch.setattr(tickdata, "parsed_map", lambda blob, label, version="": one)

    totals = cstat_import.run(db, cstat, log=lambda _line: None)
    assert totals == {"maps": 2, "parsed": 2, "current": 0, "missing": 0, "failed": 0}
    assert merged == [2]
    assert parsed_paths[-2:] == ["alpha-vs-bravo-m2-nuke-p1.dem", "alpha-vs-bravo-m2-nuke-p2.dem"]
    parts = db.scalars(select(Demo).where(Demo.map == "nuke").order_by(Demo.part)).all()
    assert [(d.part, d.map_number, d.is_processed) for d in parts] == [(1, 2, True), (2, 2, True)]

    again = cstat_import.run(db, cstat, log=lambda _line: None)
    assert again["current"] == 2 and again["parsed"] == 0
