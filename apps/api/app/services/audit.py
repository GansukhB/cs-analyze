"""A Match Map's timeout audit and every Player's opening duels (docs/plans/07 RV-8).

Timeouts are read off the game rules (schema 14, DATA-5): each one with the
Rounds its Team had lost in a row before it, and whether the Round after was
won against the Win probability its buys gave it. A Team that lost
:data:`STREAK` in a row with a timeout left and no break is marked as having
gone without one. Research puts a break after a 3+ Round streak at 11.7-13
points on the next Round (Gómez Seeber 2024); :func:`pool` measures it on the
Match Maps here, for the page to say beside it.

Opening duels count each Player's first kills and first deaths of a Round, how
often a first death was traded, and what his Team made of the 5v4 or the 4v5.
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from app.models import MatchMap, Player, PlayerRound, Round, Team
from app.services import review
from app.services.dbctx import db

STREAK = 3
TACTICAL = 3  # tactical timeouts a Team has in regulation, as the demos count them
REGULATION = 24
# Rounds that start after a break anyway: each half's first, then each overtime half's.
HALF_STARTS = {1, 13}
OT_HALF = 3


def _break_before(number: int) -> bool:
    return number in HALF_STARTS or (
        number > REGULATION and (number - REGULATION - 1) % OT_HALF == 0
    )


def _starts(match_map: MatchMap) -> dict[int, float]:
    """Round number -> CT's Win probability as it went live, from the stored Review."""
    stored = review.ensure(db(), match_map) if match_map.is_parsed else None
    out = {}
    for r in (stored or {}).get("rounds") or []:
        if r.get("wp"):
            out[r["n"]] = float(r["wp"][0][1])
    return out


def _walk(rounds: list[Round]):
    """Each Round with, per Team, the Rounds it had lost in a row coming into it,
    the timeouts it had used, and who called one in its freeze time."""
    streak: Counter = Counter()
    used: Counter = Counter()
    for r in rounds:
        if _break_before(r.number):
            streak.clear()
        sides = ((r.ct_team_id, "ct", r.ct_timeout), (r.t_team_id, "t", r.t_timeout))
        called = [(team, side) for team, side, flag in sides if flag and team]
        yield r, dict(streak), dict(used), called
        for team, _side in called:
            used[team] += 1
        if called or r.tech_timeout:
            streak.clear()  # a break is a break, whoever called it
        for team in (r.ct_team_id, r.t_team_id):
            if team is None:
                continue
            streak[team] = 0 if r.winner_team_id == team else streak[team] + 1


def map_audit(match_map: MatchMap) -> dict:
    session = db()
    rounds = list(
        session.scalars(
            select(Round).where(Round.match_map_id == match_map.id).order_by(Round.number)
        )
    )
    known = bool(rounds) and all(r.ct_timeout is not None for r in rounds)
    team_ids = {t for r in rounds for t in (r.ct_team_id, r.t_team_id) if t}
    names = dict(session.execute(select(Team.id, Team.name).where(Team.id.in_(team_ids))).all())
    timeouts, missed = [], []
    if known:
        starts = _starts(match_map)
        for r, streak, used, called in _walk(rounds):
            ct_start = starts.get(r.number)
            for team, side in called:
                timeouts.append(
                    {
                        "round": r.number,
                        "team_id": team,
                        "team": names.get(team, ""),
                        "side": side,
                        "lost_before": streak.get(team, 0),
                        "won_next": r.winner_team_id == team,
                        "expected": None if ct_start is None
                        else round(ct_start if side == "ct" else 1 - ct_start, 3),
                    }
                )  # fmt: skip
            if called or r.tech_timeout or _break_before(r.number) or r.number > REGULATION:
                continue
            for team in (r.ct_team_id, r.t_team_id):
                if team and streak.get(team, 0) == STREAK and used.get(team, 0) < TACTICAL:
                    missed.append(
                        {
                            "round": r.number,
                            "team_id": team,
                            "team": names.get(team, ""),
                            "lost_before": STREAK,
                            "won_next": r.winner_team_id == team,
                            "left": TACTICAL - used.get(team, 0),
                        }
                    )
    return {
        "known": known,
        "timeouts": timeouts,
        "missed": missed,
        "openings": openings([match_map.id]),
    }


def pool() -> dict:
    """The Round after a :data:`STREAK`+ losing run, with a break called by the
    losing Team and without any, over every Match Map whose timeouts are known."""
    session = db()
    rows = session.scalars(
        select(Round)
        .where(Round.ct_timeout.is_not(None))
        .order_by(Round.match_map_id, Round.number)
    ).all()
    by_map: dict[int, list[Round]] = {}
    for r in rows:
        by_map.setdefault(r.match_map_id, []).append(r)
    out = {"after_timeout": [0, 0], "without": [0, 0]}
    for rounds in by_map.values():
        for r, streak, _used, called in _walk(rounds):
            if _break_before(r.number):
                continue
            callers = {t for t, _s in called}
            for team in (r.ct_team_id, r.t_team_id):
                if not team or streak.get(team, 0) < STREAK:
                    continue
                if team in callers:
                    key = "after_timeout"
                elif called or r.tech_timeout:
                    continue  # the other Team's break
                else:
                    key = "without"
                out[key][0] += 1
                out[key][1] += int(r.winner_team_id == team)
    return {
        "maps": len(by_map),
        **{
            key: {"rounds": n, "won": won, "pct": round(100 * won / n, 1) if n else None}
            for key, (n, won) in out.items()
        },
    }


def openings(match_map_ids: list[int], player_id: int | None = None) -> list[dict]:
    """Per Player: opening duels taken and won, his first deaths traded, and what
    his Team made of the Round after each (5v4 won, 4v5 won)."""
    if not match_map_ids:
        return []
    query = (
        select(
            PlayerRound.player_id,
            PlayerRound.team_id,
            PlayerRound.opening_kill,
            PlayerRound.opening_death,
            PlayerRound.traded,
            Round.winner_team_id,
        )
        .join(Round, Round.id == PlayerRound.round_id)
        .where(
            Round.match_map_id.in_(match_map_ids),
            PlayerRound.opening_kill | PlayerRound.opening_death,
        )
    )
    if player_id is not None:
        query = query.where(PlayerRound.player_id == player_id)
    tally: dict[int, Counter] = {}
    teams: dict[int, Counter] = {}
    for pid, team, kill, death, traded, winner in db().execute(query):
        c = tally.setdefault(pid, Counter())
        teams.setdefault(pid, Counter())[team] += 1
        won = team is not None and winner == team
        if kill:
            c["won"] += 1
            c["after_kill_won"] += int(won)
        if death:
            c["lost"] += 1
            c["traded"] += int(bool(traded))
            c["after_death_won"] += int(won)
    players = {p.id: p for p in db().scalars(select(Player).where(Player.id.in_(list(tally))))}
    team_names = dict(
        db()
        .execute(
            select(Team.id, Team.name).where(
                Team.id.in_({t for c in teams.values() for t in c if t})
            )
        )
        .all()
    )

    def pct(n: int, of: int) -> float | None:
        return round(100 * n / of, 1) if of else None

    out = []
    for pid, c in tally.items():
        player = players.get(pid)
        team = teams[pid].most_common(1)[0][0]
        attempts = c["won"] + c["lost"]
        out.append(
            {
                "sid": str(player.steamid) if player else "",
                "name": player.name if player else "?",
                "team_id": team,
                "team": team_names.get(team, ""),
                "attempts": attempts,
                "won": c["won"],
                "won_pct": pct(c["won"], attempts),
                "traded": c["traded"],
                "traded_pct": pct(c["traded"], c["lost"]),
                "after_kill_won_pct": pct(c["after_kill_won"], c["won"]),
                "after_death_won_pct": pct(c["after_death_won"], c["lost"]),
            }
        )
    return sorted(out, key=lambda r: (r["team"], -r["attempts"]))
