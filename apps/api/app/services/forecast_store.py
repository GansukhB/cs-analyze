"""Forecasts kept and graded (CONTEXT.md: Forecast; docs/plans/03 FC-4).

:func:`record` writes a Forecast as :mod:`app.services.forecast` made it, with
its model version, and never changes it. :func:`grade` finds each ungraded
Forecast's series once it is played (a Match we hold, else a series Valve
counted) and adds the result, its log loss and Brier; one not played within
:data:`GRADE_WINDOW_DAYS` is closed as expired. :func:`summary` is how the
Forecasts did, against a coin, so a coach can see how far to trust the next one.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Forecast, GameMap, Match, MatchMap, Player, SeriesResult, Team, User
from app.models.base import utcnow
from app.services import dbctx, forecast, stats

GRADE_WINDOW_DAYS = 30


def record(
    db: Session,
    user: User,
    mine: Team,
    theirs: Team,
    my_five: Sequence[Player],
    their_five: Sequence[Player],
    fmt: str,
) -> Forecast:
    """Make the Fixture's Forecast now and keep it. ValueError when a Team is unrated."""
    with dbctx.using(db):
        out = forecast.build(
            mine,
            theirs,
            my_lineup=[p.name for p in my_five] or None,
            their_lineup=[p.name for p in their_five] or None,
        )
    p = (out["series"].get(fmt) or {}).get("expected")
    if p is None:
        raise ValueError("unrated")
    row = Forecast(
        workspace_id=user.workspace_id,
        kind="request",
        created_by_id=user.id,
        my_team_id=mine.id,
        opponent_id=theirs.id,
        my_lineup=[str(p.steamid) for p in my_five],
        their_lineup=[str(p.steamid) for p in their_five],
        format=fmt,
        model_version=out["model"],
        outputs=json.loads(json.dumps(out, default=str)),
        p_series=p,
    )
    db.add(row)
    db.commit()
    return row


def _loss(p: float, won: bool) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(p if won else 1 - p)


def _from_match(db: Session, f: Forecast) -> dict | None:
    match = db.scalars(
        select(Match)
        .where(
            or_(
                (Match.team1_id == f.my_team_id) & (Match.team2_id == f.opponent_id),
                (Match.team1_id == f.opponent_id) & (Match.team2_id == f.my_team_id),
            ),
            Match.played_at >= f.created_at,
            Match.team1_score.is_not(None),
            Match.team2_score.is_not(None),
        )
        .order_by(Match.played_at)
    ).first()
    if match is None:
        return None
    mine_first = match.team1_id == f.my_team_id
    ours, theirs = (
        (match.team1_score, match.team2_score)
        if mine_first
        else (match.team2_score, match.team1_score)
    )
    if ours == theirs:
        return None
    chance = {m["map"]: m["p"] for m in f.outputs.get("maps") or []}
    maps = [
        {"map": name, "won": winner == f.my_team_id, "p": chance.get(name)}
        for name, winner in db.execute(
            select(GameMap.name, MatchMap.winner_id)
            .join(GameMap, GameMap.id == MatchMap.game_map_id)
            .where(MatchMap.match_id == match.id, MatchMap.winner_id.is_not(None))
            .order_by(MatchMap.map_number)
        )
    ]
    return {
        "won": ours > theirs,
        "score": f"{ours}-{theirs}",
        "source": "match",
        "match_id": match.id,
        "played_on": match.played_at.date().isoformat(),
        "maps": maps,
    }


def _from_series(db: Session, f: Forecast) -> dict | None:
    ratings = f.outputs.get("ratings") or {}
    a, b = (ratings.get("mine") or {}).get("name"), (ratings.get("theirs") or {}).get("name")
    if not (a and b):
        return None
    first, second = sorted((a, b), key=str.casefold)
    found = db.scalars(
        select(SeriesResult)
        .where(
            SeriesResult.team_a == first,
            SeriesResult.team_b == second,
            SeriesResult.played_on >= f.created_at.date(),
        )
        .order_by(SeriesResult.played_on, SeriesResult.id)
    ).first()
    if found is None:
        return None
    return {
        "won": found.a_won == (found.team_a == a),
        "score": "",
        "source": "vrs",
        "played_on": found.played_on.isoformat(),
        "maps": [],
    }


def grade(db: Session, now: datetime | None = None) -> int:
    """Grade every Forecast whose series has been played. Returns how many."""
    now = now or utcnow()
    done = 0
    for f in db.scalars(select(Forecast).where(Forecast.graded_at.is_(None))):
        result = _from_match(db, f) or _from_series(db, f)
        if result is None:
            if now - f.created_at > timedelta(days=GRADE_WINDOW_DAYS):
                f.graded_at, f.result = now, {"expired": True}
            continue
        f.result = result
        f.match_id = result.get("match_id")
        f.log_loss = round(_loss(f.p_series, result["won"]), 4)
        f.brier = round((f.p_series - (1.0 if result["won"] else 0.0)) ** 2, 4)
        f.graded_at = now
        done += 1
    db.commit()
    return done


def summary(rows: Sequence[Forecast]) -> dict:
    """How the graded Forecasts did: log loss and Brier against a coin, how many
    favourites won, and the same for every Map played."""
    graded = [f for f in rows if f.log_loss is not None]
    maps = [
        (m["p"], m["won"])
        for f in graded
        for m in (f.result or {}).get("maps") or []
        if m.get("p") is not None
    ]
    out = {
        "made": len(rows),
        "graded": len(graded),
        "expired": sum(1 for f in rows if (f.result or {}).get("expired")),
        "coin_log_loss": round(math.log(2), 4),
        "log_loss": None,
        "brier": None,
        "favourites_won": None,
        "maps": len(maps),
        "map_log_loss": None,
    }
    if graded:
        out["log_loss"] = round(sum(f.log_loss for f in graded) / len(graded), 4)
        out["brier"] = round(sum(f.brier for f in graded) / len(graded), 4)
        called = [f for f in graded if f.p_series != 0.5]
        out["favourites_won"] = sum((f.p_series > 0.5) == bool(f.result["won"]) for f in called)
    if maps:
        out["map_log_loss"] = round(sum(_loss(p, won) for p, won in maps) / len(maps), 4)
    out["reliability"] = reliability([(f.p_series, bool(f.result["won"])) for f in graded])
    return out


# FC-4: our chance of the series in the bands the Forecast's words use.
BANDS = ((0.0, 0.35), (0.35, 0.45), (0.45, 0.55), (0.55, 0.65), (0.65, 1.0001))


def reliability(calls: Sequence[tuple[float, bool]]) -> list[dict]:
    """Per band of our chance: how many series, how many we won, and that share's
    80% range. A model whose 60% calls come true about 60% of the time is
    calibrated; with few series the ranges say how little that shows."""
    out = []
    for lo, hi in BANDS:
        inside = [(p, won) for p, won in calls if lo <= p < hi]
        if not inside:
            continue
        won = sum(1 for _p, w in inside if w)
        low, high = stats.wilson(won, len(inside))
        out.append({
            "lo": lo, "hi": min(hi, 1.0), "n": len(inside), "won": won,
            "mean_p": round(sum(p for p, _w in inside) / len(inside), 3),
            "low": round(low, 3), "high": round(high, 3),
        })  # fmt: skip
    return out
