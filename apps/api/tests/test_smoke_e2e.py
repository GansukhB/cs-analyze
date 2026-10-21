"""The five main paths in a real browser, against a running stack (OPS-9).

Opt-in, since it needs the apps running with data:

    CS_ANALYZE_SMOKE_WEB=http://localhost:5173 CS_ANALYZE_SMOKE_API=http://localhost:8000 \\
    CS_ANALYZE_SMOKE_TOKEN=<a Staff JWT> npm run test:api -- tests/test_smoke_e2e.py

The token signs the browser in (the login form itself is not driven, so no
password is typed). Each path must render its page's own heading with no
console error: the Scout form, a Game Plan, a Match with its Review, a Player
page, the Briefings.
"""

import json
import os
import urllib.request

import pytest

WEB = os.environ.get("CS_ANALYZE_SMOKE_WEB", "").rstrip("/")
API = os.environ.get("CS_ANALYZE_SMOKE_API", "").rstrip("/")
TOKEN = os.environ.get("CS_ANALYZE_SMOKE_TOKEN", "")

pytestmark = pytest.mark.skipif(
    not (WEB and API and TOKEN), reason="set CS_ANALYZE_SMOKE_WEB, _API and _TOKEN"
)


def _get(path: str):
    request = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(request, timeout=60) as res:  # noqa: S310 (a URL the tester set)
        return json.loads(res.read())


@pytest.fixture(scope="module")
def paths() -> list[tuple[str, str]]:
    teams = sorted(_get("/teams")["teams"], key=lambda t: -t["maps"])
    a, b = teams[0], teams[1]
    team = _get(f"/teams/{a['id']}")
    match = next(r for r in team["results"] if r["n_parsed"])
    player = team["players"][0]
    return [
        ("/", "Who are we playing?"),
        (f"/gameplan/{a['id']}/vs/{b['id']}", a["name"]),
        (f"/matches/{match['match_id']}", a["name"]),
        (f"/players/{player['steamid']}", player["name"]),
        ("/briefings", "Briefing"),
    ]


def test_the_main_paths_render(paths):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chromium")
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(WEB + "/")
        page.wait_for_load_state("networkidle")
        page.evaluate("t => localStorage.setItem('cs-analyze.token', t)", TOKEN)
        for path, text in paths:
            page.goto(WEB + path)
            # The page's own heading: a Team's name is in the nav bar too.
            page.locator("h1", has_text=text).first.wait_for(timeout=60_000)
        browser.close()
    assert errors == []
