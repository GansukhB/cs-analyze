"""The Playbook's Levers and Cautions (CONTEXT.md) for one Map of a Fixture.

Both Teams' Strengths and Weaknesses (:mod:`app.services.review_pool`) are set
against each other on the Sides that face each other: my CT against their T, my
T against their CT. Where my Strength meets their Weakness in a pair of
:data:`PAIRS`, that Lever comes first; where their Strength meets my Weakness,
that Caution does. The rest follow by weight: the Rounds per half the number is
worth against a Pool-typical Team. Above the two columns go the limits of the
data: the maps tab's cautions (:func:`app.services.gameplan.map_plan`), Reviews
still being rebuilt, Match Maps without Sightings or without Teams.

Structured here; :func:`app.services.mn.advice` words each entry.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models import Player, Team
from app.services import gameplan, mapstrategy, review_pool, spots
from app.services.dbctx import db, memo

SIDES = ("ct", "t")
OTHER = {"ct": "t", "t": "ct"}
# (mine, theirs) on facing Sides: a Lever when my first is a Strength and their
# second a Weakness; read from their side, a Caution when theirs is a Strength
# and mine a Weakness.
PAIRS = (
    ("opening", "opening"),
    ("trade", "trade"),
    ("entry", "trade"),
    ("pistol", "pistol"),
    ("full_v_full", "full_v_full"),
    ("force", "full_v_light"),
    ("eco", "full_v_light"),
    ("post_plant", "retake"),
    ("retake", "post_plant"),
    ("post_plant", "kitless"),
    ("post_plant", "defuse_chance"),
    ("fire_delay", "time_out"),
    ("clutch", "died_in_advantage"),
    ("clutch", "advantage_lost"),
    ("comeback", "died_in_advantage"),
    ("comeback", "advantage_lost"),
)
# A lone line falls away when the other Team's side of its pair says otherwise
# this far (z): their weak post-plant is no Lever while our retake is weak too.
COUNTERED_Z = 0.4
# Player lines per column: the threats may take two, the rest one each.
PLAYER_LINES = {("caution", "theirs"): 2}
# A lone line worth less than this (Rounds per half) is left out: true, but not
# what a plan is made of.
MIN_WEIGHT = 0.03


def _entry(role: str, side: str, mine: dict | None, theirs: dict | None) -> dict:
    return {
        "role": role,
        "side": side,
        "pair": mine is not None and theirs is not None,
        "mine": mine,
        "theirs": theirs,
        "weight": round(sum(x["weight"] for x in (mine, theirs) if x), 3),
    }


# A line read across all Maps ranks as if worth this share of its weight: on a
# Map's own Playbook, what that Map showed comes first.
ALL_MAPS_RANK = 0.75


def _order(entry: dict) -> tuple:
    lines = [x for x in (entry["mine"], entry["theirs"]) if x]
    here = any(x.get("scope") == "map" for x in lines)
    return (not entry["pair"], -entry["weight"] * (1.0 if here else ALL_MAPS_RANK))


def order(entry: dict) -> tuple:
    """The rank of a Lever or Caution among others: strongest first."""
    return _order(entry)


def identity(entry: dict) -> tuple:
    """What a line says, whichever Map it is on: its role and the numbers behind it."""
    return (
        entry["role"],
        *((x["key"], x["side"], x.get("sid", "")) if x else None
          for x in (entry["mine"], entry["theirs"])),
    )  # fmt: skip


def _countered(x: dict, whose: str, my_team: Team, opponent: Team, map_name: str) -> bool:
    """Whether the facing Team's half of a pair takes this lone line away.

    Their Weakness is no Lever when we are weak at what would use it; my
    Strength is none when they are strong at what answers it; their Strength is
    no Caution when we are strong at the answer. My Weakness always stays.
    """
    if whose == "mine" and not x["good"]:
        return False
    facing = OTHER[x["side"]]
    for a, b in PAIRS:
        if whose == "theirs" and not x["good"] and x["key"] == b:
            z = review_pool.score(my_team, a, map_name, facing)
            if z is not None and z <= -COUNTERED_Z:
                return True
        if whose == "mine" and x["good"] and x["key"] == a:
            z = review_pool.score(opponent, b, map_name, facing)
            if z is not None and z >= COUNTERED_Z:
                return True
        if whose == "theirs" and x["good"] and x["key"] == a:
            z = review_pool.score(my_team, b, map_name, facing)
            if z is not None and z >= COUNTERED_Z:
                return True
    return False


def _few_players(entries: list[dict], role: str) -> list[dict]:
    """Keep the strongest Player lines only: a column is about the Map, not a roster."""
    seen: dict[str, int] = {}
    out = []
    for e in entries:
        x = e["mine"] or e["theirs"]
        if x["kind"] == "player" and not e["pair"]:
            whose = "mine" if e["mine"] else "theirs"
            seen[whose] = seen.get(whose, 0) + 1
            if seen[whose] > PLAYER_LINES.get((role, whose), 1):
                continue
        out.append(e)
    return out


def build(my_team: Team, opponent: Team, map_name: str) -> dict:
    """``{"columns": {side: {"levers", "cautions"}}, "limits"}`` for one Map;
    a column is my Side."""

    def compute():
        h2h = {m.id for m in mapstrategy.maps_in_window(my_team, opponent=opponent)}
        mine = review_pool.team_lines(my_team, map_name, h2h) + review_pool.player_lines(
            my_team, map_name, h2h
        )
        theirs = review_pool.team_lines(opponent, map_name, h2h) + review_pool.player_lines(
            opponent, map_name, h2h
        )
        taken: set[int] = set()

        def find(lines, key, side, good):
            return next(
                (
                    x
                    for x in lines
                    if x["key"] == key
                    and x["side"] == side
                    and x["good"] == good
                    and id(x) not in taken
                ),
                None,
            )

        columns = {side: {"levers": [], "cautions": []} for side in SIDES}
        for side in SIDES:
            other = OTHER[side]
            for a, b in PAIRS:
                strong, weak = find(mine, a, side, True), find(theirs, b, other, False)
                if strong and weak:
                    taken |= {id(strong), id(weak)}
                    columns[side]["levers"].append(_entry("lever", side, strong, weak))
                strong, weak = find(theirs, a, other, True), find(mine, b, side, False)
                if strong and weak:
                    taken |= {id(strong), id(weak)}
                    columns[side]["cautions"].append(_entry("caution", side, weak, strong))
        for x in mine:
            if x["weight"] < MIN_WEIGHT or id(x) in taken:
                continue
            if _countered(x, "mine", my_team, opponent, map_name):
                continue
            role = "lever" if x["good"] else "caution"
            columns[x["side"]][f"{role}s"].append(_entry(role, x["side"], x, None))
        for x in theirs:
            if x["weight"] < MIN_WEIGHT or id(x) in taken:
                continue
            if _countered(x, "theirs", my_team, opponent, map_name):
                continue
            side = OTHER[x["side"]]
            role = "caution" if x["good"] else "lever"
            columns[side][f"{role}s"].append(_entry(role, side, None, x))
        for column in columns.values():
            for role in ("levers", "cautions"):
                column[role] = _few_players(sorted(column[role], key=_order), role[:-1])
        return {"columns": columns, "limits": limits(my_team, opponent, map_name)}

    return memo(("levers", my_team.id, opponent.id, map_name), compute)


def top(built: dict, said: set | None = None) -> tuple[dict | None, dict | None]:
    """The Map's first Lever and first Caution, whichever Side they are on,
    passing over what ``said`` (:func:`identity`) already holds from another Map."""
    best = {}
    for role in ("levers", "cautions"):
        entries = [e for column in built["columns"].values() for e in column[role]]
        entries = [e for e in sorted(entries, key=_order) if identity(e) not in (said or set())]
        best[role] = entries[0] if entries else None
    return best["levers"], best["cautions"]


def limits(my_team: Team, opponent: Team, map_name: str) -> list[dict]:
    """What the Map's Levers and Cautions cannot see, as Cautions of their own."""
    out = []
    plan = gameplan.map_plan(my_team, opponent, map_name)
    out += (plan or {}).get("cautions") or []
    state = review_pool.state([my_team, opponent])
    for team, whose in ((my_team, "mine"), (opponent, "theirs")):
        s = state[team.id]
        if s["waiting"]:
            out.append({"kind": "reviews_waiting", "whose": whose, "team": team.name,
                        "n": s["waiting"], "of": s["maps"]})  # fmt: skip
        if s["untagged"]:
            out.append({"kind": "untagged", "whose": whose, "team": team.name,
                        "n": s["untagged"]})  # fmt: skip
    reviewed = sum(state[t.id]["reviewed"] for t in (my_team, opponent))
    sighted = sum(state[t.id]["sightings"] for t in (my_team, opponent))
    if reviewed and sighted < reviewed:
        out.append({"kind": "few_sightings", "n": sighted, "of": reviewed})
    return out


def lineups(my_team: Team, opponent: Team) -> list[Player]:
    """Both Lineups' Players."""
    from app.services import lineup

    ids = lineup.fielded(my_team) | lineup.fielded(opponent)
    return list(db().scalars(select(Player).where(Player.id.in_(list(ids))))) if ids else []


# ------------------------------------------------------- habit lines' notes ---
def annotate(habits: list[dict], team: Team, map_name: str) -> list[dict]:
    """Add the Review's word to habits it can be tied to exactly: the same
    Player on the same Side, or Findings whose Spot is inside the habit's Callout."""
    ids = {h["player_id"] for h in habits if h.get("player_id")}
    steam = {}
    if ids:
        rows = db().execute(select(Player.id, Player.steamid).where(Player.id.in_(list(ids))))
        steam = dict(rows.all())
    for h in habits:
        side = h.get("side")
        if side not in SIDES:
            continue
        note = None
        if h.get("player_id") in steam:
            note = review_pool.player_note(team, str(steam[h["player_id"]]), map_name, side)
            if note:
                note = {"kind": "player", "player": h.get("player"), **note}
        elif h.get("place"):
            place = h["place"]
            found = review_pool.place_note(
                team, map_name, side, lambda spot, p=place: spots.in_callout(map_name, spot, p)
            )
            if found:
                note = {"kind": "place", "place": place, **found}
        if note:
            h["review"] = note
    return habits
