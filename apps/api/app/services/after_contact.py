"""What a Team does after the first contact on a Map (docs/plans/05 TM-7).

The Round's opening (its first kill) is placed by where the victim fell
(``playbook.lean``: A, mid or B), and each Round then goes one of three ways:
the bomb goes down at A, at B, or not at all. On T that is the decision tree
"after the opening at A, do they go in or rotate"; on CT, "after losing B,
does B fall, or do they hold it". Two more trees come from positions:

* T: where most of them stood at the Setup (20 s), then where they planted;
  a plant on the other site is a rotate;
* CT, having lost the opening at a site: did another CT reach that site in
  the next :data:`REINFORCE_SECONDS` (the Round search's tokens), the stack.

After the plant: where the T stood at it, per site, and how the CT's retakes
went by the numbers left (ahead, even, behind). Plants after
:data:`LATE_PLANT` seconds are the late executes.
"""

from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict

from sqlalchemy import func, select

from app.models import (
    GameMap,
    KillEvent,
    MatchMap,
    ReplayRound,
    Round,
    RoundSnapshot,
    SnapshotMoment,
)
from app.services import playbook
from app.services.dbctx import db, memo

LATE_PLANT = 60.0
REINFORCE_SECONDS = 10
MAX_REFS = 8
TOP_PLACES = 4
WHERE = ("A", "mid", "B")
THEN = ("A", "B", "none")


def _rows(team_id: int, map_name: str) -> list:
    return list(
        db().execute(
            select(
                Round.id, Round.match_map_id, Round.number, Round.freeze_end_tick,
                Round.bomb_plant_tick, Round.bomb_site, Round.winner_team_id,
                Round.ct_team_id, Round.t_team_id, MatchMap.tickrate, MatchMap.match_id,
                MatchMap.map_number,
            )
            .join(MatchMap, MatchMap.id == Round.match_map_id)
            .join(GameMap, GameMap.id == MatchMap.game_map_id)
            .where(
                GameMap.name == map_name, MatchMap.parsed_at.is_not(None),
                (Round.ct_team_id == team_id) | (Round.t_team_id == team_id),
            )
            .order_by(MatchMap.id.desc(), Round.number)
        )
    )  # fmt: skip


def _openings(ids: list[int]) -> dict[int, tuple]:
    """``{round: (tick, attacker_side, (x, y, z) of the victim)}``."""
    first = (
        select(KillEvent.round_id, func.min(KillEvent.tick).label("tick"))
        .where(KillEvent.round_id.in_(ids))
        .group_by(KillEvent.round_id)
        .subquery()
    )
    out = {}
    for rid, tick, side, x, y, z in db().execute(
        select(
            KillEvent.round_id, KillEvent.tick, KillEvent.attacker_side,
            KillEvent.victim_x, KillEvent.victim_y, KillEvent.victim_z,
        ).join(first, (first.c.round_id == KillEvent.round_id) & (first.c.tick == KillEvent.tick))
    ):  # fmt: skip
        out.setdefault(rid, (tick, side, (x, y, z)))
    return out


def _snapshots(ids: list[int]) -> dict[str, dict[int, list]]:
    """``{moment: {round: [(side, place, (x, y, z))]}}``."""
    out: dict[str, dict[int, list]] = {m.value: defaultdict(list) for m in SnapshotMoment}
    for rid, moment, side, place, x, y, z in db().execute(
        select(
            RoundSnapshot.round_id, RoundSnapshot.moment, RoundSnapshot.side,
            RoundSnapshot.place, RoundSnapshot.x, RoundSnapshot.y, RoundSnapshot.z,
        ).where(RoundSnapshot.round_id.in_(ids))
    ):  # fmt: skip
        out[moment][rid].append((side, place, (x, y, z)))
    return out


def place_leans(map_name: str) -> dict[str, str]:
    """Each Callout's lean (A, mid or B), from where the deaths in it fell."""

    def compute():
        sites = playbook.site_centroids(map_name)
        rows = db().execute(
            select(
                KillEvent.victim_place, func.avg(KillEvent.victim_x),
                func.avg(KillEvent.victim_y), func.avg(KillEvent.victim_z),
            )
            .join(Round, Round.id == KillEvent.round_id)
            .join(MatchMap, MatchMap.id == Round.match_map_id)
            .join(GameMap, GameMap.id == MatchMap.game_map_id)
            .where(
                GameMap.name == map_name, KillEvent.victim_place != "",
                KillEvent.victim_x.is_not(None),
            )
            .group_by(KillEvent.victim_place)
        )  # fmt: skip
        return {
            place: playbook.lean((float(x), float(y), float(z or 0)), sites)
            for place, x, y, z in rows
        }

    return memo(("ac_leans", map_name), compute)


def _tokens(rows: list) -> dict[tuple[int, int], dict]:
    keys = {(r.match_map_id, r.number) for r in rows}
    out = {}
    for mm, number, blob in db().execute(
        select(ReplayRound.match_map_id, ReplayRound.number, ReplayRound.tokens).where(
            ReplayRound.match_map_id.in_({k[0] for k in keys}), ReplayRound.tokens.is_not(None)
        )
    ):
        if (mm, number) in keys:
            out[(mm, number)] = json.loads(gzip.decompress(blob))
    return out


def _at(tokens: dict, side: str, second: int, places: set[str]) -> int:
    idx = {i for i, name in enumerate(tokens["places"]) if name in places}
    return sum(n for s, i, n in tokens[side] if s == second and i in idx)


def _node() -> dict:
    return {"n": 0, "won": 0, "then": {k: {"n": 0, "won": 0, "refs": []} for k in THEN}}


def _add(node: dict, then: str, won: bool, ref: dict) -> None:
    node["n"] += 1
    node["won"] += won
    branch = node["then"][then]
    branch["n"] += 1
    branch["won"] += won
    if len(branch["refs"]) < MAX_REFS:
        branch["refs"].append(ref)


def _out(key: dict, node: dict) -> dict:
    return {**key, "n": node["n"], "wins": node["won"],
            "then": [{"then": k, **node["then"][k]} for k in THEN]}  # fmt: skip


def _situation(ct: int, t: int) -> str:
    return "ahead" if ct > t else "even" if ct == t else "behind"


def team(team_id: int, map_name: str) -> dict:
    rows = _rows(team_id, map_name)
    ids = [r.id for r in rows]
    openings = _openings(ids) if ids else {}
    snaps = _snapshots(ids) if ids else {m.value: {} for m in SnapshotMoment}
    sites = playbook.site_centroids(map_name)
    leans = place_leans(map_name)
    toward = {w: {p for p, lean in leans.items() if lean == w} for w in ("A", "B")}
    tokens = _tokens(rows) if ids else {}

    t_open: dict[tuple, dict] = defaultdict(_node)
    t_setup: dict[str, dict] = defaultdict(_node)
    ct_open: dict[tuple, dict] = defaultdict(_node)
    reinforced: Counter = Counter()
    looked: Counter = Counter()
    plants = {"n": 0, "late": 0, "late_won": 0, "seconds": []}
    post: dict[str, Counter] = {"A": Counter(), "B": Counter()}
    post_rounds: Counter = Counter()
    retakes: dict[tuple, dict] = {}
    counts = {"t": 0, "ct": 0}
    for r in rows:
        side = "ct" if r.ct_team_id == team_id else "t"
        counts[side] += 1
        won = r.winner_team_id == team_id
        rate = r.tickrate or 64
        ref = {"match": r.match_id, "map": r.map_number, "round": r.number}
        planted = r.bomb_plant_tick is not None and r.bomb_site in ("A", "B")
        then = r.bomb_site if planted else "none"
        first = openings.get(r.id)
        where = playbook.lean(first[2], sites) if first and None not in first[2] else ""
        at_plant = snaps[SnapshotMoment.PLANT.value].get(r.id, [])
        if side == "t":
            if first and where:
                _add(t_open[(first[1] == "t", where)], then, won, ref)
            # Where most of them stood at the Setup.
            stood = Counter(
                playbook.lean(pos, sites)
                for s, _p, pos in snaps[SnapshotMoment.SETUP.value].get(r.id, [])
                if s == "t" and None not in pos
            )
            heavy = max(("A", "B"), key=lambda w: stood[w])
            if stood[heavy] >= 3:
                _add(t_setup[heavy], then, won, ref)
            if planted:
                secs = (r.bomb_plant_tick - r.freeze_end_tick) / rate
                plants["n"] += 1
                plants["seconds"].append(secs)
                if secs > LATE_PLANT:
                    plants["late"] += 1
                    plants["late_won"] += won
                places = {p for s, p, _pos in at_plant if s == "t" and p}
                post_rounds[r.bomb_site] += 1
                post[r.bomb_site].update(places)
        else:
            if first and where:
                _add(ct_open[(first[1] == "ct", where)], then, won, ref)
                # Lost the opening at a site: did another CT get there?
                tk = tokens.get((r.match_map_id, r.number))
                if first[1] == "t" and where in toward and tk:
                    # Counted from the second after the death, so it is not one of them.
                    s0 = int((first[0] - r.freeze_end_tick) / rate) + 1
                    base = _at(tk, "ct", s0, toward[where])
                    after = max(_at(tk, "ct", s0 + d, toward[where])
                                for d in range(1, REINFORCE_SECONDS + 1))  # fmt: skip
                    looked[where] += 1
                    reinforced[where] += after > base
            if planted and at_plant:
                alive = Counter(s for s, _p, _pos in at_plant)
                key = (r.bomb_site, _situation(alive["ct"], alive["t"]))
                cell = retakes.setdefault(key, {"n": 0, "won": 0, "refs": []})
                cell["n"] += 1
                cell["won"] += won
                if len(cell["refs"]) < MAX_REFS:
                    cell["refs"].append(ref)

    seconds = sorted(plants["seconds"])
    median = seconds[len(seconds) // 2] if seconds else None
    return {
        "map": map_name,
        "t": {
            "rounds": counts["t"],
            "openings": [
                _out({"won": got, "where": w}, t_open[(got, w)])
                for got in (True, False) for w in WHERE if t_open[(got, w)]["n"]
            ],
            "setups": [_out({"won": None, "where": w}, t_setup[w]) for w in ("A", "B")
                       if t_setup[w]["n"]],
            "plants": plants["n"],
            "plant_median": round(median, 1) if median is not None else None,
            "late": plants["late"],
            "late_won": plants["late_won"],
            "post_plant": [
                {"site": s, "rounds": post_rounds[s],
                 "places": [[p, n] for p, n in post[s].most_common(TOP_PLACES)]}
                for s in ("A", "B") if post_rounds[s]
            ],
        },
        "ct": {
            "rounds": counts["ct"],
            "openings": [
                {**_out({"won": got, "where": w}, ct_open[(got, w)]),
                 "looked": looked[w] if not got else 0,
                 "reinforced": reinforced[w] if not got else 0}
                for got in (False, True) for w in WHERE if ct_open[(got, w)]["n"]
            ],
            "retakes": [
                {"site": s, "situation": sit, **retakes[(s, sit)]}
                for s in ("A", "B") for sit in ("ahead", "even", "behind") if (s, sit) in retakes
            ],
        },
    }  # fmt: skip
