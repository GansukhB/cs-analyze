"""Where the my team and an opponent stand and move on one Map (v2 screen 05)."""

from collections import Counter
from typing import Literal

from fastapi import APIRouter, Response

from app.deps import DbSession, StaffUser
from app.routers.v2.common import my_team, team
from app.schemas_v2 import Spatial
from app.services import answers, dbctx, mn, spatial, team_numbers

router = APIRouter()
VERSION = 1


@router.get("/teams/{team_id}/spatial")
def spatial_view(
    team_id: int,
    db: DbSession,
    user: StaffUser,
    response: Response,
    opponent: int | None = None,
    map: str | None = None,
    side: Literal["t", "ct"] = "t",
    mode: Literal["heat", "move", "trade", "lurk"] = "heat",
) -> Spatial:
    my_team(db, user, team_id)
    if opponent:
        team(db, opponent)
    params = {"team": team_id, "opponent": opponent, "map": map, "side": side, "mode": mode}
    return Spatial(**answers.serve(db, "v2.spatial", params, response=response))


@answers.kind("v2.spatial", VERSION, deps=answers.teams("team", "opponent"))
def _spatial(db, p: dict) -> dict:
    mine = team(db, p["team"])
    theirs = team(db, p["opponent"]) if p.get("opponent") else None
    map, side, mode = p.get("map"), p["side"], p["mode"]
    with dbctx.using(db):
        maps = team_numbers.team_maps(mine.id)
        counts = Counter(team_numbers.map_name(m) for m in maps)
        names = [n for n, _c in counts.most_common()]
        chosen = map if map in counts else (names[0] if names else None)
        if chosen is None:
            empty = Spatial(maps=[], map=None, side=side, mode=mode, windows=[], plate=None,
                            labels=[], us=None, them=None, opponent=None)  # fmt: skip
            return empty.model_dump(mode="json")
        us = spatial.build(mine, chosen, side, mode)
        them = spatial.build(theirs, chosen, side, mode) if theirs else None
        drawn = spatial.scene([m for m in maps if team_numbers.map_name(m) == chosen], chosen)
        return Spatial(
            maps=[{"map": n, "label": mn.game_map(n), "n": counts[n]} for n in names],
            map=chosen,
            side=side,
            mode=mode,
            windows=[list(w) for w in spatial.WINDOWS],
            plate=drawn["plate"],
            labels=drawn["labels"],
            us=us,
            them=them,
            opponent={"id": theirs.id, "name": theirs.name} if theirs else None,
        ).model_dump(mode="json")
