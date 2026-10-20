"""Aim, as Leetify measures it, from the Review's engagements (docs/plans/04 PL-5).

An engagement is a stretch of Sighting of a living enemy with a gun in hand and
eyes not flashed (:meth:`app.services.review._RoundReview.engagements`). Over a
Player's Match Maps with Sightings: the median time from first sight to first
damage (within a second), the median angle of the crosshair off the enemy's
head as he came into view, the share of shots fired counter-strafed (below the
weapon class's moving share of its top speed) and of first shots that hit.
Shown only past :data:`MIN_ENGAGEMENTS`, each against every Player's past it.

The Sighting is the game's own radar spotting, an approximation (docs/adr/0006);
a smoke between the two is not ruled out.
"""

from __future__ import annotations

import statistics

from app.services import review_pool

MIN_ENGAGEMENTS = 100
# Lower is better for these; higher for the shares.
LOWER_BETTER = {"ttd_ms", "xhair_deg"}


def summarise(parts: list[dict]) -> dict | None:
    """One Player's engagements over Match Maps, as the page says them."""
    if not parts:
        return None
    ttd = [v for p in parts for v in p.get("ttd") or []]
    xhair = [v for p in parts for v in p.get("xhair") or []]
    shots = sum(p.get("shots", 0) for p in parts)
    still = sum(p.get("still", 0) for p in parts)
    first = sum(p.get("first", 0) for p in parts)
    hit = sum(p.get("first_hit", 0) for p in parts)
    return {
        "engagements": sum(p.get("engagements", 0) for p in parts),
        "maps": len(parts),
        "ttd_ms": round(1000 * statistics.median(ttd)) if ttd else None,
        "xhair_deg": round(statistics.median(xhair), 1) if xhair else None,
        "counter_strafe_pct": round(100 * still / shots, 1) if shots else None,
        "first_hit_pct": round(100 * hit / first, 1) if first else None,
    }


def player(sid: str, match_map_ids: set[int] | None = None) -> dict | None:
    """``sid``'s aim over his Match Maps (those given, or all), with where each
    number stands among every Player past :data:`MIN_ENGAGEMENTS` (0-100, higher
    better)."""
    data = review_pool.data()
    mine = data.aims.get(sid) or {}
    parts = [a for mm, a in mine.items() if match_map_ids is None or mm in match_map_ids]
    out = summarise(parts)
    if out is None:
        return None
    out["enough"] = out["engagements"] >= MIN_ENGAGEMENTS
    if not out["enough"]:
        return out
    others = [summarise(list(maps.values())) for maps in data.aims.values()]
    others = [o for o in others if o and o["engagements"] >= MIN_ENGAGEMENTS]
    out["players"] = len(others)
    out["rank"] = {}
    for key in ("ttd_ms", "xhair_deg", "counter_strafe_pct", "first_hit_pct"):
        values = [o[key] for o in others if o[key] is not None]
        if out[key] is None or not values:
            continue
        if key in LOWER_BETTER:
            beaten = sum(1 for v in values if v > out[key])
        else:
            beaten = sum(1 for v in values if v < out[key])
        out["rank"][key] = round(100 * beaten / len(values))
    return out
