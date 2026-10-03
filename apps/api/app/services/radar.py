"""The official radar overview as the map background, placed by coordinates.

Every map ships with a radar image and three numbers that anchor it in the
world: ``pos_x``/``pos_y`` are the world coordinate of the image's *top-left
pixel*, and ``scale`` is world units per pixel. So the transform is a division,
not a fit::

    px = (x - pos_x) / scale
    py = (pos_y - y) / scale          # world y grows up, image rows grow down

The images are static files the public app serves from ``/radars/`` (copied from
cstat's ``data/radars``); this module only knows the numbers, and hands the
page a plate: the image URL plus the world rectangle its edges sit at.

Ported from cstat's ``hltv/services/radar.py``, without its server-side plate
rendering: cstat dims, desaturates and crops the overview with numpy, where
this app's pages (replay, heatmaps, movement) draw the raw 1024 px overview and
dim it in the browser.

Maps with a second floor ship two images. Which floor a position is on comes
from ``Z`` and nothing else -- see :func:`level_at`. The callout cannot answer
it: on Nuke, Ramp is 27% lower, Secret is 56/44 and Vents is 92%.
"""

from __future__ import annotations

import math

from app.config import REPO_ROOT

# Where the public app keeps the overview PNGs it serves at /radars/<name>.png.
RADAR_DIR = REPO_ROOT / "apps" / "public" / "public" / "radars"
RADAR_PX = 1024

# Valve's overview calibration (as published by cs-demo-manager, MIT). "lower"
# marks the maps that ship a second image for their bottom floor. "split_z" is
# the altitude where the lower floor stops and the upper one begins, and it is
# deliberately absent from most of the maps that have a second image: a map with
# no verified split behaves as a single-level map. de_nuke's -495 was checked by
# cstat across nine parsed Nuke maps (the empty band between the two altitude
# clusters comes out as -635 to -425 every time).
CALIBRATION = {
    "cs_agency": {"pos_x": -2597, "pos_y": 2079, "scale": 4.1817436},
    "cs_alpine": {"pos_x": -2107, "pos_y": 4687, "scale": 6.5296063},
    "cs_assault": {"pos_x": 4041, "pos_y": 7838, "scale": 4.6},
    "cs_italy": {"pos_x": -2647, "pos_y": 2592, "scale": 4.6},
    "cs_militia": {"pos_x": -1474, "pos_y": 2296, "scale": 4.5, "lower": True},
    "cs_office": {"pos_x": -1838, "pos_y": 1858, "scale": 4.1},
    "cs_shelter": {"pos_x": -3448, "pos_y": 3805, "scale": 3.311857},
    "de_ancient": {"pos_x": -2953, "pos_y": 2164, "scale": 5},
    "de_anubis": {"pos_x": -2796, "pos_y": 3328, "scale": 5.22},
    "de_assembly": {"pos_x": 1628, "pos_y": 4512, "scale": 2.84},
    "de_aztec": {"pos_x": -3200, "pos_y": 2841, "scale": 6},
    "de_basalt": {"pos_x": -2345, "pos_y": 2391, "scale": 4.37},
    "de_boulder": {"pos_x": -3273, "pos_y": 2930, "scale": 2.8491137, "lower": True},
    "de_brewery": {"pos_x": -4122, "pos_y": 4394, "scale": 2.1820312},
    "de_cache": {"pos_x": -2000, "pos_y": 3250, "scale": 5.5},
    "de_canals": {"pos_x": -2496, "pos_y": 1792, "scale": 4},
    "de_cbble": {"pos_x": -3840, "pos_y": 3072, "scale": 6},
    "de_debris": {"pos_x": -3015, "pos_y": 2919, "scale": 1.9445695},
    "de_dogtown": {"pos_x": -1741, "pos_y": 3295, "scale": 2.0323243},
    "de_dust": {"pos_x": -2850, "pos_y": 4073, "scale": 6},
    "de_dust2": {"pos_x": -2476, "pos_y": 3239, "scale": 4.4},
    "de_edin": {"pos_x": -383, "pos_y": 4420, "scale": 4.803717},
    "de_eldorado": {"pos_x": -3548, "pos_y": 2571, "scale": 2.0656068},
    "de_fachwerk": {"pos_x": -2311, "pos_y": 2874, "scale": 2.5537856},
    "de_golden": {"pos_x": -856, "pos_y": 2399, "scale": 4.506695},
    "de_grail": {"pos_x": -4395, "pos_y": 4203, "scale": 2.1756864},
    "de_inferno": {"pos_x": -2087, "pos_y": 3870, "scale": 4.9},
    "de_jura": {"pos_x": -2126, "pos_y": 2389, "scale": 2.504188},
    "de_memento": {"pos_x": -2111, "pos_y": 2534, "scale": 3.9720395},
    "de_mills": {"pos_x": -4810, "pos_y": -320, "scale": 5.148437},
    "de_mirage": {"pos_x": -3230, "pos_y": 1713, "scale": 5},
    "de_nuke": {"pos_x": -3453, "pos_y": 2887, "scale": 7, "lower": True, "split_z": -495.0},
    "de_overpass": {"pos_x": -4831, "pos_y": 1781, "scale": 5.2},
    "de_palacio": {"pos_x": -2443, "pos_y": 1896, "scale": 3.8676212},
    "de_palais": {"pos_x": -1353, "pos_y": 2044, "scale": 2.8003397, "lower": True},
    "de_poseidon": {"pos_x": -1046, "pos_y": 1166, "scale": 3.0124886},
    "de_rooftop": {"pos_x": -1847, "pos_y": 2301, "scale": 1.914732},
    "de_sanctum": {"pos_x": -1846, "pos_y": 674, "scale": 3.658203},
    "de_stronghold": {"pos_x": -2786, "pos_y": 2598, "scale": 2.9476247},
    "de_thera": {"pos_x": -85, "pos_y": 2261, "scale": 4.846961, "lower": True},
    "de_train": {"pos_x": -2308, "pos_y": 2078, "scale": 4.082077, "lower": True},
    "de_vertigo": {"pos_x": -3168, "pos_y": 1762, "scale": 4, "lower": True},
    "de_warden": {"pos_x": -3150, "pos_y": 2681, "scale": 5.642361},
    "de_whistle": {"pos_x": -1825, "pos_y": 1104, "scale": 2.8},
}

UPPER = "upper"
LOWER = "lower"

# How far past the split a position must be before it counts as having changed
# floor. On a ramp Z sits on the boundary and flickers; cstat measured +/-35
# units bringing floor changes from 0.58 to 0.45 per player-round on Nuke while
# keeping every real change.
HYSTERESIS = 35.0


def normalise(map_name: str) -> str:
    """``mirage`` and ``de_mirage`` are the same map."""
    name = (map_name or "").strip().lower()
    if not name or name in CALIBRATION:
        return name
    for prefix in ("de_", "cs_"):
        if prefix + name in CALIBRATION:
            return prefix + name
    return name


def calibration(map_name: str) -> dict | None:
    return CALIBRATION.get(normalise(map_name))


def split_altitude(map_name: str) -> float | None:
    """The Z where this map's lower floor ends; None for one floor or an unverified split."""
    spec = calibration(map_name)
    if not spec or not spec.get("lower") or spec.get("split_z") is None:
        return None
    return float(spec["split_z"])


def levels(map_name: str) -> list[dict]:
    """``[{'key', 'image'}, ...]`` for a multi-level map, ``[]`` for a flat one."""
    if split_altitude(map_name) is None:
        return []
    name = normalise(map_name)
    return [{"key": UPPER, "image": name}, {"key": LOWER, "image": f"{name}_lower"}]


def level_at(split: float | None, z, previous: str | None = None) -> str:
    """Which floor an altitude is on, given the split. ``''`` on a flat map.

    ``previous`` is the answer for the point before, which is what makes
    :data:`HYSTERESIS` work. A position with no usable Z keeps the previous
    answer: a player without a Z is still somewhere.
    """
    if split is None:
        return ""
    try:
        value = float(z)
    except (TypeError, ValueError):
        value = math.nan
    if not math.isfinite(value):
        return previous if previous in (UPPER, LOWER) else UPPER
    if value < split - HYSTERESIS:
        return LOWER
    if value > split + HYSTERESIS:
        return UPPER
    if previous in (UPPER, LOWER):
        return previous
    return LOWER if value < split else UPPER


def image_url(image: str) -> str | None:
    """The public app's URL for an overview, or None if it isn't shipped."""
    return f"/radars/{image}.png" if (RADAR_DIR / f"{image}.png").exists() else None


def plate(map_name: str) -> dict | None:
    """The background a round is drawn over: ``{url, width, height, extent}``.

    ``extent`` is ``[x0, x1, y0, y1]`` in world units, so the page's world-to-pixel
    step is a division. ``url`` is None for a map whose overview isn't shipped:
    the replay still plays, on a plain background. None for an uncalibrated map.
    """
    spec = calibration(map_name)
    if spec is None:
        return None
    span = RADAR_PX * spec["scale"]
    return {
        "url": image_url(normalise(map_name)),
        "width": RADAR_PX,
        "height": RADAR_PX,
        "extent": [spec["pos_x"], spec["pos_x"] + span, spec["pos_y"] - span, spec["pos_y"]],
    }
