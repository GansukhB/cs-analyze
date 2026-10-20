"""Writing a :class:`~app.services.demo_parser.ParsedMap` into the analysis models.

The ORM half of parsing, kept apart from awpy the same way ``store.py`` is kept
apart from Playwright: this module never imports awpy, so storage logic can be
exercised with hand-built frames and no demo on disk.

Ingesting a map is one transaction and is idempotent -- an existing ``MatchMap``
for the same ``(match, map_number)`` is deleted first, and the database cascade
takes its rounds, events and rollups with it. Re-parsing therefore converges
instead of doubling.

Ported from cstat's ``hltv/services/analysis_store.py``. The hazard notes
(H1-H11) refer to cstat's ``plans/ANALYZE.md``. Event and rollup rows are
inserted as plain dicts (Core ``insert``) because a map is thousands of them.
"""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping

import polars as pl
from sqlalchemy import case, delete, func, insert, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    BombEvent,
    BuyType,
    DamageEvent,
    Demo,
    GameMap,
    GrenadeThrow,
    KillEvent,
    MapRoster,
    Match,
    MatchMap,
    Player,
    PlayerAlias,
    PlayerMap,
    PlayerMapDuel,
    PlayerMapPosition,
    PlayerMapRoute,
    PlayerMapUtility,
    PlayerMapWeapon,
    PlayerMatch,
    PlayerRound,
    PositionKind,
    Round,
    RoundSnapshot,
    SnapshotMoment,
    Team,
    TeamAlias,
    TickDataset,
)
from app.models.base import utcnow
from app.services import teamnames, tickdata

logger = logging.getLogger(__name__)

# Bump whenever the ingest starts recording something new. Maps stored under an
# older version are re-parsed automatically, which is how a new metric reaches
# matches that were parsed before it existed. 10 was cstat's last; 11 added the
# economy, which old Tick Data lacks, so those maps are downloaded again
# (docs/adr/0003); 12 added the Replay's Loadout to the Tick Data, the same way
# (docs/adr/0005). 13 added Sightings and aim to the Tick Data, which only a Demo
# gives; unlike 11 and 12 a map without them is not downloaded again, so a map at
# 13 re-parsed from older Tick Data still has none (docs/adr/0006). 14 adds the
# timeouts, the scoreboard's per-round numbers and each grenade's throw (DATA-5),
# the same way: from older Tick Data they stay None.
CURRENT_SCHEMA_VERSION = 14

# A Setup (CONTEXT.md) is where everyone stands this long after freeze end.
SETUP_SECONDS = 20
# How far back a snapshot may reach for a player's last recorded tick.
SNAPSHOT_TOLERANCE_TICKS = 32

# Buy type (CONTEXT.md), from a side's summed equipment value as the round goes
# live. Only regulation halves open on a pistol: overtime starts everyone on $10,000.
PISTOL_ROUNDS = (1, 13)
ECO_BELOW = 5_000
FULL_FROM = 20_000

# Every gun that is not a pistol, as the demo's inventory names it, so knives
# (named per skin), pistols, grenades, C4 and the Zeus are never a primary.
PRIMARY_WEAPONS = frozenset({
    "AK-47", "M4A4", "M4A1-S", "AWP", "Galil AR", "FAMAS", "SSG 08", "SG 553", "AUG",
    "G3SG1", "SCAR-20", "MAC-10", "MP9", "MP7", "MP5-SD", "UMP-45", "P90", "PP-Bizon",
    "Nova", "XM1014", "MAG-7", "Sawed-Off", "M249", "Negev",
})  # fmt: skip

SMALL_MAX = 32767

# Pretty names for the maps in circulation; anything unknown keeps its raw name.
_MAP_LABELS = {
    "de_ancient": "Ancient",
    "de_anubis": "Anubis",
    "de_cache": "Cache",
    "de_dust2": "Dust II",
    "de_inferno": "Inferno",
    "de_mirage": "Mirage",
    "de_nuke": "Nuke",
    "de_overpass": "Overpass",
    "de_train": "Train",
    "de_vertigo": "Vertigo",
    "de_cbble": "Cobblestone",
    "de_tuscan": "Tuscan",
}


# -- small normalisers ------------------------------------------------------
def normalise_site(value) -> str:
    """``bombsite_b``/``BombsiteB``/``B`` all mean B (H5)."""
    text = str(value or "").strip().lower()
    if not text or "not_planted" in text:
        return ""
    if text.endswith("a"):
        return "A"
    if text.endswith("b"):
        return "B"
    return ""


def normalise_hitgroup(value) -> str:
    """awpy emits a literal ``-1`` alongside the real hitgroups (H4)."""
    text = str(value or "").strip()
    return "" if text in ("-1", "None") else text[:16]


def _side(value) -> str:
    text = str(value or "").strip().lower()
    return text if text in ("ct", "t") else ""


def _int(value) -> int | None:
    return None if value is None else int(value)


def buy_type(number: int, equip_value: int | None) -> str:
    """The Buy type of one side's round, or ``""`` when its economy is unknown."""
    if number in PISTOL_ROUNDS:
        return BuyType.PISTOL
    if equip_value is None:
        return ""
    if equip_value < ECO_BELOW:
        return BuyType.ECO
    return BuyType.FORCE if equip_value < FULL_FROM else BuyType.FULL


def primary_weapon(inventory) -> str:
    return next((item for item in inventory or () if item in PRIMARY_WEAPONS), "")


def normalise_team_name(value: str) -> str:
    """Reduce a team name to the part both sources agree on (``Team Vitality`` → ``vitality``)."""
    return teamnames.core(value)


def _rounds_of(match_map: MatchMap):
    return select(Round.id).where(Round.match_map_id == match_map.id)


# -- identity ---------------------------------------------------------------
def get_or_create_player(db: Session, steamid: int, name: str) -> Player:
    """One row per steamid, with every name it has been seen under recorded."""
    now = utcnow()
    player = db.scalar(select(Player).where(Player.steamid == int(steamid)))
    if player is None:
        player = Player(steamid=int(steamid), name=name or str(steamid), first_seen=now)
        db.add(player)
    elif name and player.name != name:
        player.name = name
    player.last_seen = now
    db.flush()
    if name:
        alias = db.scalar(
            select(PlayerAlias).where(PlayerAlias.player_id == player.id, PlayerAlias.name == name)
        )
        if alias is None:
            db.add(PlayerAlias(player_id=player.id, name=name, first_seen=now, last_seen=now))
        else:
            alias.last_seen = now
        db.flush()
    return player


def resolve_team(db: Session, clan_name: str, match: Match) -> Team | None:
    """Map a server-side clan name onto an HLTV team.

    Tried in order: an explicit :class:`TeamAlias`; a team already on this match
    whose name matches; any team with that name; then every team, scored. A match
    found by name is written back as an alias, so the lookup is a single indexed
    hit next time and a wrong guess can be corrected in one row.
    """
    clan = (clan_name or "").strip()
    if not clan:
        return None

    alias = db.scalar(
        select(TeamAlias)
        .options(joinedload(TeamAlias.team))
        .where(func.lower(TeamAlias.clan_name) == clan.lower())
    )
    if alias:
        return alias.team

    # The two teams on this match are the strongest candidates -- we already know
    # who played, so a loose name match cannot stray to an unrelated club.
    found = teamnames.resolve(clan, [t for t in (match.team1, match.team2) if t is not None])
    team = found[0] if found else None
    if team is None:
        team = db.scalar(
            select(Team).where(func.lower(Team.name) == clan.lower()).order_by(Team.hltv_id)
        )
    if team is None:
        # Widen to every known team. Still scored rather than string-equal, but
        # a loose match against the whole table has no roster to sanity-check.
        found = teamnames.resolve(clan, db.scalars(select(Team)).all())
        team = found[0] if found else None

    if team is not None:
        if db.scalar(select(TeamAlias.id).where(TeamAlias.clan_name == clan)) is None:
            db.add(TeamAlias(clan_name=clan, team_id=team.id, note="auto-matched on name"))
            db.flush()
        if team.name.casefold() != clan.casefold():
            logger.info("clan name %r resolved to team %r", clan, team.name)
    else:
        logger.info("no team matches clan name %r on match %s", clan, match.hltv_id)
    return team


def get_or_create_game_map(db: Session, map_name: str) -> GameMap | None:
    name = (map_name or "").strip()
    if not name:
        return None
    game_map = db.scalar(select(GameMap).where(GameMap.name == name))
    if game_map is None:
        game_map = GameMap(name=name, display_name=_MAP_LABELS.get(name, ""))
        db.add(game_map)
        db.flush()
    return game_map


# -- the ingest -------------------------------------------------------------
def ingest_map(
    db: Session,
    demo: Demo,
    parsed,
    *,
    bundle: bytes | None = None,
    on_step: Callable[[str], None] | None = None,
    sides: Mapping[int, int] | None = None,
) -> MatchMap:
    """Store one parsed map, in one transaction. Replaces any previous analysis of it.

    ``sides`` (Steam id -> Team id) says outright whose each Player is, before any
    clan name: an uploaded Scrim's Demo rarely carries one (DATA-1's "who is who").

    ``bundle`` is the map's Tick Data (:func:`app.services.tickdata.pack`, or the
    stored bundle a re-parse was read from). It is stored with the rows, and the
    Replay, walks and geometry are cut from it before the commit.

    ``on_step(key)`` is called before each pass, if given; the keys let a caller
    say which pass is running without this module knowing how it is worded.
    The caller's own commits (job progress) must use a different session, or
    they would commit half an ingest.
    """
    step = on_step or (lambda _key: None)
    try:
        match = demo.match
        map_number = demo.map_number or 1

        # Idempotency: drop the old analysis wholesale; ON DELETE CASCADE takes the rest.
        db.execute(
            delete(MatchMap).where(MatchMap.match_id == match.id, MatchMap.map_number == map_number)
        )
        db.expire_all()
        # A re-parse from stored Tick Data loaded that row; the cascade just deleted it.
        for stale in [o for o in db.identity_map.values() if isinstance(o, TickDataset)]:
            db.expunge(stale)

        match_map = MatchMap(
            match_id=match.id,
            demo_id=demo.id,
            game_map=get_or_create_game_map(db, parsed.map_name),
            map_number=map_number,
            tickrate=parsed.tickrate,
            n_rounds=parsed.n_rounds,
            parsed_at=utcnow(),
            awpy_version=parsed.awpy_version,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
        db.add(match_map)
        db.flush()

        step("roster")
        players, teams, player_teams = _ingest_roster(db, match_map, parsed, match, sides)
        step("rounds")
        rounds = _ingest_rounds(db, match_map, parsed, teams, player_teams)
        step("events")
        _ingest_events(db, parsed, rounds, players)
        step("player_rounds")
        _ingest_player_rounds(db, match_map, parsed, rounds, players, player_teams)
        step("snapshots")
        _ingest_snapshots(db, parsed, rounds, players)
        step("breakdown")
        _ingest_player_breakdown(db, match_map)
        step("routes")
        _ingest_player_routes(db, match_map, parsed)
        step("duels")
        _ingest_player_duels(db, match_map)
        step("scores")
        _finalise_scores(db, match_map, rounds)
        if bundle is not None:
            step("tickdata")
            tickdata.store(db, match_map, bundle, awpy_version=parsed.awpy_version)
        step("player_match")
        rebuild_player_match(db, match)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return match_map


def _team_from_roster_history(db: Session, player: Player, match: Match) -> Team | None:
    """A player's team when the demo gives ``resolve_team`` nothing to go on.

    Some lower-tier demos carry an empty ``team_clan_name`` on every tick. HLTV
    still names the two teams on the match, so a player's own history answers
    which of them he belongs to -- but only when that history points at exactly
    one of *this* match's two teams; a tie or no history stays unresolved.
    """
    candidate_ids = {match.team1_id, match.team2_id} - {None}
    if not candidate_ids:
        return None
    seen = set(
        db.scalars(
            select(MapRoster.team_id)
            .where(MapRoster.player_id == player.id, MapRoster.team_id.in_(candidate_ids))
            .distinct()
        )
    )
    return db.get(Team, seen.pop()) if len(seen) == 1 else None


def _ingest_roster(
    db: Session, match_map: MatchMap, parsed, match: Match, sides: Mapping[int, int] | None = None
):
    """Players, their team for this map, and their rounds-per-side denominators."""
    given = {sid: db.get(Team, team_id) for sid, team_id in (sides or {}).items()}
    totals: dict[int, dict[str, int]] = {}
    if parsed.round_totals is not None and not parsed.round_totals.is_empty():
        for row in parsed.round_totals.to_dicts():
            totals.setdefault(int(row["steamid"]), {})[str(row["side"])] = int(row["n_rounds"])

    players: dict[int, Player] = {}
    teams: dict[str, Team | None] = {}
    player_teams: dict[int, Team | None] = {}
    roster_rows = []
    for row in parsed.roster.to_dicts():
        steamid = int(row["steamid"])
        player = get_or_create_player(db, steamid, row.get("name") or "")
        players[steamid] = player

        clan = (row.get("clan_name") or "").strip()
        if clan not in teams:
            # Sides given outright: no clan-name guess, and no alias written from one.
            teams[clan] = None if given else resolve_team(db, clan, match)
        team = given.get(steamid) or teams[clan] or _team_from_roster_history(db, player, match)
        player_teams[steamid] = team

        counts = totals.get(steamid, {})
        roster_rows.append(
            {
                "match_map_id": match_map.id,
                "player_id": player.id,
                "team_id": team.id if team else None,
                "clan_name": clan[:64],
                "display_name": (row.get("name") or "")[:64],
                "rounds_ct": counts.get("ct", 0),
                "rounds_t": counts.get("t", 0),
                "rounds_total": counts.get("all", 0) or parsed.n_rounds,
            }
        )
    if roster_rows:
        db.execute(insert(MapRoster), roster_rows)

    named = list(dict.fromkeys(t for t in player_teams.values() if t is not None))
    if named:
        team1 = match.team1 if match.team1 in named else named[0]
        others = [t for t in named if t != team1]
        match_map.team1_id = team1.id
        match_map.team2_id = others[0].id if others else None
        db.flush()
    return players, teams, player_teams


def _plant_sites(parsed) -> dict[int, str]:
    """The bombsite of each round's plant, taken from the bomb feed (H11).

    awpy's ``rounds.bomb_site`` reads ``bombsite_b`` for every planted round; the
    ``bomb`` table is right. Keyed by tick, because a plant recorded after the
    round ended is a post-round plant and not part of the round at all.
    """
    by_round: dict[int, list] = defaultdict(list)
    for row in parsed.bomb.to_dicts():
        if str(row.get("event") or "") != "plant":
            continue
        number = _int(row.get("round_num"))
        tick = _int(row.get("tick"))
        site = normalise_site(row.get("bombsite"))
        if number is not None and tick is not None and site:
            by_round[number].append((tick, site))

    out: dict[int, str] = {}
    for row in parsed.rounds.to_dicts():
        number = _int(row.get("round_num"))
        plant_tick = _int(row.get("bomb_plant"))
        if number is None or plant_tick is None:
            continue
        plants = by_round.get(number) or []
        exact = next((site for tick, site in plants if tick == plant_tick), None)
        if exact is None and plants:
            exact = min(plants, key=lambda p: abs(p[0] - plant_tick))[1]
        if exact:
            out[number] = exact
    return out


def _round_side_teams(parsed, player_teams: dict[int, Team | None]) -> dict[int, tuple]:
    """Per-round (ct_team, t_team) from who stood on which side, by majority.

    The fallback for when ``round_sides``' clan-name lookup has nothing to go on.
    """
    tally: dict[tuple, Counter] = defaultdict(Counter)
    for row in parsed.player_sides.to_dicts():
        team = player_teams.get(int(row["steamid"]))
        if team is not None:
            tally[(int(row["round_num"]), str(row["side"]))][team] += 1
    out: dict[int, tuple] = {}
    for number in {n for n, _ in tally}:
        ct = tally.get((number, "ct"))
        t = tally.get((number, "t"))
        out[number] = (
            ct.most_common(1)[0][0] if ct else None,
            t.most_common(1)[0][0] if t else None,
        )
    return out


def _table(parsed, name: str) -> pl.DataFrame:
    """One of the parse's optional tables, empty where it has none (schema 13+)."""
    frame = getattr(parsed, name, None)
    return frame if frame is not None else pl.DataFrame()


def _id(team: Team | None) -> int | None:
    return team.id if team is not None else None


def _ingest_rounds(
    db: Session, match_map: MatchMap, parsed, teams, player_teams: dict[int, Team | None]
) -> dict[int, Round]:
    sides = {int(r["round_num"]): r for r in parsed.round_sides.to_dicts()}
    plant_sites = _plant_sites(parsed)
    side_teams = _round_side_teams(parsed, player_teams)
    equipment = _side_equipment(parsed)
    timeouts = {int(r["round_num"]): r for r in _table(parsed, "timeouts").to_dicts()}
    known = bool(timeouts)
    rows = []
    for row in parsed.rounds.to_dicts():
        number = int(row["round_num"])
        mapping = sides.get(number, {})
        fallback_ct, fallback_t = side_teams.get(number, (None, None))
        ct_team = teams.get((mapping.get("ct_clan") or "").strip()) or fallback_ct
        t_team = teams.get((mapping.get("t_clan") or "").strip()) or fallback_t
        winner_side = _side(row.get("winner"))
        winner = ct_team if winner_side == "ct" else (t_team if winner_side == "t" else None)
        rows.append(
            {
                "match_map_id": match_map.id,
                "number": number,
                "start_tick": max(0, _int(row["start"]) or 0),
                "freeze_end_tick": max(0, _int(row["freeze_end"]) or 0),
                "end_tick": max(0, _int(row["end"]) or 0),
                "official_end_tick": max(0, _int(row["official_end"]) or 0),
                "winner_side": winner_side,
                "winner_team_id": _id(winner),
                "ct_team_id": _id(ct_team),
                "t_team_id": _id(t_team),
                "end_reason": str(row.get("reason") or "")[:24],
                "bomb_plant_tick": _int(row.get("bomb_plant")),
                # Never row["bomb_site"] -- see _plant_sites (H11).
                "bomb_site": plant_sites.get(number, ""),
                "ct_equip_value": equipment.get((number, "ct")),
                "t_equip_value": equipment.get((number, "t")),
                "ct_buy": buy_type(number, equipment.get((number, "ct"))) if equipment else "",
                "t_buy": buy_type(number, equipment.get((number, "t"))) if equipment else "",
                "ct_timeout": bool(timeouts.get(number, {}).get("ct")) if known else None,
                "t_timeout": bool(timeouts.get(number, {}).get("t")) if known else None,
                "tech_timeout": bool(timeouts.get(number, {}).get("technical")) if known else None,
            }
        )
    if rows:
        db.execute(insert(Round), rows)
    return {
        r.number: r for r in db.scalars(select(Round).where(Round.match_map_id == match_map.id))
    }


def _grenade_throw_rows(
    frame: pl.DataFrame | None, kind: str, rounds: dict[int, Round], player_for, seen: set
) -> list[dict]:
    """``GrenadeThrow`` rows for one grenade kind, skipping anything already in ``seen``.

    ``entity_id`` repeats across rounds, so the de-dup key is ``(round, id, type)``
    (H2). Smoke/inferno carry a start/end pair (the effect's lifetime); flash/HE
    detonations are a single moment, so only ``throw_tick`` is set.
    """
    rows = []
    if frame is None or frame.is_empty():
        return rows
    for g in frame.to_dicts():
        rnd = rounds.get(int(g["round_num"]))
        if rnd is None:
            continue
        key = (rnd.id, int(g["entity_id"]), kind)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "round_id": rnd.id,
                "entity_id": int(g["entity_id"]),
                "type": kind,
                "thrower_id": player_for(g.get("thrower_steamid")),
                "thrower_side": _side(g.get("thrower_side")),
                "throw_tick": _int(g.get("tick")),
                "start_tick": _int(g.get("start_tick")),
                "end_tick": _int(g.get("end_tick")),
                "thrower_x": g.get("thrower_X"),
                "thrower_y": g.get("thrower_Y"),
                "thrower_z": g.get("thrower_Z"),
                "x": g.get("X"),
                "y": g.get("Y"),
                "z": g.get("Z"),
                "thrower_place": str(g.get("thrower_place") or "")[:24],
                # Filled by _attach_throws where the throw is found (schema 14).
                "thrown_tick": None,
                "thrown_x": None,
                "thrown_y": None,
                "thrown_z": None,
                "thrown_pitch": None,
                "thrown_yaw": None,
                "thrown_place": "",
                "_steamid": _int(g.get("thrower_steamid")),
                "_number": int(g["round_num"]),
            }
        )
    return rows


# A grenade's throw is at most this long before it took effect.
THROW_REACH_SECONDS = 15
# How near a pitch sample must be to the throw: grenade_thrown's own, else aim's.
PITCH_TICKS = {"throws": 2, "aim": 8}


def _attach_throws(grenades: list[dict], parsed) -> list[dict]:
    """Each grenade's throw (schema 14): the same player's latest unmatched
    projectile of that kind in that round, no later than it took effect, and where
    the thrower stood and looked then. Fills ``thrown_*``; returns the grenades
    it found a throw for."""
    from app.services import demo_parser

    starts = demo_parser.projectile_starts(getattr(parsed, "grenades", None))
    if starts.is_empty() or not grenades:
        return []
    pending: dict[tuple, list[dict]] = {}
    for t in starts.to_dicts():
        pending.setdefault((t["round_num"], int(t["steamid"]), t["kind"]), []).append(t)
    reach = THROW_REACH_SECONDS * parsed.tickrate
    matched = []
    effect = sorted(
        (g for g in grenades if g["_steamid"] is not None),
        key=lambda g: g["start_tick"] or g["throw_tick"] or 0,
    )
    for g in effect:
        at = g["start_tick"] or g["throw_tick"]
        queue = pending.get((g["_number"], g["_steamid"], g["type"]))
        if at is None or not queue:
            continue
        earlier = [t for t in queue if at - reach <= t["tick"] <= at]
        if not earlier:
            continue
        throw = earlier[-1]
        queue.remove(throw)
        g["thrown_tick"] = int(throw["tick"])
        matched.append(g)
    if not matched:
        return []

    # Where each thrower stood and faced then, from the every-tick positions.
    want = pl.DataFrame(
        {"i": range(len(matched)), "steamid": [g["_steamid"] for g in matched],
         "tick": [g["thrown_tick"] for g in matched]},
        schema={"i": pl.Int64, "steamid": pl.UInt64, "tick": pl.Int64},
    )  # fmt: skip
    ticks = parsed.ticks.select(
        pl.col("steamid").cast(pl.UInt64),
        pl.col("tick").cast(pl.Int64),
        pl.col("X").cast(pl.Float64),
        pl.col("Y").cast(pl.Float64),
        pl.col("Z").cast(pl.Float64),
        (pl.col("yaw").cast(pl.Float64) if "yaw" in parsed.ticks.columns else pl.lit(None)).alias(
            "yaw"
        ),
        # The thrower's own Callout there: the lineup's spot.
        (pl.col("place") if "place" in parsed.ticks.columns else pl.lit("")).alias("place"),
    )
    stood = want.join(ticks, on=["steamid", "tick"], how="left").sort("i")
    pitch = pl.Series("pitch", [None] * len(matched), dtype=pl.Float64)
    for name, tolerance in PITCH_TICKS.items():
        frame = getattr(parsed, name, None)
        if frame is None or frame.is_empty() or "pitch" not in frame.columns:
            continue
        near = (
            want.sort("tick")
            .join_asof(
                frame.select(
                    pl.col("steamid").cast(pl.UInt64),
                    pl.col("tick").cast(pl.Int64),
                    pl.col("pitch").cast(pl.Float64),
                ).sort("tick"),
                on="tick",
                by="steamid",
                strategy="nearest",
                tolerance=tolerance,
                check_sortedness=False,  # sorted by tick; polars can't check within ``by``
            )
            .sort("i")["pitch"]
        )
        pitch = pitch.fill_null(near)
    for g, row, p in zip(matched, stood.iter_rows(named=True), pitch, strict=True):
        g.update(thrown_x=row["X"], thrown_y=row["Y"], thrown_z=row["Z"], thrown_yaw=row["yaw"],
                 thrown_pitch=p, thrown_place=(row["place"] or "")[:24])  # fmt: skip
    return matched


def _ingest_events(db: Session, parsed, rounds: dict[int, Round], players: dict[int, Player]):
    def player_for(value) -> int | None:
        player = players.get(int(value)) if value is not None else None
        return player.id if player is not None else None

    kills = []
    for k in parsed.kills.to_dicts():
        rnd = rounds.get(int(k["round_num"]))
        victim = player_for(k.get("victim_steamid"))
        if rnd is None or victim is None:
            continue
        kills.append(
            {
                "round_id": rnd.id,
                "tick": max(0, _int(k["tick"]) or 0),
                "attacker_id": player_for(k.get("attacker_steamid")),  # nullable by design (H3)
                "victim_id": victim,
                "assister_id": player_for(k.get("assister_steamid")),
                "attacker_side": _side(k.get("attacker_side")),
                "victim_side": _side(k.get("victim_side")),
                "weapon": str(k.get("weapon") or "")[:32],
                "hitgroup": normalise_hitgroup(k.get("hitgroup")),
                "headshot": bool(k.get("headshot")),
                "distance": k.get("distance"),
                "dmg_health": _int(k.get("dmg_health")) or 0,
                "dmg_armor": _int(k.get("dmg_armor")) or 0,
                "penetrated": _int(k.get("penetrated")) or 0,
                "thrusmoke": bool(k.get("thrusmoke")),
                "noscope": bool(k.get("noscope")),
                "attackerblind": bool(k.get("attackerblind")),
                "attackerinair": bool(k.get("attackerinair")),
                "assistedflash": bool(k.get("assistedflash")),
                "attacker_x": k.get("attacker_X"),
                "attacker_y": k.get("attacker_Y"),
                "attacker_z": k.get("attacker_Z"),
                "victim_x": k.get("victim_X"),
                "victim_y": k.get("victim_Y"),
                "victim_z": k.get("victim_Z"),
                "attacker_place": str(k.get("attacker_place") or "")[:24],
                "victim_place": str(k.get("victim_place") or "")[:24],
                "attacker_health": k.get("attacker_health"),
                "victim_health": _int(k.get("victim_health")),
            }
        )
    if kills:
        db.execute(insert(KillEvent), kills)

    damages = []
    for d in parsed.damages.to_dicts():
        rnd = rounds.get(int(d["round_num"]))
        victim = player_for(d.get("victim_steamid"))
        if rnd is None or victim is None:
            continue
        damages.append(
            {
                "round_id": rnd.id,
                "tick": max(0, _int(d["tick"]) or 0),
                "attacker_id": player_for(d.get("attacker_steamid")),
                "victim_id": victim,
                "attacker_side": _side(d.get("attacker_side")),
                "victim_side": _side(d.get("victim_side")),
                "weapon": str(d.get("weapon") or "")[:32],
                "hitgroup": normalise_hitgroup(d.get("hitgroup")),
                # dmg_health_real is capped at what the victim could absorb (H6).
                "damage": max(0, _int(d.get("dmg_health_real")) or 0),
                "damage_raw": max(0, _int(d.get("dmg_health")) or 0),
                "damage_armor": max(0, _int(d.get("dmg_armor")) or 0),
                "victim_health_before": _int(d.get("victim_health")),
                "victim_health_after": _int(d.get("health")),
                "attacker_place": str(d.get("attacker_place") or "")[:24],
                "victim_place": str(d.get("victim_place") or "")[:24],
            }
        )
    if damages:
        db.execute(insert(DamageEvent), damages)

    bombs = []
    for b in parsed.bomb.to_dicts():
        rnd = rounds.get(int(b["round_num"]))
        if rnd is None:
            continue
        bombs.append(
            {
                "round_id": rnd.id,
                "tick": max(0, _int(b["tick"]) or 0),
                "event": str(b.get("event") or "")[:12],
                "player_id": player_for(b.get("steamid")),
                "bombsite": normalise_site(b.get("bombsite")),
                "x": b.get("X"),
                "y": b.get("Y"),
                "z": b.get("Z"),
            }
        )
    if bombs:
        db.execute(insert(BombEvent), bombs)

    # smokes/infernos/flashes/he_grenades all share the GrenadeThrow model.
    grenades: list[dict] = []
    seen: set = set()
    for kind, frame in (
        ("smoke", parsed.smokes),
        ("inferno", parsed.infernos),
        ("flash", parsed.flashes),
        ("he", parsed.he_grenades),
    ):
        grenades += _grenade_throw_rows(frame, kind, rounds, player_for, seen)
    if grenades:
        _attach_throws(grenades, parsed)
        cells = tickdata.callout_cells(parsed.ticks)
        places = tickdata.callouts_at(cells, [(g["x"], g["y"], g["z"]) for g in grenades])
        for grenade, place in zip(grenades, places, strict=True):
            grenade["place"] = place[:24]
        db.execute(
            insert(GrenadeThrow),
            [{k: v for k, v in g.items() if not k.startswith("_")} for g in grenades],
        )


def _ingest_snapshots(db: Session, parsed, rounds: dict[int, Round], players: dict[int, Player]):
    """Where every living player stood at each round's Setup and at its plant."""
    moments = []
    for number, rnd in rounds.items():
        setup = rnd.freeze_end_tick + SETUP_SECONDS * parsed.tickrate
        if setup <= rnd.end_tick:
            moments.append((number, SnapshotMoment.SETUP, setup))
        if rnd.bomb_plant_tick:
            moments.append((number, SnapshotMoment.PLANT, rnd.bomb_plant_tick))
    ticks = parsed.ticks
    if not moments or ticks is None or ticks.is_empty():
        return
    wanted = pl.DataFrame(
        {
            "round_num": [m[0] for m in moments],
            "moment": [str(m[1]) for m in moments],
            "tick": [m[2] for m in moments],
        },
        schema={"round_num": pl.Int64, "moment": pl.String, "tick": pl.Int64},
    ).sort("tick")
    seen = ticks.select(
        pl.col("round_num").cast(pl.Int64),
        pl.col("tick").cast(pl.Int64),
        pl.col("steamid").cast(pl.UInt64),
        "side",
        "place",
        "X",
        "Y",
        "Z",
        "health",
    ).filter(pl.col("round_num").is_in(list(rounds)))
    # Each player's last tick at or before the moment, per round.
    spots = (
        wanted.join(seen.select("round_num", "steamid").unique(), on="round_num")
        .sort("tick")
        .join_asof(
            seen.sort("tick"),
            on="tick",
            by=["round_num", "steamid"],
            strategy="backward",
            tolerance=SNAPSHOT_TOLERANCE_TICKS,
            check_sortedness=False,  # both sides are sorted by tick just above
        )
        .filter(pl.col("health") > 0)
    )
    rows = []
    for r in spots.to_dicts():
        player = players.get(int(r["steamid"]))
        if player is None:
            continue
        rows.append(
            {
                "round_id": rounds[int(r["round_num"])].id,
                "player_id": player.id,
                "moment": r["moment"],
                "side": _side(r["side"]),
                "place": str(r["place"] or "")[:24],
                "x": r["X"],
                "y": r["Y"],
                "z": r["Z"],
            }
        )
    if rows:
        db.execute(insert(RoundSnapshot), rows)


def _player_economy(parsed) -> dict[tuple[int, int], dict]:
    """``{(round_num, steamid): row}`` of :data:`demo_parser.ECONOMY_PROPS` as read."""
    economy = getattr(parsed, "economy", None)
    if economy is None or economy.is_empty():
        return {}
    return {(int(r["round_num"]), int(r["steamid"])): r for r in economy.to_dicts()}


def _side_equipment(parsed) -> dict[tuple[int, str], int]:
    """``{(round_num, side): summed equipment value}`` of the players on each side."""
    economy = getattr(parsed, "economy", None)
    if economy is None or economy.is_empty():
        return {}
    sides = parsed.player_sides.with_columns(
        pl.col("round_num").cast(pl.Int64), pl.col("steamid").cast(pl.UInt64)
    )
    totals = (
        economy.join(sides, on=["round_num", "steamid"])
        .group_by(["round_num", "side"])
        .agg(pl.col("equip_value").sum())
    )
    return {
        (int(r["round_num"]), _side(r["side"])): int(r["equip_value"] or 0)
        for r in totals.to_dicts()
        if _side(r["side"])
    }


def _ingest_player_rounds(
    db: Session,
    match_map: MatchMap,
    parsed,
    rounds: dict[int, Round],
    players: dict[int, Player],
    player_teams: dict[int, Team | None],
):
    """Per-round facts, then the per-map scoreboard rolled up from them."""
    kills_df = parsed.kills
    window = parsed.trade_window

    killers = kills_df.select(["round_num", "tick", "attacker_steamid", "victim_steamid"])
    # A death is traded when the killer is killed inside the trade window.
    traded = (
        killers.join(
            killers.select(
                [
                    pl.col("round_num"),
                    pl.col("tick").alias("revenge_tick"),
                    pl.col("victim_steamid").alias("revenge_victim"),
                ]
            ),
            on="round_num",
            how="inner",
        )
        .filter(
            (pl.col("revenge_victim") == pl.col("attacker_steamid"))
            & (pl.col("revenge_tick") > pl.col("tick"))
            & (pl.col("revenge_tick") - pl.col("tick") <= window)
        )
        .select(["round_num", pl.col("victim_steamid").alias("steamid")])
        .unique()
    )
    traded_set = {(int(r["round_num"]), int(r["steamid"])) for r in traded.to_dicts()}

    first_kills = kills_df.sort("tick").group_by("round_num").first()
    openers = {
        int(r["round_num"]): (r.get("attacker_steamid"), r.get("victim_steamid"))
        for r in first_kills.to_dicts()
    }

    def counts(frame, key):
        out = {}
        if frame is None or frame.is_empty():
            return out
        rows = frame.filter(pl.col(key).is_not_null()).group_by(["round_num", key]).len()
        for r in rows.to_dicts():
            out[(int(r["round_num"]), int(r[key]))] = int(r["len"])
        return out

    k_by = counts(kills_df, "attacker_steamid")
    d_by = counts(kills_df, "victim_steamid")
    a_by = counts(kills_df, "assister_steamid")
    hs_by = counts(kills_df.filter(pl.col("headshot")), "attacker_steamid")

    dmg_by = {}
    if parsed.damages is not None and not parsed.damages.is_empty():
        for r in (
            parsed.damages.filter(pl.col("attacker_steamid").is_not_null())
            .group_by(["round_num", "attacker_steamid"])
            .agg(pl.col("dmg_health_real").sum().alias("d"))
            .to_dicts()
        ):
            dmg_by[(int(r["round_num"]), int(r["attacker_steamid"]))] = int(r["d"] or 0)

    sides = {
        (int(r["round_num"]), int(r["steamid"])): _side(r["side"])
        for r in parsed.player_sides.to_dicts()
    }
    team_of = {steamid: _id(team) for steamid, team in player_teams.items()}
    economy = _player_economy(parsed)
    round_stats = {
        (int(r["round_num"]), int(r["steamid"])): r
        for r in _table(parsed, "round_stats").to_dicts()
    }

    def stat(key, name):
        # Absent from the scoreboard (a player who left): 0 once the table exists.
        if not round_stats:
            return None
        value = (round_stats.get(key) or {}).get(name)
        return min(max(0, int(value or 0)), SMALL_MAX)

    rows = []
    for number, rnd in rounds.items():
        opener_attacker, opener_victim = openers.get(number, (None, None))
        for steamid, player in players.items():
            key = (number, steamid)
            deaths = d_by.get(key, 0)
            kills = k_by.get(key, 0)
            assists = a_by.get(key, 0)
            traded_here = key in traded_set
            bought = economy.get(key) or {}
            rows.append(
                {
                    "round_id": rnd.id,
                    "player_id": player.id,
                    "team_id": team_of.get(steamid),
                    "side": sides.get(key, ""),
                    "kills": kills,
                    "deaths": deaths,
                    "assists": assists,
                    "damage": min(dmg_by.get(key, 0), SMALL_MAX),
                    "survived": deaths == 0,
                    "traded": traded_here,
                    "opening_kill": opener_attacker is not None and int(opener_attacker) == steamid,
                    "opening_death": opener_victim is not None and int(opener_victim) == steamid,
                    "kast": bool(kills or assists or deaths == 0 or traded_here),
                    "money": _int(bought.get("balance")),
                    "equip_value": _int(bought.get("equip_value")),
                    "armor": _int(bought.get("armor")),
                    "helmet": bought.get("helmet"),
                    "defuser": bought.get("defuser"),
                    "primary_weapon": primary_weapon(bought.get("inventory")),
                    "enemies_flashed": stat(key, "enemies_flashed"),
                    "utility_damage": stat(key, "utility_damage"),
                    "money_saved": stat(key, "money_saved"),
                    "kill_reward": stat(key, "kill_reward"),
                    "_number": number,
                    "_steamid": steamid,
                }
            )
    if rows:
        db.execute(
            insert(PlayerRound),
            [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
        )

    # Scoreboard = the per-round rows summed. Nothing is recomputed from awpy here.
    n_rounds = max(1, parsed.n_rounds)
    stats = []
    for steamid, player in players.items():
        mine = [r for r in rows if r["_steamid"] == steamid]
        kills = sum(r["kills"] for r in mine)
        deaths = sum(r["deaths"] for r in mine)
        damage = sum(r["damage"] for r in mine)
        headshots = sum(hs_by.get((r["_number"], steamid), 0) for r in mine)
        kast_rounds = sum(1 for r in mine if r["kast"])
        stats.append(
            {
                "match_map_id": match_map.id,
                "player_id": player.id,
                "team_id": team_of.get(steamid),
                "rounds_played": n_rounds,
                "kills": kills,
                "deaths": deaths,
                "assists": sum(r["assists"] for r in mine),
                "headshots": headshots,
                "kd_diff": kills - deaths,  # signed, deliberately (H7)
                "damage": damage,
                "adr": round(damage / n_rounds, 1),
                "hs_pct": round(headshots / kills * 100, 1) if kills else None,
                "kast_pct": round(kast_rounds / n_rounds * 100, 1),
                "opening_kills": sum(1 for r in mine if r["opening_kill"]),
                "opening_deaths": sum(1 for r in mine if r["opening_death"]),
            }
        )
    if stats:
        db.execute(insert(PlayerMap), stats)


# The kill feed and the damage feed name the same gun differently: a kill says
# "usp_silencer" where the damage says "hkp2000". Folded onto one key so the CT
# pistol does not read as thousands of damage and zero kills.
WEAPON_FAMILIES = {
    "usp_silencer": "usp",
    "hkp2000": "usp",
    "m4a1_silencer": "m4a1",
    "m4a1": "m4a1",
    "knife_butterfly": "knife",
    "knife": "knife",
}
WEAPON_LABELS = {"usp": "usp/p2000"}
NOT_A_GUN = ("knife", "world", "")
FIRE_WEAPONS = ("inferno", "molotov", "incgrenade")
HE_WEAPONS = ("hegrenade",)


def weapon_family(weapon: str) -> str:
    """One key per real gun, whichever feed named it."""
    name = (weapon or "").strip().lower()
    return WEAPON_LABELS.get(WEAPON_FAMILIES.get(name, name), WEAPON_FAMILIES.get(name, name))


def _roster_teams(db: Session, match_map: MatchMap) -> dict[int, int | None]:
    return dict(
        db.execute(
            select(MapRoster.player_id, MapRoster.team_id).where(
                MapRoster.match_map_id == match_map.id
            )
        ).all()
    )


def _ingest_player_breakdown(db: Session, match_map: MatchMap) -> None:
    """Per player, on **this map**: positions, weapons and utility.

    Grouped here rather than at report time because a callout only means
    something inside its own map. Everything it reads was written moments ago
    by the same transaction.
    """
    teams = _roster_teams(db, match_map)
    if not teams:
        return
    in_map = KillEvent.round_id.in_(_rounds_of(match_map))
    dmg_in_map = DamageEvent.round_id.in_(_rounds_of(match_map))

    # -- positions, split by the side the player was on when it happened
    rows = []
    for kind, player_col, place_col, side_col in (
        (
            PositionKind.KILL_FROM,
            KillEvent.attacker_id,
            KillEvent.attacker_place,
            KillEvent.attacker_side,
        ),
        (
            PositionKind.VICTIM_AT,
            KillEvent.attacker_id,
            KillEvent.victim_place,
            KillEvent.attacker_side,
        ),
        (PositionKind.DEATH_AT, KillEvent.victim_id, KillEvent.victim_place, KillEvent.victim_side),
    ):
        query = (
            select(player_col, place_col, side_col, func.count())
            .where(in_map, place_col != "")
            .group_by(player_col, place_col, side_col)
        )
        for player_id, place, side, n in db.execute(query):
            if player_id is None or player_id not in teams:
                continue
            rows.append(
                {
                    "match_map_id": match_map.id,
                    "player_id": player_id,
                    "team_id": teams[player_id],
                    "kind": kind,
                    "side": _side(side),
                    "place": place[:24],
                    "count": min(n, SMALL_MAX),
                }
            )
    if rows:
        db.execute(insert(PlayerMapPosition), rows)

    # -- weapons: kills and damage folded onto one family key, per side
    stats: dict[tuple, dict] = {}

    def weapon_entry(pid, weapon, side) -> dict:
        return stats.setdefault(
            (pid, weapon_family(weapon), _side(side)),
            {"kills": 0, "hs": 0, "damage": 0, "hits": 0},
        )

    headshots = func.sum(case((KillEvent.headshot, 1), else_=0))
    for pid, weapon, side, n, hs in db.execute(
        select(
            KillEvent.attacker_id,
            KillEvent.weapon,
            KillEvent.attacker_side,
            func.count(),
            headshots,
        )
        .where(in_map)
        .group_by(KillEvent.attacker_id, KillEvent.weapon, KillEvent.attacker_side)
    ):
        if pid is None or pid not in teams:
            continue
        entry = weapon_entry(pid, weapon, side)
        entry["kills"] += n
        entry["hs"] += int(hs or 0)
    for pid, weapon, side, dmg, hits in db.execute(
        select(
            DamageEvent.attacker_id,
            DamageEvent.weapon,
            DamageEvent.attacker_side,
            func.sum(DamageEvent.damage),
            func.count(),
        )
        .where(dmg_in_map)
        .group_by(DamageEvent.attacker_id, DamageEvent.weapon, DamageEvent.attacker_side)
    ):
        if pid is None or pid not in teams or weapon_family(weapon) in NOT_A_GUN:
            continue
        entry = weapon_entry(pid, weapon, side)
        entry["damage"] += int(dmg or 0)
        entry["hits"] += hits
    if stats:
        db.execute(
            insert(PlayerMapWeapon),
            [
                {
                    "match_map_id": match_map.id,
                    "player_id": pid,
                    "team_id": teams[pid],
                    "weapon": weapon,
                    "side": side,
                    "kills": min(v["kills"], SMALL_MAX),
                    "headshots": min(v["hs"], SMALL_MAX),
                    "damage": v["damage"],
                    "hits": min(v["hits"], SMALL_MAX),
                }
                for (pid, weapon, side), v in stats.items()
            ],
        )

    # -- utility, per side
    util: dict[tuple, dict] = {}

    def bucket(pid, side) -> dict:
        return util.setdefault(
            (pid, _side(side)),
            {
                "smokes": 0,
                "infernos": 0,
                "fire_damage": 0,
                "he_damage": 0,
                "flash_assists": 0,
                "smoke_rounds": set(),
                "smoke_rounds_won": 0,
            },
        )

    grenades_in_map = GrenadeThrow.round_id.in_(_rounds_of(match_map))
    for pid, kind, side, n in db.execute(
        select(GrenadeThrow.thrower_id, GrenadeThrow.type, GrenadeThrow.thrower_side, func.count())
        .where(grenades_in_map)
        .group_by(GrenadeThrow.thrower_id, GrenadeThrow.type, GrenadeThrow.thrower_side)
    ):
        if pid in teams:
            key = {"smoke": "smokes", "inferno": "infernos"}.get(kind)
            if key:
                bucket(pid, side)[key] += n

    for weapons, field in ((FIRE_WEAPONS, "fire_damage"), (HE_WEAPONS, "he_damage")):
        for pid, side, total in db.execute(
            select(DamageEvent.attacker_id, DamageEvent.attacker_side, func.sum(DamageEvent.damage))
            .where(dmg_in_map, DamageEvent.weapon.in_(weapons))
            .group_by(DamageEvent.attacker_id, DamageEvent.attacker_side)
        ):
            if pid in teams:
                bucket(pid, side)[field] += int(total or 0)

    # The assister is a team-mate of the attacker, so the kill's attacker side is
    # the assister's side too -- the assist itself carries no side of its own.
    for pid, side, n in db.execute(
        select(KillEvent.assister_id, KillEvent.attacker_side, func.count())
        .where(in_map, KillEvent.assistedflash, KillEvent.assister_id.in_(list(teams)))
        .group_by(KillEvent.assister_id, KillEvent.attacker_side)
    ):
        bucket(pid, side)["flash_assists"] += n

    for pid, side, round_id, winner_id in db.execute(
        select(
            GrenadeThrow.thrower_id,
            GrenadeThrow.thrower_side,
            GrenadeThrow.round_id,
            Round.winner_team_id,
        )
        .join(Round, Round.id == GrenadeThrow.round_id)
        .where(grenades_in_map, GrenadeThrow.type == "smoke")
        .distinct()
    ):
        if pid not in teams:
            continue
        entry = bucket(pid, side)
        entry["smoke_rounds"].add(round_id)
        if winner_id == teams[pid]:
            entry["smoke_rounds_won"] += 1

    if util:
        db.execute(
            insert(PlayerMapUtility),
            [
                {
                    "match_map_id": match_map.id,
                    "player_id": pid,
                    "team_id": teams[pid],
                    "side": side,
                    "smokes": v["smokes"],
                    "infernos": v["infernos"],
                    "fire_damage": v["fire_damage"],
                    "he_damage": v["he_damage"],
                    "flash_assists": v["flash_assists"],
                    "smoke_rounds": len(v["smoke_rounds"]),
                    "smoke_rounds_won": v["smoke_rounds_won"],
                }
                for (pid, side), v in util.items()
            ],
        )


def _ingest_player_duels(db: Session, match_map: MatchMap) -> None:
    """Who killed whom, and from where -- the matchup layer.

    Only cross-team kills are stored: a team-mate death is an accident, not a
    duel, and keeping them would pollute every matchup number downstream.
    """
    teams = _roster_teams(db, match_map)
    if not teams:
        return

    kills = db.execute(
        select(
            KillEvent.id,
            KillEvent.round_id,
            KillEvent.attacker_id,
            KillEvent.victim_id,
            KillEvent.attacker_side,
            KillEvent.attacker_place,
            KillEvent.victim_place,
            KillEvent.headshot,
        )
        .where(KillEvent.round_id.in_(_rounds_of(match_map)))
        .order_by(KillEvent.round_id, KillEvent.tick, KillEvent.id)
    ).all()
    # The round's first kill, so an opening duel can be told apart from a trade
    # or a clean-up later in the round.
    openers: set[int] = set()
    seen_rounds: set[int] = set()
    for kill in kills:
        if kill.round_id not in seen_rounds:
            seen_rounds.add(kill.round_id)
            openers.add(kill.id)

    tally: dict[tuple, dict] = {}
    for kill in kills:
        killer, victim = kill.attacker_id, kill.victim_id
        if killer is None:
            continue
        killer_team, victim_team = teams.get(killer), teams.get(victim)
        if not killer_team or not victim_team or killer_team == victim_team:
            continue
        key = (
            killer,
            victim,
            _side(kill.attacker_side),
            (kill.attacker_place or "")[:24],
            (kill.victim_place or "")[:24],
        )
        entry = tally.setdefault(
            key, {"kills": 0, "hs": 0, "opening": 0, "kt": killer_team, "vt": victim_team}
        )
        entry["kills"] += 1
        entry["hs"] += 1 if kill.headshot else 0
        entry["opening"] += 1 if kill.id in openers else 0

    if tally:
        db.execute(
            insert(PlayerMapDuel),
            [
                {
                    "match_map_id": match_map.id,
                    "killer_id": killer,
                    "victim_id": victim,
                    "killer_team_id": v["kt"],
                    "victim_team_id": v["vt"],
                    "side": side,
                    "killer_place": kp,
                    "victim_place": vp,
                    "kills": min(v["kills"], SMALL_MAX),
                    "headshots": min(v["hs"], SMALL_MAX),
                    "opening_kills": min(v["opening"], SMALL_MAX),
                }
                for (killer, victim, side, kp, vp), v in tally.items()
            ],
        )


# How many callouts make a route. Long enough to describe an approach, short
# enough that the same approach in twenty rounds groups into one row.
ROUTE_STEPS = 5
# A route walked fewer times than this is an anecdote, not a tendency.
MIN_ROUTE_ROUNDS = 2


def _ingest_player_routes(db: Session, match_map: MatchMap, parsed) -> None:
    """The paths each player walks on this map, and what they produced.

    Built from the tick stream: after freeze time, the sequence of callouts a
    player passes through, consecutive repeats collapsed. Coarse on purpose --
    coordinates never repeat, callouts do, so this is what actually groups.
    """
    ticks = getattr(parsed, "ticks", None)
    if ticks is None or ticks.is_empty() or "place" not in ticks.columns:
        return

    freeze = {int(r["round_num"]): int(r["freeze_end"] or 0) for r in parsed.rounds.to_dicts()}
    live = (
        ticks.filter(
            pl.col("place").is_not_null()
            & (pl.col("place") != "")
            # Non-finite coordinates are real: a NaN centroid poisons every plot.
            & pl.col("X").is_not_null()
            & pl.col("Y").is_not_null()
            & pl.col("X").is_finite()
            & pl.col("Y").is_finite()
        )
        .with_columns(pl.col("round_num").replace_strict(freeze, default=0).alias("_freeze"))
        .filter(pl.col("tick") >= pl.col("_freeze"))
    )
    if live.is_empty():
        return

    # One centroid per callout for the whole map, so routes sharing a callout
    # line up exactly when drawn on top of each other.
    centroids = {
        row["place"]: (float(row["x"]), float(row["y"]))
        for row in live.group_by("place")
        .agg(pl.col("X").mean().alias("x"), pl.col("Y").mean().alias("y"))
        .to_dicts()
        if row["x"] is not None
        and row["y"] is not None
        and math.isfinite(row["x"])
        and math.isfinite(row["y"])
    }

    sequences = (
        live.sort("tick")
        .group_by(["round_num", "steamid"])
        .agg(pl.col("place").alias("places"), pl.col("side").first().alias("side"))
    )

    roster = db.execute(
        select(Player.steamid, MapRoster.player_id, MapRoster.team_id)
        .join(Player, Player.id == MapRoster.player_id)
        .where(MapRoster.match_map_id == match_map.id)
    ).all()
    players = {r.steamid: r.player_id for r in roster}
    teams = {r.player_id: r.team_id for r in roster}
    outcomes = {
        (number, player_id): (kills, deaths)
        for number, player_id, kills, deaths in db.execute(
            select(Round.number, PlayerRound.player_id, PlayerRound.kills, PlayerRound.deaths)
            .join(Round, Round.id == PlayerRound.round_id)
            .where(Round.match_map_id == match_map.id)
        )
    }
    winners = dict(
        db.execute(
            select(Round.number, Round.winner_team_id).where(Round.match_map_id == match_map.id)
        ).all()
    )

    tally: dict[tuple, dict] = {}
    for row in sequences.to_dicts():
        player_id = players.get(int(row["steamid"]))
        if player_id is None:
            continue
        places = _collapse(row["places"], ROUTE_STEPS)
        if len(places) < 2:
            continue

        key = (player_id, _side(row.get("side")), ">".join(places))
        entry = tally.setdefault(
            key, {"places": places, "rounds": 0, "kills": 0, "deaths": 0, "won": 0}
        )
        entry["rounds"] += 1
        result = outcomes.get((int(row["round_num"]), player_id))
        if result:
            entry["kills"] += result[0]
            entry["deaths"] += result[1]
        won_by = winners.get(int(row["round_num"]))
        if won_by and won_by == teams.get(player_id):
            entry["won"] += 1

    rows = [
        {
            "match_map_id": match_map.id,
            "player_id": player_id,
            "team_id": teams.get(player_id),
            "side": side,
            "route_key": route_key[:200],
            "places": entry["places"],
            "path": [
                {"place": p, "x": centroids[p][0], "y": centroids[p][1]}
                for p in entry["places"]
                if p in centroids
            ],
            "rounds": entry["rounds"],
            "kills": min(entry["kills"], SMALL_MAX),
            "deaths": min(entry["deaths"], SMALL_MAX),
            "rounds_won": entry["won"],
        }
        for (player_id, side, route_key), entry in tally.items()
        if entry["rounds"] >= MIN_ROUTE_ROUNDS
    ]
    if rows:
        db.execute(insert(PlayerMapRoute), rows)


def _collapse(places, limit: int) -> list:
    """Consecutive repeats are standing still, not moving."""
    out: list = []
    for place in places:
        if not out or out[-1] != place:
            out.append(place)
        if len(out) >= limit:
            break
    return out


def _finalise_scores(db: Session, match_map: MatchMap, rounds: dict[int, Round]) -> None:
    """Turn round winners into a team scoreline (H1 -- 'ct won' is not a team)."""
    tally = dict(
        db.execute(
            select(Round.winner_team_id, func.count())
            .where(Round.match_map_id == match_map.id, Round.winner_team_id.is_not(None))
            .group_by(Round.winner_team_id)
        ).all()
    )
    match_map.team1_score = tally.get(match_map.team1_id, 0)
    match_map.team2_score = tally.get(match_map.team2_id, 0)
    if match_map.team1_score != match_map.team2_score:
        match_map.winner_id = (
            match_map.team1_id
            if match_map.team1_score > match_map.team2_score
            else match_map.team2_id
        )
    match_map.n_rounds = len(rounds)
    db.flush()


def rebuild_player_match(db: Session, match: Match) -> int:
    """Recompute the per-series rollup from every parsed map of this match."""
    db.execute(delete(PlayerMatch).where(PlayerMatch.match_id == match.id))
    per_player: dict[int, list[PlayerMap]] = {}
    for stat in db.scalars(select(PlayerMap).join(MatchMap).where(MatchMap.match_id == match.id)):
        per_player.setdefault(stat.player_id, []).append(stat)

    rows = []
    for player_id, maps in per_player.items():
        rounds = sum(m.rounds_played for m in maps) or 1
        kills = sum(m.kills for m in maps)
        deaths = sum(m.deaths for m in maps)
        damage = sum(m.damage for m in maps)
        headshots = sum(m.headshots for m in maps)
        kast_rounds = sum((m.kast_pct or 0) / 100 * m.rounds_played for m in maps)
        rows.append(
            {
                "match_id": match.id,
                "player_id": player_id,
                "team_id": maps[0].team_id,
                "maps_played": len(maps),
                "rounds_played": rounds,
                "kills": kills,
                "deaths": deaths,
                "assists": sum(m.assists for m in maps),
                "headshots": headshots,
                "kd_diff": kills - deaths,
                "damage": damage,
                "adr": round(damage / rounds, 1),
                "hs_pct": round(headshots / kills * 100, 1) if kills else None,
                "kast_pct": round(kast_rounds / rounds * 100, 1),
                "opening_kills": sum(m.opening_kills for m in maps),
                "opening_deaths": sum(m.opening_deaths for m in maps),
            }
        )
    if rows:
        db.execute(insert(PlayerMatch), rows)
    return len(rows)


def pending_map_demos(db: Session, match_ids=None) -> list[Demo]:
    """Map-level demos that need parsing.

    "Need parsing" is not only "never parsed": a map stored under an older
    ``schema_version`` is stale, because the ingest has learnt to record
    something since. Those are picked up automatically.

    A Match Map recorded as Demo parts is listed once, by part 1; the rest come
    with it (:func:`demo_parts`).
    """
    query = (
        select(Demo)
        .join(Demo.match)
        .outerjoin(MatchMap, MatchMap.demo_id == Demo.id)
        .options(
            joinedload(Demo.match).joinedload(Match.team1),
            joinedload(Demo.match).joinedload(Match.team2),
            joinedload(Demo.analysis),
        )
        .where(Demo.is_downloaded, Demo.map != "", Demo.part <= 1)
        .where(
            or_(
                ~Demo.is_processed,
                MatchMap.id.is_(None),
                MatchMap.schema_version < CURRENT_SCHEMA_VERSION,
            )
        )
        .order_by(Match.played_at, Demo.match_id, Demo.map_number)
    )
    if match_ids is not None:
        query = query.where(Match.hltv_id.in_(list(match_ids)))
    return list(db.scalars(query).unique())


def demo_parts(db: Session, demo: Demo) -> list[Demo]:
    """``demo`` with the rest of its Match Map's Demo parts, in order; just
    ``demo`` for a map recorded whole (docs/adr/0009)."""
    if not demo.part:
        return [demo]
    return list(
        db.scalars(
            select(Demo)
            .where(Demo.match_id == demo.match_id, Demo.map == demo.map, Demo.part >= 1)
            .order_by(Demo.part)
        )
    )


def count_map_demos(db: Session, match_ids=None) -> int:
    """Every downloaded map demo in scope, parsed or not; Demo parts once."""
    query = (
        select(func.count())
        .select_from(Demo)
        .join(Demo.match)
        .where(Demo.is_downloaded, Demo.map != "", Demo.part <= 1)
    )
    if match_ids is not None:
        query = query.where(Match.hltv_id.in_(list(match_ids)))
    return db.scalar(query) or 0
