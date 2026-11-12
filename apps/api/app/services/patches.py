"""CS2 patch eras and the Active Duty Map pool by date (docs/plans/02 DATA-7).

Both live in ``app/data/patches.json``, edited by hand and committed: a patch
that changes how Rounds play (an economy rule, a Map in or out, the C4) starts
an era, and a Match Map belongs to the latest patch on or before the day it was
played. Nothing is stored per Match Map, so a patch added later re-labels
everything on the next read.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "data" / "patches.json"


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(PATH.read_text())


def _day(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def every() -> list[dict]:
    """Every patch, oldest first: ``{date, name, note}``."""
    return sorted(_data()["patches"], key=lambda p: p["date"])


def era(when) -> dict | None:
    """The patch a day falls under: the latest one on or before it."""
    if when is None:
        return None
    day = _day(when).isoformat()
    found = None
    for p in every():
        if p["date"] <= day:
            found = p
    return found


def latest() -> dict | None:
    listed = every()
    return listed[-1] if listed else None


def pool_on(when=None) -> tuple[str, ...]:
    """The Active Duty Maps on a day (today when none is given)."""
    day = (_day(when) if when is not None else date.today()).isoformat()
    return tuple(
        sorted(
            name
            for name, periods in _data()["pool"].items()
            if any((lo is None or lo <= day) and (hi is None or day < hi) for lo, hi in periods)
        )
    )


def pool_changed(when=None) -> date:
    """The day the Active Duty Maps last changed, on or before ``when`` (today when
    none is given): a Veto from before it was made over another pool."""
    day = (_day(when) if when is not None else date.today()).isoformat()
    edges = {
        edge
        for periods in _data()["pool"].values()
        for lo, hi in periods
        for edge in (lo, hi)
        if edge is not None and edge <= day
    }
    return date.fromisoformat(max(edges)) if edges else date(2023, 9, 27)
