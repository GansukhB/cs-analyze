"""One Match Map seen from one of its Teams (v2 screen 03, the match report).

Round by Round what each side spent and how the Round ended, the score's run,
what decided it side by side (opening kills, trades, utility damage, flash
assists, AWP kills, clutches won), both scoreboards with each Player's rating,
multi-kill Rounds, clutches and utility, the record by buy, and the Rounds that
turned on a reversal of the Win probability, worded by the Review. Read from
stored rows and the stored Review only. Bind a session with ``dbctx.using``.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BuyType,
    KillEvent,
    MatchMap,
    Player,
    PlayerMap,
    PlayerMapUtility,
    PlayerRound,
    Round,
)
from app.services import player_rating, review_view
from app.services.demo_parser import TRADE_SECONDS

# How a Round ended, as the design's one letter.
END = {"ct_killed": "E", "t_killed": "E", "bomb_exploded": "B", "bomb_defused": "D",
       "time_ran_out": "T"}  # fmt: skip
# A Round turned when the Win probability went this far the other way inside it.
TURN = 0.5
TURNS = 4


def build(db: Session, match_map: MatchMap, team_id: int) -> dict:
    rounds = list(
        db.scalars(select(Round).where(Round.match_map_id == match_map.id).order_by(Round.number))
    )
    them_id = match_map.team2_id if match_map.team1_id == team_id else match_map.team1_id
    rate = match_map.tickrate or 64
    ids = [r.id for r in rounds] or [0]
    per_round = list(db.scalars(select(PlayerRound).where(PlayerRound.round_id.in_(ids))))
    kills = list(
        db.scalars(
            select(KillEvent)
            .where(KillEvent.round_id.in_(ids))
            .order_by(KillEvent.round_id, KillEvent.tick)
        )
    )
    team_of = {(pr.round_id, pr.player_id): pr.team_id for pr in per_round}
    clutch = _clutches(rounds, per_round, kills)
    trades = _trades(kills, team_of, rate)

    review = None
    try:
        review = review_view.panel(db, match_map)
    except Exception:  # the report stands without the Review's words
        review = None

    turning = _turning(review, team_id) if review else set()
    board = _board(db, match_map, team_id, them_id, per_round, kills, clutch, review)
    return {
        "halves": _halves(rounds, team_id),
        "seconds": _seconds(rounds, rate),
        "rounds": [_round(r, team_id, r.number in turning) for r in rounds],
        "factors": _factors(team_id, them_id, per_round, kills, trades, clutch, board),
        "teams": board,
        "buys": _buys(rounds, team_id),
        "turning": [t for t in _turning_lines(review, team_id) if t["n"] in turning]
        if review
        else [],
        "quick": _quick(team_id, them_id, per_round, trades, clutch, rounds),
        "reviewed": review is not None,
    }


def _side(r: Round, team_id: int) -> str | None:
    return "ct" if r.ct_team_id == team_id else "t" if r.t_team_id == team_id else None


def _round(r: Round, team_id: int, turned: bool) -> dict:
    side = _side(r, team_id)
    ours_ct = side == "ct"
    return {
        "n": r.number,
        "won": r.winner_team_id == team_id if r.winner_team_id else None,
        "side": side,
        "end": END.get(r.end_reason, "?"),
        "site": r.bomb_site,
        "ours": (r.ct_equip_value if ours_ct else r.t_equip_value),
        "theirs": (r.t_equip_value if ours_ct else r.ct_equip_value),
        "our_buy": (r.ct_buy if ours_ct else r.t_buy) or "",
        "their_buy": (r.t_buy if ours_ct else r.ct_buy) or "",
        "turning": turned,
    }


def _halves(rounds: list[Round], team_id: int) -> list[dict]:
    """Regulation halves and overtime, cut where the Sides swap."""
    out, current = [], None
    for r in rounds:
        side = _side(r, team_id)
        if current is None or side != current["side"]:
            current = {"side": side, "ours": 0, "theirs": 0}
            out.append(current)
        if r.winner_team_id:
            current["ours" if r.winner_team_id == team_id else "theirs"] += 1
    return out


def _seconds(rounds: list[Round], rate: int) -> int | None:
    if not rounds:
        return None
    return round((rounds[-1].official_end_tick - rounds[0].start_tick) / rate)


def _trades(kills: list[KillEvent], team_of: dict, rate: int) -> list[KillEvent]:
    """Kills that avenged a teammate inside the trade window (CONTEXT.md: Trade):
    the victim had killed one of the killer's team in the seconds before."""
    window = TRADE_SECONDS * rate
    out = []
    by_round: dict[int, list[KillEvent]] = defaultdict(list)
    for k in kills:
        by_round[k.round_id].append(k)
    for rid, seq in by_round.items():
        for i, k in enumerate(seq):
            if k.attacker_id is None:
                continue
            mine = team_of.get((rid, k.attacker_id))
            for prev in reversed(seq[:i]):
                if k.tick - prev.tick > window:
                    break
                if prev.attacker_id == k.victim_id and team_of.get((rid, prev.victim_id)) == mine:
                    out.append(k)
                    break
    return out


def _clutches(rounds, per_round, kills) -> dict[int, list[tuple[int, bool, int]]]:
    """player id -> [(round number, won, enemies left)]: each time a Player was
    his Team's last one alive with an enemy still standing."""
    players: dict[int, dict[int, int]] = defaultdict(dict)  # round id -> player -> team
    for pr in per_round:
        if pr.team_id:
            players[pr.round_id][pr.player_id] = pr.team_id
    by_round: dict[int, list[KillEvent]] = defaultdict(list)
    for k in kills:
        by_round[k.round_id].append(k)
    out: dict[int, list] = defaultdict(list)
    for r in rounds:
        team = players.get(r.id) or {}
        alive = {pid for pid in team}
        seen: set[int] = set()
        for k in by_round.get(r.id, []):
            alive.discard(k.victim_id)
            for tid in set(team.values()):
                mine = [p for p in alive if team[p] == tid]
                enemies = [p for p in alive if team[p] != tid]
                if len(mine) == 1 and enemies and mine[0] not in seen:
                    seen.add(mine[0])
                    out[mine[0]].append((r.number, r.winner_team_id == tid, len(enemies)))
    return out


def _board(db, match_map, team_id, them_id, per_round, kills, clutch, review) -> list[dict]:
    lines = player_rating.per_map([match_map.id])
    names = dict(
        db.execute(
            select(Player.id, Player.name).where(
                Player.id.in_([pid for (_mm, pid) in lines] or [0])
            )
        ).all()
    )
    steam = dict(
        db.execute(
            select(Player.id, Player.steamid).where(
                Player.id.in_([pid for (_mm, pid) in lines] or [0])
            )
        ).all()
    )
    util = {
        u.player_id: u
        for u in db.scalars(
            select(PlayerMapUtility).where(PlayerMapUtility.match_map_id == match_map.id)
        )
    }
    pm = {
        p.player_id: p
        for p in db.scalars(select(PlayerMap).where(PlayerMap.match_map_id == match_map.id))
    }
    multi: dict[int, int] = defaultdict(int)
    for pr in per_round:
        if pr.kills >= 2:
            multi[pr.player_id] += 1
    swing = {p["sid"]: p["swing_per_round"] for p in review["players"]} if review else {}
    out = []
    for tid in (team_id, them_id):
        if tid is None:
            continue
        rows = []
        for (_mm, pid), (line, team) in lines.items():
            if team != tid:
                continue
            u = util.get(pid)
            sid = str(steam.get(pid, ""))
            got = clutch.get(pid, [])
            rows.append(
                {
                    "steamid": sid,
                    "name": names.get(pid, "?"),
                    "kills": line.kills,
                    "deaths": line.deaths,
                    "assists": line.assists,
                    "adr": round(line.adr, 1) if line.adr is not None else None,
                    "kast": round(line.kast, 1) if line.kast is not None else None,
                    "opening_kills": pm[pid].opening_kills if pid in pm else 0,
                    "opening_deaths": pm[pid].opening_deaths if pid in pm else 0,
                    "multi": multi.get(pid, 0),
                    "clutch_won": sum(1 for _n, won, _e in got if won),
                    "clutch_of": len(got),
                    "utility_damage": (u.fire_damage + u.he_damage) if u else 0,
                    "flash_assists": u.flash_assists if u else 0,
                    "awp_kills": sum(
                        1 for k in kills if k.attacker_id == pid and k.weapon == "awp"
                    ),
                    "rating": round(line.rating, 2) if line.rating is not None else None,
                    "swing_per_round": swing.get(sid),
                }
            )
        rows.sort(key=lambda r: -(r["rating"] or 0))
        team = match_map.team1 if match_map.team1_id == tid else match_map.team2
        out.append(
            {
                "team": {"id": tid, "name": team.name if team else "?"},
                "rating": round(
                    player_rating.team_average(
                        line for (_mm, _pid), (line, t) in lines.items() if t == tid
                    )
                    or 0,
                    2,
                ),
                "players": rows,
            }
        )
    return out


def _factors(team_id, them_id, per_round, kills, trades, clutch, board) -> list[dict]:
    def by(rows, key):
        return sum(r[key] for r in rows)

    us = next((b["players"] for b in board if b["team"]["id"] == team_id), [])
    them = next((b["players"] for b in board if b["team"]["id"] == them_id), [])
    opening = defaultdict(int)
    for pr in per_round:
        if pr.opening_kill:
            opening[pr.team_id] += 1
    traded = defaultdict(int)
    team_of = {(pr.round_id, pr.player_id): pr.team_id for pr in per_round}
    for k in trades:
        traded[team_of.get((k.round_id, k.attacker_id))] += 1
    pairs = (
        ("opening", "Opening алалт", opening[team_id], opening[them_id]),
        ("trade", "Trade алалт", traded[team_id], traded[them_id]),
        ("utility_damage", "Utility damage", by(us, "utility_damage"), by(them, "utility_damage")),
        ("flash_assists", "Flash assist", by(us, "flash_assists"), by(them, "flash_assists")),
        ("awp", "AWP алалт", by(us, "awp_kills"), by(them, "awp_kills")),
        ("clutch", "Clutch хожсон", by(us, "clutch_won"), by(them, "clutch_won")),
    )
    return [{"key": k, "label": label, "us": a, "them": b} for k, label, a, b in pairs]


def _quick(team_id, them_id, per_round, trades, clutch, rounds) -> dict:
    opening = defaultdict(int)
    team_of = {(pr.round_id, pr.player_id): pr.team_id for pr in per_round}
    for pr in per_round:
        if pr.opening_kill:
            opening[pr.team_id] += 1
    traded = defaultdict(int)
    for k in trades:
        traded[team_of.get((k.round_id, k.attacker_id))] += 1
    won_by = defaultdict(int)
    of_by = defaultdict(int)
    for pid, tries in clutch.items():
        tid = next((t for (_r, p), t in team_of.items() if p == pid), None)
        won_by[tid] += sum(1 for _n, won, _e in tries if won)
        of_by[tid] += len(tries)
    plants = [r for r in rounds if r.t_team_id == team_id and r.bomb_plant_tick is not None]
    return {
        "opening": [opening[team_id], opening[them_id]],
        "trade": [traded[team_id], traded[them_id]],
        "clutch": [won_by[team_id], won_by[them_id]],
        "post_plant": [sum(1 for r in plants if r.winner_team_id == team_id), len(plants)],
    }


def _buys(rounds: list[Round], team_id: int) -> list[dict]:
    """Our record by what we bought, with the Rounds."""
    out = []
    for buy, label in (
        (BuyType.PISTOL, "Pistol"),
        (BuyType.ECO, "Eco / Save"),
        (BuyType.FORCE, "Force buy"),
        (BuyType.FULL, "Full buy"),
    ):
        mine = [
            r
            for r in rounds
            if r.winner_team_id and (r.ct_buy if _side(r, team_id) == "ct" else r.t_buy) == buy
        ]
        won = [r.number for r in mine if r.winner_team_id == team_id]
        lost = [r.number for r in mine if r.winner_team_id != team_id]
        out.append({"buy": str(buy), "label": label, "won": len(won), "of": len(mine),
                    "won_rounds": won, "lost_rounds": lost})  # fmt: skip
    return out


def _our_wp(r: dict, team_id: int) -> list[float]:
    ct = r["ct_team_id"] == team_id
    return [p[1] if ct else 1.0 - p[1] for p in r["wp"]]


def _turning(review: dict, team_id: int) -> set[int]:
    """The Rounds where the Win probability went furthest the other way: won from
    deep down, lost from well ahead."""
    scored = []
    for r in review["rounds"]:
        wp = _our_wp(r, team_id)
        if not wp or r["winner_team_id"] is None:
            continue
        won = r["winner_team_id"] == team_id
        turn = (1.0 - min(wp)) if won else max(wp)
        if turn >= TURN:
            scored.append((turn, r["n"]))
    return {n for _t, n in sorted(scored, reverse=True)[:TURNS]}


def _turning_lines(review: dict, team_id: int) -> list[dict]:
    out = []
    for r in review["rounds"]:
        wp = _our_wp(r, team_id)
        if not wp or r["winner_team_id"] is None:
            continue
        won = r["winner_team_id"] == team_id
        ours = next((t for t in r["teams"] if t["team_id"] == team_id), None)
        out.append(
            {
                "n": r["n"],
                "won": won,
                "title": ours["line"] if ours else "",
                "body": r["summary"],
                "from_wp": round(min(wp) if won else max(wp), 3),
                "to_wp": 1.0 if won else 0.0,
                "site": r["site"],
            }
        )
    return out
