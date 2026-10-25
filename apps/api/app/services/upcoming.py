"""Upcoming matches (CONTEXT.md): a Match a my team is due to play, as Staff
entered it, with its pre-match checklist and the counters picked for it.

Once a stored Match between the two Teams turns up around its start, the
Upcoming match points at it (:func:`link`), read lazily whenever it is shown.
Bind a session with ``dbctx.using``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select

from app.models import Match, Team, UpcomingMatch
from app.services.dbctx import db

# The design's checklist, as a start Staff edit.
DEFAULT_CHECKLIST = (
    "Veto-г баг, дасгалжуулагчтай баталгаажуулах",
    "Скаутингийн клипүүдийг бүгдийг үзсэн",
    "Pistol төлөвлөгөөг газрын зураг бүрт давтсан",
    "Хариу төлөвлөгөөг scrim-д туршсан",
    "Timeout-ийн «хэрэв … бол» жагсаалтыг IGL-тэй тохирсон",
    "Тоглолтын өдрийн халаалтын хуваарь",
)
# A stored Match this close to the start is taken for this one.
LINK_BEFORE = timedelta(days=2)
LINK_AFTER = timedelta(days=3)


def naive_utc(value: datetime) -> datetime:
    """What the database keeps: naive UTC."""
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value


def link(u: UpcomingMatch) -> None:
    """Point at the stored Match between the two Teams nearest the start, if any."""
    if u.match_id is not None:
        return
    found = (
        db()
        .scalars(
            select(Match).where(
                or_(
                    and_(Match.team1_id == u.team_id, Match.team2_id == u.opponent_id),
                    and_(Match.team1_id == u.opponent_id, Match.team2_id == u.team_id),
                ),
                Match.played_at >= u.starts_at - LINK_BEFORE,
                Match.played_at <= u.starts_at + LINK_AFTER,
            )
        )
        .all()
    )
    if found:
        u.match_id = min(found, key=lambda m: abs((m.played_at - u.starts_at).total_seconds())).id


def read(u: UpcomingMatch) -> dict:
    session = db()
    team, opponent = session.get(Team, u.team_id), session.get(Team, u.opponent_id)
    return {
        "id": u.id,
        "team": {"id": team.id, "name": team.name},
        "opponent": {"id": opponent.id, "name": opponent.name},
        "starts_at": u.starts_at,
        "best_of": u.best_of,
        "tournament": u.tournament,
        "match_id": u.match_id,
        "checklist": u.checklist or [],
        "counters": u.counters or [],
    }


def listing(workspace_id: int, team_id: int | None, *, past: bool = False) -> list[UpcomingMatch]:
    now = datetime.now(UTC).replace(tzinfo=None)
    q = select(UpcomingMatch).where(UpcomingMatch.workspace_id == workspace_id)
    if team_id is not None:
        q = q.where(UpcomingMatch.team_id == team_id)
    if not past:
        q = q.where(UpcomingMatch.starts_at >= now - timedelta(hours=6))
    return list(db().scalars(q.order_by(UpcomingMatch.starts_at)))


def for_fixture(workspace_id: int, team_id: int, opponent_id: int) -> UpcomingMatch | None:
    """The next Upcoming match of this Fixture, for its Game Plan."""
    now = datetime.now(UTC).replace(tzinfo=None)
    return db().scalar(
        select(UpcomingMatch)
        .where(
            UpcomingMatch.workspace_id == workspace_id,
            UpcomingMatch.team_id == team_id,
            UpcomingMatch.opponent_id == opponent_id,
            UpcomingMatch.starts_at >= now - timedelta(hours=6),
        )
        .order_by(UpcomingMatch.starts_at)
        .limit(1)
    )
