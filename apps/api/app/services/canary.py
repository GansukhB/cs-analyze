"""Whether HLTV still reads the way the Scout expects (docs/plans/11 OPS-9).

HLTV has no API: the Scout reads its pages through selectors (``client.py``).
If HLTV changes its markup, a Scout ends "SUCCESS, 0 Matches" and nobody
notices. The canary reads one known Team the Scout's way: found by name, its
latest Matches listed with their teams and scores, and a demo link on one of
them. Each step that fails is named. Run weekly (``npm run hltv:canary``); it
opens three HLTV pages, so never more often.
"""

from __future__ import annotations

DEFAULT_TEAM = "Vitality"
MATCHES = 3


def check(client, team_name: str = DEFAULT_TEAM) -> list[str]:
    """The problems found, empty when every selector still reads."""
    team = client.resolve_team(team_name)
    if team is None:
        return [f"search: no team found for {team_name!r} (div.search / data-result-type)"]
    problems = []
    matches = client.latest_matches(team, MATCHES)
    if not matches:
        return [f"results: no matches listed for {team.name} (.allres .result-con)"]
    if not all(m.team1 and m.team2 for m in matches):
        problems.append("results: a match without its two teams (.team)")
    if not any(m.score for m in matches):
        problems.append("results: no score read (.result-score)")
    if not any(m.played_at for m in matches):
        problems.append("results: no date read (data-zonedgrouping-entry-unix)")
    # A very recent Match may not have its demo yet: one of them is enough.
    if not any(client.demo_link(m) for m in matches):
        problems.append(
            "match page: no demo link on the latest matches (a[href^='/download/demo/'])"
        )
    return problems
