"""Which Game Plans of a my team are ready to open (docs/adr/0014)."""

from fastapi import APIRouter
from sqlalchemy import select

from app.deps import DbSession, StaffUser
from app.models import Team
from app.routers.v2.common import my_team
from app.schemas import WarmState
from app.schemas_v2 import ReadyFixtures, ReadyOpponent
from app.services import warmer

router = APIRouter()


@router.get("/teams/{team_id}/ready")
def ready(team_id: int, db: DbSession, user: StaffUser) -> ReadyFixtures:
    """The opponents the warm-up computes this my team's Game Plan against, in
    its order (the latest Scouts', the Upcoming matches', the Teams met last,
    then the most parsed), and how each one stands."""
    my_team(db, user, team_id)
    counts = warmer.parsed_map_counts(db)
    order = warmer.opponents(db, team_id, counts)
    names = dict(db.execute(select(Team.id, Team.name).where(Team.id.in_(order))).all())
    states = warmer.readiness(db, team_id, order)
    found = warmer.status()
    fields = WarmState.model_fields
    return ReadyFixtures(
        opponents=[
            ReadyOpponent(id=o, name=names.get(o, "?"), maps=counts.get(o, 0), state=states[o])
            for o in order
        ],
        warm=WarmState(**{k: v for k, v in found.items() if k in fields}) if found else None,
    )
