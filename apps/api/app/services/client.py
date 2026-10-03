"""Reading teams, results and demo links off HLTV.org.

Every selector here was verified against the live site. HLTV has no public API
(the old ``/searchbar/anything`` JSON endpoint now 404s after their redesign),
so this scrapes rendered HTML:

* team lookup  -- ``/search?query=<term>``, teams are the anchors carrying
  ``data-result-type="TEAM"`` inside ``div.search`` (see :meth:`search_teams`)
* match list   -- ``/results?team=<id>``, newest first, one ``.result-con`` per
  match inside ``.allres``
* demo link    -- on the match page, ``a[href^='/download/demo/']``
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from .browser import HltvBrowser

_TEAM_HREF = re.compile(r"^/team/(\d+)/([^/?#]+)")
_MATCH_HREF = re.compile(r"^/matches/(\d+)/([^/?#]+)")


@dataclass(frozen=True)
class Team:
    id: int
    name: str
    slug: str

    @property
    def url(self) -> str:
        return f"/team/{self.id}/{self.slug}"


@dataclass(frozen=True)
class Match:
    id: int
    slug: str
    team1: str
    team2: str
    score: str
    event: str
    played_at: dt.datetime | None

    @property
    def url(self) -> str:
        return f"/matches/{self.id}/{self.slug}"

    @property
    def label(self) -> str:
        when = self.played_at.date().isoformat() if self.played_at else "unknown date"
        return f"{self.team1} {self.score} {self.team2} — {self.event} ({when})"


class HltvClient:
    """Thin read layer over a live :class:`HltvBrowser`."""

    def __init__(self, browser: HltvBrowser):
        self.browser = browser

    # -- teams -------------------------------------------------------------
    def search_teams(self, term: str) -> list[Team]:
        """Teams matching ``term``, in HLTV's own relevance order.

        The results page carries one ``table.table`` per *kind* of result --
        Player, Team, Article -- and which kinds appear depends on the term. So
        "the first table" is not the team table: searching ``HEROIC`` puts the
        player Scott 'Heroic' Cayeta above the five HEROIC teams, and reading the
        first table returned no teams at all for a term with five of them.

        Each result anchor says what it is (``data-result-type="TEAM"``), so that
        is what is read, and it is order-independent by construction. The table
        whose header cell says "Team" is kept as a fallback for the day HLTV
        drops the attribute.

        Scoped to ``div.search`` throughout: the page's sidebar and top matches
        link to teams too, and unscoped this picks up Spirit, Falcons and FURIA
        on every search regardless of the term.
        """
        page = self.browser.open(f"/search?query={term.strip().replace(' ', '+')}")
        rows = page.evaluate(
            """() => {
                const box = document.querySelector('div.search');
                if (!box) return [];
                const read = a => ({
                    href: a.getAttribute('href'),
                    name: (a.innerText || '').trim(),
                });
                const tagged = Array.from(box.querySelectorAll(
                    "a[data-result-type='TEAM'][href^='/team/']"));
                if (tagged.length) return tagged.map(read);
                const table = Array.from(box.querySelectorAll('table.table')).find(
                    t => /team/i.test(t.querySelector('.table-header')?.innerText || ''));
                return table
                    ? Array.from(table.querySelectorAll("a[href^='/team/']")).map(read)
                    : [];
            }"""
        )

        teams, seen = [], set()
        for row in rows:
            m = _TEAM_HREF.match(row["href"] or "")
            if not m:
                continue
            team_id = int(m.group(1))
            if team_id in seen:
                continue
            seen.add(team_id)
            teams.append(Team(id=team_id, name=row["name"] or m.group(2), slug=m.group(2)))
        return teams

    def resolve_team(self, term: str) -> Team | None:
        """The team HLTV ranks first for ``term``, or None if it found none.

        HLTV's own ordering decides, rather than an exact name match here. A
        club's name is not unique on that site -- ``HEROIC`` returns five teams,
        three of them literally named some casing of "Heroic" -- and the extra
        ones are dead rosters and academy sides that happen to share the name.
        HLTV ranks the live club first, so preferring an exact string match over
        that ordering picks the defunct team precisely when there is a choice to
        get wrong.
        """
        teams = self.search_teams(term)
        return teams[0] if teams else None

    # -- matches -----------------------------------------------------------
    def latest_matches(self, team: Team, limit: int) -> list[Match]:
        """The ``limit`` most recently played matches for ``team``."""
        page = self.browser.open(f"/results?team={team.id}")
        rows = page.evaluate(
            """() => Array.from(document.querySelectorAll('.allres .result-con')).map(c => {
                const a = c.querySelector("a[href^='/matches/']");
                const names = Array.from(c.querySelectorAll('.team'))
                    .map(e => (e.innerText || '').trim()).filter(Boolean);
                return {
                    href: a ? a.getAttribute('href') : null,
                    unix: c.getAttribute('data-zonedgrouping-entry-unix'),
                    team1: names[0] || '',
                    team2: names[1] || '',
                    score: (c.querySelector('.result-score')?.innerText || '').trim(),
                    event: (c.querySelector('.event-name')?.innerText || '').trim(),
                };
            })"""
        )

        matches, seen = [], set()
        for row in rows:
            m = _MATCH_HREF.match(row["href"] or "")
            if not m:
                continue
            match_id = int(m.group(1))
            if match_id in seen:
                continue
            seen.add(match_id)

            played_at = None
            if row.get("unix"):
                try:
                    played_at = dt.datetime.fromtimestamp(int(row["unix"]) / 1000, tz=dt.UTC)
                except (TypeError, ValueError):
                    played_at = None

            matches.append(
                Match(
                    id=match_id,
                    slug=m.group(2),
                    team1=row["team1"],
                    team2=row["team2"],
                    score=row["score"].replace("\n", " ").strip(),
                    event=row["event"],
                    played_at=played_at,
                )
            )
            if len(matches) >= limit:
                break
        return matches

    # -- demos -------------------------------------------------------------
    def demo_link(self, match: Match) -> str | None:
        """The ``/download/demo/<id>`` path for ``match``, or None if absent.

        Not every match has a demo: very recent or very old matches, and some
        online qualifiers, simply never get one published.
        """
        page = self.browser.open(match.url)
        return page.evaluate(
            """() => {
                const a = document.querySelector("a[href^='/download/demo/']");
                return a ? a.getAttribute('href') : null;
            }"""
        )
