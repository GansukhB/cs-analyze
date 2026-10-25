"""One Player's profile (v2 screen 04) and Staff's note on him."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import select

from app.deps import DbSession, StaffUser
from app.models import DevelopmentNote, MatchKind, Player, PlayerAlias
from app.routers.v2.common import my_team
from app.schemas_v2 import DevNote, Five, NoteWrite, PlayerProfile
from app.services import dbctx, player_cards, player_profile, scope, team_numbers, team_overview

router = APIRouter()
Steamid = Annotated[str, Path(pattern=r"^\d{1,20}$")]
KPIS = ("rating", "adr", "kast", "opening_pct", "hs", "traded_pct")


def _player(db, steamid: str) -> Player:
    found = db.scalar(select(Player).where(Player.steamid == int(steamid)))
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such player")
    return found


def _kpis(d: dict) -> dict:
    return {k: (round(d[k], 3) if d.get(k) is not None else None) for k in KPIS}


def _mean(rows: list[dict]) -> dict:
    out = {}
    for k in KPIS:
        values = [r[k] for r in rows if r.get(k) is not None]
        out[k] = round(sum(values) / len(values), 3) if values else None
    return out


@router.get("/teams/{team_id}/players")
def roster(team_id: int, db: DbSession, user: StaffUser) -> Five:
    """The my team's five on its latest parsed Match Map."""
    team = my_team(db, user, team_id)
    with dbctx.using(db):
        five = team_overview.current_five(team)
    return Five(players=[{"steamid": str(p.steamid), "name": p.name} for p in five])


@router.get("/teams/{team_id}/players/{steamid}/profile")
def profile(
    team_id: int,
    steamid: Steamid,
    db: DbSession,
    user: StaffUser,
    scrims: bool = False,
    map: str | None = None,
    side: Literal["t", "ct"] = "t",
) -> PlayerProfile:
    team = my_team(db, user, team_id)
    player = _player(db, steamid)
    with dbctx.using(db):
        # The Pool first, before this request may see Scrims (docs/adr/0010).
        pool = player_profile.pool()
        mates = player_profile.teammates(team.id, player.id)
        team_maps = [m.id for m in team_numbers.team_maps(team.id, kind=MatchKind.OFFICIAL)]
        mate_raw = player_profile._raw(team_maps, [p.id for p in mates])
        if scrims:
            scope.allow_scrims(db)
        maps = player_profile.maps_of(player.id)
        ids = [m.id for m in maps]
        mine = player_profile.derive(player_profile._raw(ids, [player.id]).get(player.id, {}))
        mate_lines = []
        for p in mates:
            d = player_profile.derive(mate_raw.get(p.id, {}))
            if d:
                mate_lines.append(
                    {
                        "steamid": str(p.steamid),
                        "name": p.name,
                        "axes": player_profile.axes(d, pool),
                        "kpis": _kpis(d),
                    }
                )
        team_axes = {}
        for axis in player_profile.AXES:
            values = [m["axes"][axis] for m in mate_lines if m["axes"].get(axis) is not None]
            team_axes[axis] = round(sum(values) / len(values)) if values else None
        cards = player_cards.lines(team, [player.id]).get(player.id) or {}
        note = db.scalar(
            select(DevelopmentNote).where(
                DevelopmentNote.workspace_id == user.workspace_id,
                DevelopmentNote.player_id == player.id,
            )
        )
        aliases = sorted(
            set(db.scalars(select(PlayerAlias.name).where(PlayerAlias.player_id == player.id)))
            - {player.name}
        )
        axes = player_profile.axes(mine, pool) if mine else {}
        return PlayerProfile(
            steamid=str(player.steamid),
            name=player.name,
            aliases=aliases,
            team={"id": team.id, "name": team.name},
            rounds=mine.get("rounds", 0),
            maps=len(maps),
            clutch_won=mine.get("clutch_won", 0),
            clutch_of=mine.get("clutch_of", 0),
            pool_players=len(pool),
            kpis=_kpis(mine),
            team_kpis=_mean([m["kpis"] for m in mate_lines]),
            pool_kpis={k: player_profile.median(pool, k) for k in KPIS},
            axes=axes,
            team_axes=team_axes,
            mates=mate_lines,
            form=player_profile.form(player, maps),
            mechanics=player_profile.mechanics(str(player.steamid), set(ids)),
            duels=player_profile.duel_grid(player.id, ids),
            positions=player_profile.positions(player.id, maps, map, side),
            weapons=player_profile.weapons(player.id, ids),
            lines=_lines(cards, axes),
            note={"text": note.text, "updated_at": note.updated_at} if note else None,
        )


AXIS_LABEL = {
    "firepower": "Firepower", "entry": "Entry", "trade": "Trade", "utility": "Utility",
    "clutch": "Clutch", "survival": "Survival", "opening": "Opening",
}  # fmt: skip


def _lines(card: dict, axes: dict) -> list[dict]:
    """What the evidence settles about him: the Reviews' tested lines (PL-7), then
    his strongest and weakest axes among the Pool."""
    out = []
    swing = card.get("swing")
    if swing and swing.get("clear"):
        good = swing["per_round"] > 0
        out.append(
            {"good": good, "text": f"Swing/раунд {100 * swing['per_round']:+.1f}% "
             f"({100 * swing['low']:+.1f}…{100 * swing['high']:+.1f}%)"}
        )  # fmt: skip
    for t in card.get("tendencies", [])[:2]:
        out.append(
            {"good": True, "text": f"{t['label']}: {t['per24']}/24 (бусад {t['pool_per24']})"}
        )
    for w in card.get("weaknesses", [])[:3]:
        out.append(
            {"good": False, "text": f"{w['label']}: {w['per24']}/24 (бусад {w['pool_per24']})"}
        )
    ranked = sorted(((v, k) for k, v in axes.items() if v is not None), reverse=True)
    if ranked:
        top, bottom = ranked[0], ranked[-1]
        if top[0] >= 70:
            out.append(
                {"good": True, "text": f"{AXIS_LABEL[top[1]]}: Pool-ын {top[0]:.0f}-р percentile"}
            )
        if bottom[0] <= 30:
            out.append(
                {
                    "good": False,
                    "text": f"{AXIS_LABEL[bottom[1]]}: Pool-ын {bottom[0]:.0f}-р percentile",
                }
            )
    return out


@router.put("/players/{steamid}/note")
def put_note(steamid: Steamid, body: NoteWrite, db: DbSession, user: StaffUser) -> DevNote:
    player = _player(db, steamid)
    note = db.scalar(
        select(DevelopmentNote).where(
            DevelopmentNote.workspace_id == user.workspace_id,
            DevelopmentNote.player_id == player.id,
        )
    )
    if note is None:
        note = DevelopmentNote(workspace_id=user.workspace_id, player_id=player.id)
        db.add(note)
    note.text = body.text.strip()
    note.updated_by_id = user.id
    db.commit()
    return DevNote(text=note.text, updated_at=note.updated_at)
