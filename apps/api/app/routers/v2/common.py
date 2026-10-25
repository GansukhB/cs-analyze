"""What every v2 endpoint checks first."""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Team, User


def my_team(db: Session, user: User, team_id: int) -> Team:
    """One of the User's Workspace's my teams (CONTEXT.md), else 404: v2 is read
    from "we", and another Workspace's plans are never reachable."""
    if team_id not in {t.team_id for t in user.workspace.teams}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not one of your teams")
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team")
    return team


def team(db: Session, team_id: int) -> Team:
    found = db.get(Team, team_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such team")
    return found
