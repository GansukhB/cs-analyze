"""One match: its maps as tabs, and one of them replayable round by round.

Ported from cstat's ``match_detail``/``match_round`` views. The scoreboard and
the round list answer most of what the page is opened for, so they come with the
map; the replay's rounds are fetched one at a time, because a map is twenty-four
rounds of a couple of hundred kilobytes each.
"""

import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.deps import CurrentUser, DbSession
from app.models import Match, MatchMap, PlayerMap, Round
from app.routers.teams import map_label
from app.schemas import (
    MatchInfo,
    MatchMapDetail,
    MatchMapTab,
    RoundStripRow,
    Scene,
    ScoreboardPlayer,
    ScoreboardSide,
    TeamRef,
)
from app.services import replay

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matches", tags=["matches"])


def _ref(team) -> TeamRef | None:
    return TeamRef(id=team.id, name=team.name) if team else None


def _playable(match_map: MatchMap) -> bool:
    return match_map.is_parsed and replay.is_playable(match_map)


def _match(db: Session, match_id: int) -> Match:
    match = db.scalar(
        select(Match)
        .where(Match.id == match_id)
        .options(
            joinedload(Match.team1),
            joinedload(Match.team2),
            joinedload(Match.tournament),
            selectinload(Match.map_results).joinedload(MatchMap.game_map),
        )
    )
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such match")
    return match


def _map(db: Session, match_id: int, map_number: int) -> MatchMap:
    match_map = db.scalar(
        select(MatchMap)
        .where(MatchMap.match_id == match_id, MatchMap.map_number == map_number)
        .options(
            joinedload(MatchMap.game_map), joinedload(MatchMap.team1), joinedload(MatchMap.team2)
        )
    )
    if match_map is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"This match has no map {map_number}")
    return match_map


@router.get("/{match_id}")
def get_match(match_id: int, db: DbSession, _: CurrentUser) -> MatchInfo:
    """The match and its maps. ``default_map`` is where a bare match link lands:
    the first replayable map, else the first parsed one (whose page can then say
    its bundle is gone), else none."""
    match = _match(db, match_id)
    maps = sorted(match.map_results, key=lambda m: m.map_number)
    playable = [m for m in maps if _playable(m)]
    target = playable[0] if playable else next((m for m in maps if m.is_parsed), None)
    return MatchInfo(
        id=match.id,
        hltv_id=match.hltv_id,
        hltv_url=f"https://www.hltv.org{match.url}",
        team1=_ref(match.team1),
        team2=_ref(match.team2),
        score=match.score,
        tournament=match.tournament.name if match.tournament else "",
        played_at=match.played_at,
        maps=[
            MatchMapTab(
                map_number=m.map_number,
                label=map_label(m.game_map),
                scoreline=m.scoreline,
                parsed=m.is_parsed,
                playable=_playable(m),
            )
            for m in maps
        ],
        default_map=target.map_number if target else None,
    )


@router.get("/{match_id}/maps/{map_number}")
def get_match_map(match_id: int, map_number: int, db: DbSession, _: CurrentUser) -> MatchMapDetail:
    """One map: its scene (the floor plan the replay draws on), round list and
    scoreboard. The Replay itself was cut from the Tick Data at ingest."""
    match_map = _map(db, match_id, map_number)
    scene = None
    if _playable(match_map):
        try:
            built = replay.scene(db, match_map)
        except Exception:  # a replay must never take the page down with it
            logger.exception("replay scene failed for map %s", match_map.id)
            built = None
        scene = Scene(**built) if built else None
    return MatchMapDetail(
        map_number=match_map.map_number,
        label=map_label(match_map.game_map),
        parsed=match_map.is_parsed,
        playable=_playable(match_map),
        scene=scene,
        rounds=_round_strip(db, match_map),
        scoreboard=_scoreboard(db, match_map),
    )


@router.get(
    "/{match_id}/maps/{map_number}/rounds/{number}",
    response_class=Response,
    responses={
        200: {
            "description": "One round's replay payload (gzip JSON; see app/services/replay.py).",
            "content": {"application/json": {"schema": {"type": "object"}}},
        }
    },
)
def get_round(match_id: int, map_number: int, number: int, db: DbSession, _: CurrentUser):
    """One round's replay payload, sent exactly as stored: gzip JSON, which the
    browser decodes on its own (``Content-Encoding: gzip``)."""
    match_map = _map(db, match_id, map_number)
    try:
        payload = replay.round_payload(db, match_map, number)
    except Exception as exc:  # a replay must never take the page down with it
        logger.exception("replay failed for map %s round %s", match_map.id, number)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not load this round"
        ) from exc
    if payload is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No replay data for this round")
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Encoding": "gzip", "Cache-Control": "private, max-age=3600"},
    )


def _round_strip(db: Session, match_map: MatchMap) -> list[RoundStripRow]:
    """Every round with the score it produced, in order.

    The half is detected from the CT team changing rather than from a round
    number, because overtime moves it.
    """
    rounds = db.scalars(
        select(Round)
        .options(joinedload(Round.winner_team))
        .where(Round.match_map_id == match_map.id)
        .order_by(Round.number)
    )
    score = {match_map.team1_id: 0, match_map.team2_id: 0}
    strip, previous_ct = [], None
    for rnd in rounds:
        if rnd.winner_team_id in score:
            score[rnd.winner_team_id] += 1
        strip.append(
            RoundStripRow(
                number=rnd.number,
                winner_side=rnd.winner_side,
                winner=rnd.winner_team.name if rnd.winner_team else "",
                reason=rnd.end_reason.replace("_", " "),
                planted=rnd.was_planted,
                site=rnd.bomb_site,
                score=f"{score.get(match_map.team1_id, 0)}-{score.get(match_map.team2_id, 0)}",
                mine=rnd.winner_team_id == match_map.team1_id,
                half_break=previous_ct is not None and rnd.ct_team_id != previous_ct,
            )
        )
        previous_ct = rnd.ct_team_id
    return strip


def _scoreboard(db: Session, match_map: MatchMap) -> list[ScoreboardSide]:
    """The two teams' stat lines, each under the team that produced them."""
    by_team: dict = defaultdict(list)
    for row in db.scalars(
        select(PlayerMap)
        .options(joinedload(PlayerMap.player))
        .where(PlayerMap.match_map_id == match_map.id)
        .order_by(PlayerMap.kills.desc())
    ):
        by_team[row.team_id].append(row)
    board = []
    for team, score, other in (
        (match_map.team1, match_map.team1_score, match_map.team2_score),
        (match_map.team2, match_map.team2_score, match_map.team1_score),
    ):
        if team is None:
            continue
        board.append(
            ScoreboardSide(
                team=TeamRef(id=team.id, name=team.name),
                score=score,
                won=score is not None and other is not None and score > other,
                players=[
                    ScoreboardPlayer(
                        name=p.player.name,
                        kills=p.kills,
                        deaths=p.deaths,
                        kd_diff=p.kd_diff,
                        adr=p.adr,
                        kast_pct=p.kast_pct,
                        hs_pct=p.hs_pct,
                    )  # fmt: skip
                    for p in by_team.get(team.id, [])
                ],
            )
        )
    return board
