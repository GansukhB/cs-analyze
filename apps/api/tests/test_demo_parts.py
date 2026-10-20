"""Demo parts (CONTEXT.md, docs/adr/0009): named from their files, numbered as
played, and merged into one Match Map's Tick Data."""

import io
import zipfile
from functools import cached_property
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import polars as pl
import pytest

from app.services import demo_parser, tickdata
from app.services.archive import parse_demo_name
from tests.test_tickdata import _bundle


@pytest.fixture(autouse=True)
def _unchecked_parse(monkeypatch):
    """These tests fake the parse with stand-ins that carry no frames to check."""
    monkeypatch.setattr(demo_parser, "quality", lambda parsed: ([], []))


@pytest.mark.parametrize(
    ("name", "map_", "number", "part"),
    [
        ("vitality-vs-inner-circle-m1-anubis.dem", "anubis", 1, 0),
        ("chinggis-warriors-vs-vitalem-aerem-m1-nuke-p1.dem", "nuke", 1, 1),
        ("maps/the-huns-vs-depo-m2-inferno-p2.dem", "inferno", 2, 2),
        ("magic-vs-the-mongolz-mirage.dem", "mirage", None, 0),
        ("falcons-vs-k27-de_dust2.dem", "dust2", None, 0),
    ],
)
def test_demo_names(name, map_, number, part):
    entry = parse_demo_name(name)
    assert (entry.map, entry.map_number, entry.part) == (map_, number, part)


def test_an_unfamiliar_name_still_fits_the_column():
    assert len(parse_demo_name("x" * 80 + ".dem").map) == 40


class _Parser:
    def parse_event(self, name, other=None):
        # The restored count carries on from round 3, after a pseudo-event at the start.
        return pd.DataFrame(
            {"tick": [4, 6844, 14091, 21379], "total_rounds_played": [float("nan"), 4, 5, 6]}
        )


def test_a_part_numbers_its_rounds_as_the_game_counted_them():
    parsed = SimpleNamespace(
        path=Path("x-m1-ancient-p2.dem"),
        _demo=SimpleNamespace(parser=_Parser()),
        rounds=pl.DataFrame({"round_num": [1, 2, 3, 4], "end": [6844, 14091, 21379, 30000]}),
    )
    # The last round's end isn't among the events: it follows the one before.
    assert demo_parser.round_numbers(parsed).rows() == [(1, 4), (2, 5), (3, 6), (4, 7)]


def test_a_part_without_molotovs_still_parses():
    class Dem:
        @cached_property
        def infernos(self):
            raise KeyError(
                "Required event 'inferno_startburn' is missing from the events dictionary."
            )

    dem = Dem()
    assert demo_parser._optional(dem, "infernos").is_empty()
    assert dem.infernos.is_empty()  # compress() finds it and doesn't ask again


def _numbers(*pairs: tuple[int, int]) -> pl.DataFrame:
    return pl.DataFrame(
        list(pairs), schema={"round_num": pl.Int64, "number": pl.Int64}, orient="row"
    )


def _with_sightings(blob: bytes) -> bytes:
    buffer = io.BytesIO(blob)
    with zipfile.ZipFile(buffer, "a") as bundle:
        frame = pl.DataFrame(
            {"round_num": [1, 2], "tick": [1300, 3300], "steamid": [11, 21], "spotter": [21, 11]},
            schema_overrides={"steamid": pl.UInt64, "spotter": pl.UInt64},
        )
        out = io.BytesIO()
        frame.write_parquet(out)
        bundle.writestr("sightings.parquet", out.getvalue())
    return buffer.getvalue()


def test_parts_merge_into_one_bundle_numbered_as_played():
    first = _with_sightings(_bundle())  # rounds 1-2, ticks 1000-3950
    second = _bundle()  # resumed from the backup of round 2
    blob, missing = tickdata.merge(
        [(first, _numbers((1, 1), (2, 2))), (second, _numbers((1, 2), (2, 3)))]
    )
    assert missing == []
    merged = tickdata.read(blob)
    rounds = merged.tables["rounds"]
    assert rounds["round_num"].to_list() == [1, 2, 3]
    # Round 2 was played again in the second part: that one counts. The second
    # part's ticks follow the first part's last one.
    offset = 3950 + tickdata.PART_GAP_TICKS
    assert rounds["start"].to_list() == [1000, 1000 + offset, 3000 + offset]
    assert rounds.schema == tickdata.read(second).tables["rounds"].schema
    ticks = merged.tables["ticks"]
    by_round = {n: ticks.filter(pl.col("round_num") == n)["tick"] for n in (1, 2, 3)}
    assert by_round[1].max() < by_round[2].min() and by_round[2].max() < by_round[3].min()
    assert "sightings" not in merged.tables  # the second part has none
    assert merged.header["map_name"] == "de_nuke"

    parsed = tickdata.parsed_map(blob, "alpha-vs-bravo-m1-nuke-p1.dem")
    assert parsed.n_rounds == 3
    assert parsed.economy["round_num"].unique().sort().to_list() == [1, 2, 3]
    assert parsed.round_sides["round_num"].sort().to_list() == [1, 2, 3]


def test_sightings_stay_when_every_part_has_them():
    part = _with_sightings(_bundle())
    blob, _missing = tickdata.merge([(part, _numbers((1, 1), (2, 2))), (part, _numbers((1, 3)))])
    assert tickdata.read(blob).tables["sightings"]["round_num"].to_list() == [1, 2, 3]


def test_a_round_no_part_holds_is_reported_missing():
    blob, missing = tickdata.merge(
        [(_bundle(), _numbers((1, 1), (2, 2))), (_bundle(), _numbers((1, 5), (2, 6)))]
    )
    assert missing == [3, 4]
    assert tickdata.read(blob).tables["rounds"]["round_num"].to_list() == [1, 2, 5, 6]


def test_a_part_that_wont_parse_is_left_out(monkeypatch, tmp_path):
    def parse(path):
        if path.name.endswith("p1.dem"):
            raise demo_parser.DemoParseError("Required event 'inferno_startburn' is missing")
        return SimpleNamespace(path=path, awpy_version="2.0.2")

    monkeypatch.setattr(demo_parser, "parse_map", parse)
    monkeypatch.setattr(demo_parser, "round_numbers", lambda parsed: _numbers((1, 8), (2, 9)))
    monkeypatch.setattr(tickdata, "pack", lambda parsed, scratch: _bundle())
    paths = [tmp_path / "x-m1-ancient-p1.dem", tmp_path / "x-m1-ancient-p2.dem"]

    result = tickdata.parse_parts(paths, tmp_path)
    assert [name for name, _error in result.failed] == ["x-m1-ancient-p1.dem"]
    assert result.missing == list(range(1, 8))
    assert result.parsed.n_rounds == 2
    assert result.parsed.rounds["round_num"].to_list() == [8, 9]

    # A lone part is still numbered as played.
    alone = tickdata.parse_parts(paths[1:], tmp_path, parts=True)
    assert alone.parsed.rounds["round_num"].to_list() == [8, 9]

    with pytest.raises(demo_parser.DemoParseError, match="no Demo part could be parsed"):
        tickdata.parse_parts(paths[:1], tmp_path, parts=True)
