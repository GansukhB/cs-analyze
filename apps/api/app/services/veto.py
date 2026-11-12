"""Reading and keeping a Match's Veto (CONTEXT.md) from its HLTV match page.

The page shows the Veto in ``.veto-box`` blocks (verified on the live site,
2026-11-12): one holds the format line ("Best of 3 (LAN)", then the stage), the
other one ``<div>`` per step::

    1. Chinggis Warriors removed Anubis
    3. Chinggis Warriors picked Ancient
    7. Nuke was left over

Older pages write the steps into the format block's text instead, so every line
of every block is read the same way. The page names the two Teams in
``.teamsBox`` with their ``/team/<id>`` links, which is how a step's Team is
told apart from the other's (a step names a Team as the page displays it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Match, MatchVeto, Team, VetoAction
from app.models.base import utcnow

_STEP = re.compile(r"^\s*(\d+)\.\s+(.+?)\s+(removed|picked)\s+(.+?)\s*$")
_LEFT = re.compile(r"^\s*(\d+)\.\s+(.+?)\s+was left over\s*$")
_BEST_OF = re.compile(r"Best of (\d)", re.I)
_TEAM_HREF = re.compile(r"^/team/(\d+)/")

# JavaScript run on the match page: the blocks' text and the two Teams.
PAGE_JS = """() => ({
    boxes: Array.from(document.querySelectorAll('.veto-box')).map(b => b.innerText || ''),
    names: Array.from(document.querySelectorAll('.teamsBox .teamName'))
        .map(e => (e.innerText || '').trim()),
    links: Array.from(document.querySelectorAll('.teamsBox a[href^="/team/"]'))
        .map(a => a.getAttribute('href')),
})"""


@dataclass(frozen=True)
class Step:
    step: int
    action: str  # VetoAction
    map: str  # de_ancient
    side: int | None  # 1 or 2, the page's order; None for the decider or a name not matched
    team_name: str


@dataclass
class PageVeto:
    best_of: int | None = None
    lan: bool | None = None
    teams: list[tuple[str, int | None]] = field(default_factory=list)  # (name, HLTV id)
    steps: list[Step] = field(default_factory=list)


def map_name(display: str) -> str:
    """HLTV's "Dust2" or "Ancient" as the demo header name ``de_dust2``."""
    return "de_" + re.sub(r"[^a-z0-9]", "", display.casefold())


def _side(name: str, teams: list[tuple[str, int | None]]) -> int | None:
    key = name.casefold()
    for i, (team, _) in enumerate(teams, start=1):
        if team.casefold() == key:
            return i
    for i, (team, _) in enumerate(teams, start=1):
        if team and (team.casefold().startswith(key) or key.startswith(team.casefold())):
            return i
    return None


def parse(page: dict) -> PageVeto:
    """What :data:`PAGE_JS` read, as a Veto. A page with no steps gives none."""
    names = [n for n in page.get("names") or []]
    links = [h for h in page.get("links") or []]
    teams = []
    for i, name in enumerate(names[:2]):
        m = _TEAM_HREF.match(links[i] or "") if i < len(links) else None
        teams.append((name, int(m.group(1)) if m else None))
    out = PageVeto(teams=teams)
    seen: set[int] = set()
    for box in page.get("boxes") or []:
        if out.best_of is None and (m := _BEST_OF.search(box)):
            out.best_of = int(m.group(1))
        if out.lan is None:
            if "(LAN)" in box:
                out.lan = True
            elif "(Online)" in box:
                out.lan = False
        for line in box.splitlines():
            if m := _STEP.match(line):
                n, team, verb, game_map = m.groups()
                action = VetoAction.BAN if verb == "removed" else VetoAction.PICK
                step = Step(int(n), action, map_name(game_map), _side(team, teams), team)
            elif m := _LEFT.match(line):
                n, game_map = m.groups()
                step = Step(int(n), VetoAction.DECIDER, map_name(game_map), None, "")
            else:
                continue
            if step.step not in seen:
                seen.add(step.step)
                out.steps.append(step)
    out.steps.sort(key=lambda s: s.step)
    return out


def _team_row(db: Session, match: Match, side: int | None, teams) -> Team | None:
    if side is None:
        return None
    name, hltv_id = teams[side - 1]
    if hltv_id is not None:
        found = db.scalar(select(Team).where(Team.hltv_id == hltv_id))
        if found is not None:
            return found
    for team in (match.team1, match.team2):
        if team is not None and team.name.casefold() == name.casefold():
            return team
    return None


def record(db: Session, match: Match, veto: PageVeto) -> int:
    """Keep what the page said (its steps replace any kept before); commits.
    Returns how many steps were kept."""
    db.execute(delete(MatchVeto).where(MatchVeto.match_id == match.id))
    for s in veto.steps:
        team = _team_row(db, match, s.side, veto.teams)
        hltv_id = veto.teams[s.side - 1][1] if s.side else None
        db.add(
            MatchVeto(
                match_id=match.id,
                step=s.step,
                action=s.action,
                map=s.map,
                team_id=team.id if team else None,
                team_hltv_id=hltv_id,
                team_name=s.team_name[:120],
            )
        )
    if veto.best_of is not None:
        match.best_of = veto.best_of
    if veto.lan is not None:
        match.lan = veto.lan
    match.veto_checked_at = utcnow()
    db.commit()
    return len(veto.steps)
