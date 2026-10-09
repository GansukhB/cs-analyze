"""Spots (CONTEXT.md): the finer names players give parts of a Map.

The game's Callout (``place``) is coarse: Inferno's "BombsiteB" is Coffin, Dark,
New Box and Fountain at once. Each Map's Spots are hand-drawn polygons in world
units, in ``app/data/spots/<map>.json``::

    {"map": "de_inferno", "spots": [
        {"name": "Coffin", "callouts": ["BombsiteB"], "poly": [[x, y], ...], "z": [lo, hi]}
    ]}

The first Spot whose polygon holds a point wins, so the files list small Spots
before the bigger ones around them. ``callouts`` (the game Callouts a point must
have) and ``z`` keep a Spot on its own floor where two overlap in 2D. A point in
no Spot is named by its Callout, made readable ("TopofMid" is "Top of Mid").

Spots name things in the Review and label the Replay. Setups, the Playbook and
heatmaps stay on Callouts: they group habits by place, and finer places would
split them below their Evidence strength.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

SPOTS_DIR = Path(__file__).resolve().parent.parent / "data" / "spots"

# Game Callouts whose split-camel-case reading isn't what anyone says.
_CALLOUT_LABELS = {
    "BombsiteA": "A Site",
    "BombsiteB": "B Site",
    "CTSpawn": "CT Spawn",
    "TSpawn": "T Spawn",
    "TopofMid": "Top of Mid",
    "BackofA": "Back of A",
    "BackofB": "Back of B",
    "TRamp": "T Ramp",
    "TStairs": "T Stairs",
    "TSideUpper": "T Upper",
    "TSideLower": "T Lower",
    "CTSideUpper": "CT Upper",
    "TTruck": "T Truck",
    "CTLane": "CT Lane",
    "AMain": "A Main",
    "BMain": "B Main",
    "AHalls": "A Halls",
    "BHalls": "B Halls",
    "ABoost": "A Boost",
    "AStairs": "A Stairs",
    "ForkLift": "Forklift",
}


def callout_label(place: str | None) -> str:
    """A game Callout as words: ``SecondMid`` → ``Second Mid``."""
    place = (place or "").strip()
    if not place:
        return ""
    if place in _CALLOUT_LABELS:
        return _CALLOUT_LABELS[place]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", place)


def _key(map_name: str) -> str:
    name = (map_name or "").strip().lower()
    return name if name.startswith(("de_", "cs_")) else f"de_{name}"


@lru_cache(maxsize=32)
def spots(map_name: str) -> tuple[dict, ...]:
    """The Map's Spots in lookup order, each with its bounding box precomputed."""
    path = SPOTS_DIR / f"{_key(map_name)}.json"
    if not path.exists():
        return ()
    out = []
    for spot in json.loads(path.read_text()).get("spots", []):
        poly = [(float(x), float(y)) for x, y in spot["poly"]]
        if len(poly) < 3:
            continue
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        z = spot.get("z")
        out.append(
            {
                "name": spot["name"],
                "callouts": frozenset(spot.get("callouts") or ()),
                "poly": poly,
                "z": (float(z[0]), float(z[1])) if z else None,
                "box": (min(xs), max(xs), min(ys), max(ys)),
            }
        )
    return tuple(out)


@lru_cache(maxsize=1)
def version() -> str:
    """Changes whenever any Spots file does, so stored Reviews rebuild."""
    digest = hashlib.sha1(usedforsecurity=False)
    for path in sorted(SPOTS_DIR.glob("*.json")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:8]


def _inside(poly: list[tuple[float, float]], x: float, y: float) -> bool:
    inside, j = False, len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def spot_at(map_name: str, x, y, z=None, place: str | None = None) -> str:
    """The Spot a point is in, else its Callout as words, else ``""``."""
    try:
        fx, fy = float(x), float(y)
    except (TypeError, ValueError):
        return callout_label(place)
    if fx != fx or fy != fy:  # NaN
        return callout_label(place)
    fz = None
    if z is not None:
        try:
            fz = float(z)
        except (TypeError, ValueError):
            fz = None
    for spot in spots(map_name):
        x0, x1, y0, y1 = spot["box"]
        if not (x0 <= fx <= x1 and y0 <= fy <= y1):
            continue
        if spot["callouts"] and place not in spot["callouts"]:
            continue
        if spot["z"] and fz is not None and not (spot["z"][0] <= fz <= spot["z"][1]):
            continue
        if _inside(spot["poly"], fx, fy):
            return spot["name"]
    return callout_label(place)


def scene(map_name: str) -> list[dict]:
    """The Spots for the Replay: name, polygon and where to print the name."""
    out = []
    for spot in spots(map_name):
        poly = spot["poly"]
        cx = sum(p[0] for p in poly) / len(poly)
        cy = sum(p[1] for p in poly) / len(poly)
        out.append(
            {
                "name": spot["name"],
                "callouts": sorted(spot["callouts"]),
                "poly": [[round(x), round(y)] for x, y in poly],
                "z": list(spot["z"]) if spot["z"] else None,
                "x": round(cx, 1),
                "y": round(cy, 1),
            }
        )
    return out
