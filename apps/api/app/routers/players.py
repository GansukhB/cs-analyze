"""A Player's page (docs/plans/04-player-analytics.md PL-2), by Steam id."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from sqlalchemy import delete, select

from app.deps import CurrentUser, DbSession, StaffUser
from app.models import DeclaredRole, Player
from app.schemas import DeclaredRolePut, DeclaredRoleRead, DeclaredRoles, PlayerPage
from app.services import dbctx, player_page, roles

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/{steamid}")
def player(
    steamid: Annotated[str, Path(pattern=r"^\d{1,20}$")], db: DbSession, user: CurrentUser
) -> PlayerPage:
    """Form, numbers by Map and Side, Findings against every Player's, spots, guns.

    The Steam id is a string in the path, as everywhere the browser holds one:
    as a JavaScript number it would lose its last digits. A Player login sees
    only their own (docs/plans WS-4)."""
    if not user.is_staff and (user.player is None or str(user.player.steamid) != steamid):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such player")
    with dbctx.using(db):
        built = player_page.build(int(steamid))
        if built is not None:
            # His Scrims for our teams join his form, marked, and nothing else (RV-6).
            mine = {t.team_id for t in user.workspace.teams}
            scrims = player_page.scrim_form(int(steamid), mine)
            built["form"] = sorted(
                built["form"] + scrims,
                key=lambda r: (r["played_at"] or datetime.min, r["map_number"]),
            )
    if built is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such player")
    return PlayerPage(**built)


def _player(db, steamid: str) -> Player:
    found = db.scalar(select(Player).where(Player.steamid == int(steamid)))
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such player")
    return found


def _declared(db, user, player: Player) -> DeclaredRoles:
    rows = db.scalars(
        select(DeclaredRole).where(
            DeclaredRole.workspace_id == user.workspace_id, DeclaredRole.player_id == player.id
        )
    ).all()
    choices = {
        side: [
            {"role": k, "label": v["label"]} for k, v in roles.ROLES.items() if side in v["sides"]
        ]
        for side in ("ct", "t")
    }
    return DeclaredRoles(
        roles=[
            DeclaredRoleRead(
                side=r.side, map=r.map, role=r.role, label=roles.ROLES[r.role]["label"]
            )
            for r in rows
            if r.role in roles.ROLES
        ],
        choices=choices,
    )


@router.get("/{steamid}/roles")
def declared_roles(
    steamid: Annotated[str, Path(pattern=r"^\d{1,20}$")], db: DbSession, user: StaffUser
) -> DeclaredRoles:
    """The roles Staff declared for this Player (PL-4), and what can be declared."""
    return _declared(db, user, _player(db, steamid))


@router.put("/{steamid}/roles")
def declare_role(
    steamid: Annotated[str, Path(pattern=r"^\d{1,20}$")],
    body: DeclaredRolePut,
    db: DbSession,
    user: StaffUser,
) -> DeclaredRoles:
    """Set (or with role "" clear) the role this Player plays on a Side. It is the
    truth for his role and his cohort; opponents keep inferred roles."""
    player = _player(db, steamid)
    if body.role and (
        body.role not in roles.ROLES or body.side not in roles.ROLES[body.role]["sides"]
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No such role on that Side")
    db.execute(
        delete(DeclaredRole).where(
            DeclaredRole.workspace_id == user.workspace_id,
            DeclaredRole.player_id == player.id,
            DeclaredRole.side == body.side,
            DeclaredRole.map == body.map,
        )
    )
    if body.role:
        db.add(
            DeclaredRole(
                workspace_id=user.workspace_id,
                player_id=player.id,
                side=body.side,
                map=body.map,
                role=body.role,
            )
        )
    db.commit()
    return _declared(db, user, player)
