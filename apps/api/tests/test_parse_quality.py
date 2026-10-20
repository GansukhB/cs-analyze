"""The parse's sanity check: a broken Player is refused, a spectator is not."""

from types import SimpleNamespace

import polars as pl
import pytest

from app.services import demo_parser, tickdata


def _parsed(players: int = 10, broken: set[int] = frozenset(), spectator: bool = False,
            rounds: int = 4, ticks: int = 400):  # fmt: skip
    rows = []
    for r in range(1, rounds + 1):
        for sid in range(1, players + 1):
            for tick in range(ticks):
                empty = sid in broken
                rows.append({"round_num": r, "tick": r * 10_000 + tick, "steamid": sid,
                             "name": f"p{sid}", "side": "ct" if sid <= 5 else "t",
                             "X": None if empty else 1.0})  # fmt: skip
        if spectator:
            for tick in range(ticks):
                rows.append({"round_num": r, "tick": r * 10_000 + tick, "steamid": 99,
                             "name": "caster", "side": None, "X": None})  # fmt: skip
    frame = pl.DataFrame(rows, schema_overrides={"X": pl.Float64, "side": pl.String})
    return SimpleNamespace(
        ticks=frame, rounds=pl.DataFrame({"round_num": list(range(1, rounds + 1))})
    )


def test_a_clean_parse_passes():
    assert demo_parser.quality(_parsed()) == ([], [])


def test_a_spectator_without_positions_is_not_a_failure():
    assert demo_parser.quality(_parsed(spectator=True)) == ([], [])


def test_a_player_with_no_positions_is_refused():
    errors, _ = demo_parser.quality(_parsed(broken={7}))
    assert errors == ["p7 has no position in 100% of their ticks"]


def test_rounds_missing_players_are_a_warning():
    errors, warnings = demo_parser.quality(_parsed(players=9))
    assert errors == [] and warnings == ["4 of 4 rounds have fewer than 10 players"]


def test_parse_parts_refuses_a_broken_parse(monkeypatch, tmp_path):
    monkeypatch.setattr(demo_parser, "parse_map", lambda path: _parsed(broken={3}))
    with pytest.raises(demo_parser.DemoParseError, match="looks broken: p3"):
        tickdata.parse_parts([tmp_path / "x-m1-inferno.dem"], tmp_path)
