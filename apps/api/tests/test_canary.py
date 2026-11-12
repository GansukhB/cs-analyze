"""The HLTV selector canary (docs/plans/11 OPS-9), against a fake client."""

import datetime as dt
from types import SimpleNamespace

from app.services import canary


class FakeClient:
    def __init__(self, team=True, matches=3, demo=True, score="2 - 1", veto=True):
        self.team, self.n, self.demo, self.score, self.veto = team, matches, demo, score, veto

    def resolve_team(self, name):
        return SimpleNamespace(id=9565, name=name) if self.team else None

    def latest_matches(self, team, limit):
        when = dt.datetime(2026, 10, 1, tzinfo=dt.UTC)
        return [SimpleNamespace(team1="A", team2="B", score=self.score, played_at=when)
                for _ in range(min(self.n, limit))]  # fmt: skip

    def demo_link(self, match):
        return "/download/demo/1" if self.demo else None

    def match_page(self, match):
        from app.services import veto
        from app.services.client import MatchPage

        boxes = ["1. A removed Nuke\n2. B removed Anubis\n3. Mirage was left over"]
        page = {"boxes": boxes if self.veto else [], "names": ["A", "B"], "links": []}
        return MatchPage(demo=self.demo_link(match), veto=veto.parse(page))


def test_the_canary_names_what_broke():
    assert canary.check(FakeClient()) == []
    assert canary.check(FakeClient(team=False))[0].startswith("search:")
    assert canary.check(FakeClient(matches=0))[0].startswith("results: no matches")
    assert canary.check(FakeClient(demo=False)) == [
        "match page: no demo link on the latest matches (a[href^='/download/demo/'])"
    ]
    assert canary.check(FakeClient(score="")) == ["results: no score read (.result-score)"]
    assert canary.check(FakeClient(veto=False)) == [
        "match page: no Veto read on the latest matches (.veto-box)"
    ]
