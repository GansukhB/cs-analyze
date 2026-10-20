"""Models, in the same layers as cstat's ``hltv`` app, plus the User.

``source``   what HLTV said and which files are on disk (scraped, downloaded).
``analysis`` what parsing a demo produced (rounds, events, rollups).
``jobs``     background analysis runs, their story and their pictures.
``workspace`` one club's private space, its Users and its my teams.

Everything is re-exported here, so ``from app.models import Match, KillEvent``
works regardless of which module a model lives in. Importing this package also
registers every table on ``Base.metadata``, which Alembic relies on.
"""

from app.models.analysis import (
    BombEvent,
    BombEventType,
    BuyType,
    DamageEvent,
    GameMap,
    GrenadeThrow,
    GrenadeType,
    KillEvent,
    MapRoster,
    MatchMap,
    MatchMapReview,
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
    ReplayRound,
    Round,
    RoundSnapshot,
    Side,
    SnapshotMoment,
    TeamAlias,
    TickDataset,
)
from app.models.assistant import AssistantUsage
from app.models.base import TimestampMixin
from app.models.jobs import (
    AnalysisArtifact,
    AnalysisEvent,
    AnalysisJob,
    ArtifactKind,
    EventLevel,
    JobKind,
    JobStage,
    JobStatus,
    analysis_job_matches,
)
from app.models.results import SeriesResult, VrsStanding
from app.models.source import Demo, Match, Team, Tournament
from app.models.user import User
from app.models.workspace import UserRole, Workspace, WorkspaceTeam

__all__ = [
    "TimestampMixin",
    "User",
    "UserRole",
    "AssistantUsage",
    "SeriesResult",
    "VrsStanding",
    "Workspace",
    "WorkspaceTeam",
    # source
    "Team",
    "Tournament",
    "Match",
    "Demo",
    # analysis
    "Side",
    "Player",
    "PlayerAlias",
    "TeamAlias",
    "GameMap",
    "MatchMap",
    "MapRoster",
    "Round",
    "RoundSnapshot",
    "SnapshotMoment",
    "KillEvent",
    "DamageEvent",
    "BombEvent",
    "BombEventType",
    "BuyType",
    "GrenadeThrow",
    "GrenadeType",
    "PlayerRound",
    "PlayerMap",
    "PlayerMatch",
    "TickDataset",
    "PlayerMapPosition",
    "PositionKind",
    "PlayerMapWeapon",
    "PlayerMapUtility",
    "PlayerMapRoute",
    "PlayerMapDuel",
    "MatchMapReview",
    "ReplayRound",
    # jobs
    "AnalysisJob",
    "JobKind",
    "JobStatus",
    "JobStage",
    "analysis_job_matches",
    "AnalysisEvent",
    "EventLevel",
    "AnalysisArtifact",
    "ArtifactKind",
]
