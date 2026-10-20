"""One Player's page (docs/plans/04-player-analytics.md PL-2): who he played for,
his form Match Map by Match Map, his numbers by Map and Side, the Findings he
gets most against how often every Player gets them, where he stands, his guns.

Everything comes from rows cut at ingest and from the stored Reviews at the
current version (read through ``review_pool.data()``, cut once per stamp);
nothing is rebuilt here. Steam ids travel as strings: they exceed JavaScript's
safe integers.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import func, select

from app.models import (
    GameMap,
    MapRoster,
    Match,
    MatchMap,
    Player,
    PlayerAlias,
    PlayerMap,
    PlayerMapWeapon,
    PlayerRound,
    Round,
    RoundSnapshot,
    SnapshotMoment,
    Team,
)
from app.services import mn, review, review_pool
from app.services.dbctx import count_if, db, total

PER_ROUNDS = 24  # Finding rates are said per 24 Rounds, a regulation Map
SPOTS_PER_SIDE = 3
WEAPONS = 6


def _pct(part: float, whole: float) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def _ratio(part: float, whole: float, digits: int = 1) -> float | None:
    return round(part / whole, digits) if whole else None


def _line(rounds, kills, deaths, damage, kast, traded, ok, od) -> dict:
    return {
        "rounds": rounds,
        "kills": kills,
        "deaths": deaths,
        "adr": _ratio(damage, rounds),
        "kast_pct": _pct(kast, rounds),
        "opening_attempts": ok + od,
        "opening_win_pct": _pct(ok, ok + od),
        "traded_death_pct": _pct(traded, deaths),
    }


def build(steamid: int) -> dict | None:
    session = db()
    player = session.scalar(select(Player).where(Player.steamid == steamid))
    if player is None:
        return None
    sid = str(player.steamid)

    seen_as = session.scalars(select(PlayerAlias.name).where(PlayerAlias.player_id == player.id))
    aliases = sorted(set(seen_as) - {player.name})

    # -- the Match Maps he played, oldest first
    rows = session.execute(
        select(MatchMap, MapRoster.team_id, Match.played_at, GameMap.name)
        .join(MapRoster, MapRoster.match_map_id == MatchMap.id)
        .join(Match, Match.id == MatchMap.match_id)
        .outerjoin(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(MapRoster.player_id == player.id, MatchMap.parsed_at.is_not(None))
        .order_by(Match.played_at, MatchMap.map_number)
    ).all()
    team_ids = {t for _, t, _, _ in rows if t} | {
        x for mm, *_ in rows for x in (mm.team1_id, mm.team2_id) if x
    }
    names = dict(session.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids))).all())
    stats = {
        r.match_map_id: r
        for r in session.scalars(
            select(PlayerMap).where(
                PlayerMap.player_id == player.id,
                PlayerMap.match_map_id.in_([mm.id for mm, *_ in rows]),
            )
        )
    }

    # -- Swing and Findings, from the stored Reviews
    data = review_pool.data()
    swing_by_map: dict[int, list[float]] = defaultdict(list)
    mine: Counter = Counter()
    rounds_reviewed = 0
    pool_codes: Counter = Counter()
    pool_rounds = 0
    for t in data.tallies:
        seen = sum(len(v) for v in t.players.values())
        pool_rounds += seen
        for code, events in t.codes.items():
            pool_codes[code] += sum(1 for e in events if e[2])
        if sid not in t.players:
            continue
        swing_by_map[t.mm] += [s for _n, s in t.players[sid]]
        rounds_reviewed += len(t.players[sid])
        for code, events in t.codes.items():
            mine[code] += sum(1 for e in events if e[2] == sid)

    teams: dict[int, dict] = {}
    form = []
    for mm, team_id, played_at, map_name in rows:
        if team_id:
            entry = teams.setdefault(
                team_id, {"team_id": team_id, "name": names.get(team_id, "?"), "maps": 0}
            )
            entry["maps"] += 1
            entry["first"] = entry.get("first") or played_at
            entry["last"] = played_at
        opponent = mm.team2_id if mm.team1_id == team_id else mm.team1_id
        st = stats.get(mm.id)
        swings = swing_by_map.get(mm.id) or []
        form.append(
            {
                "match_id": mm.match_id,
                "map_number": mm.map_number,
                "map": map_name or "?",
                "played_at": played_at,
                "team": names.get(team_id, "?") if team_id else "",
                "opponent": names.get(opponent, "?") if opponent else "",
                "won": mm.winner_id == team_id if mm.winner_id and team_id else None,
                "rounds": st.rounds_played if st else 0,
                "kills": st.kills if st else 0,
                "deaths": st.deaths if st else 0,
                "adr": round(st.adr, 1) if st and st.adr is not None else None,
                "kast_pct": round(st.kast_pct, 1) if st and st.kast_pct is not None else None,
                "swing_per_round": round(sum(swings) / len(swings), 4) if swings else None,
            }
        )

    # -- by Map and Side, from the Round rollup
    per = session.execute(
        select(
            GameMap.name,
            PlayerRound.side,
            count_if(PlayerRound.id.is_not(None)),
            total(PlayerRound.kills),
            total(PlayerRound.deaths),
            total(PlayerRound.damage),
            count_if(PlayerRound.kast),
            count_if(PlayerRound.traded),
            count_if(PlayerRound.opening_kill),
            count_if(PlayerRound.opening_death),
        )
        .join(Round, Round.id == PlayerRound.round_id)
        .join(MatchMap, MatchMap.id == Round.match_map_id)
        .join(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(PlayerRound.player_id == player.id, PlayerRound.side.in_(("ct", "t")))
        .group_by(GameMap.name, PlayerRound.side)
    ).all()
    by_map = []
    sides: dict[str, list[int]] = defaultdict(lambda: [0] * 8)
    for map_name, side, *nums in per:
        nums = [int(v or 0) for v in nums]
        by_map.append({"map": map_name, "side": side, **_line(*nums)})
        sides[side] = [a + b for a, b in zip(sides[side], nums, strict=True)]
    by_map.sort(key=lambda r: (r["map"], r["side"]))
    totals = _line(*[a + b for a, b in zip(sides["ct"], sides["t"], strict=True)])
    all_swings = [s for v in swing_by_map.values() for s in v]
    totals["swing_per_round"] = round(sum(all_swings) / len(all_swings), 4) if all_swings else None
    totals["maps"] = len(rows)

    # -- Findings: his rate per 24 Rounds against every Player's
    findings = []
    for code, n in mine.most_common():
        if not n:
            continue
        findings.append(
            {
                "code": code,
                "kind": review.CODE_KIND.get(code, ""),
                "label": mn.REVIEW_CODE.get(code, code),
                "count": n,
                "per24": _ratio(PER_ROUNDS * n, rounds_reviewed, 2),
                "pool_per24": _ratio(PER_ROUNDS * pool_codes[code], pool_rounds, 2),
            }
        )

    # -- where he stands 20 s in (the Setup), per Map and Side
    spots_rows = session.execute(
        select(GameMap.name, RoundSnapshot.side, RoundSnapshot.place, func.count(RoundSnapshot.id))
        .join(Round, Round.id == RoundSnapshot.round_id)
        .join(MatchMap, MatchMap.id == Round.match_map_id)
        .join(GameMap, GameMap.id == MatchMap.game_map_id)
        .where(
            RoundSnapshot.player_id == player.id,
            RoundSnapshot.moment == SnapshotMoment.SETUP,
            RoundSnapshot.place != "",
        )
        .group_by(GameMap.name, RoundSnapshot.side, RoundSnapshot.place)
    ).all()
    grouped: dict[tuple, list] = defaultdict(list)
    for map_name, side, place, n in spots_rows:
        grouped[(map_name, side)].append((place, int(n)))
    spots = []
    for (map_name, side), places in sorted(grouped.items()):
        seen = sum(n for _, n in places)
        for place, n in sorted(places, key=lambda p: -p[1])[:SPOTS_PER_SIDE]:
            spots.append(
                {
                    "map": map_name,
                    "side": side,
                    "place": place,
                    "rounds": n,
                    "share": _pct(n, seen),
                }
            )

    # -- his guns
    guns = session.execute(
        select(PlayerMapWeapon.weapon, total(PlayerMapWeapon.kills))
        .where(PlayerMapWeapon.player_id == player.id)
        .group_by(PlayerMapWeapon.weapon)
    ).all()
    kills = sum(int(k or 0) for _, k in guns)
    weapons = [
        {"weapon": w, "kills": int(k or 0), "share": _pct(int(k or 0), kills)}
        for w, k in sorted(guns, key=lambda g: -int(g[1] or 0))[:WEAPONS]
        if int(k or 0)
    ]

    return {
        "player": {"steamid": sid, "name": player.name, "aliases": aliases},
        "teams": sorted(teams.values(), key=lambda t: t["last"] or 0, reverse=True),
        "totals": totals,
        "sides": {side: _line(*nums) for side, nums in sorted(sides.items())},
        "maps": by_map,
        "form": form,
        "findings": findings,
        "rounds_reviewed": rounds_reviewed,
        "spots": spots,
        "weapons": weapons,
    }
