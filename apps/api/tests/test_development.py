# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""Development plans: goals with progress read from Match Maps and Scrims (RV-9)."""

import datetime as dt

from app.models import DevelopmentGoal, MatchKind, User, UserRole
from app.security import create_access_token, hash_password
from app.services import dbctx, development, scope
from tests.test_gameplan import _map, league, memory_cache  # noqa: F401
from tests.test_uploads import _private


def _login(db, workspace, player):
    user = User(username=f"p{player.id}", password_hash=hash_password("x" * 12),
                workspace=workspace, role=UserRole.PLAYER, player_id=player.id)  # fmt: skip
    db.add(user)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_a_goal_reads_its_progress_from_the_maps(client, db, auth, league, workspace):
    star = league["players"][league["a"].id][0]
    body = {"kpi": "kast_pct", "target": 70.0, "start_on": "2026-08-01", "due_on": "2026-12-01"}
    made = client.post(f"/players/{star.steamid}/goals", json=body, headers=auth)
    assert made.status_code == 201, made.text
    goal = made.json()
    # The league's maps give player 0 KAST in every Round he played (j < 3).
    assert goal["progress"]["maps"] == 2 and goal["progress"]["value"] == 100.0
    assert goal["progress"]["verdict"] == "reached" and goal["label"] == "KAST"

    plan = client.get(f"/players/{star.steamid}/goals", headers=auth).json()
    assert [g["id"] for g in plan["goals"]] == [goal["id"]] and plan["kpis"]
    done = client.patch(f"/goals/{goal['id']}", json={"status": "done"}, headers=auth).json()
    assert done["status"] == "done"
    assert client.delete(f"/goals/{goal['id']}", headers=auth).status_code == 204
    assert db.query(DevelopmentGoal).count() == 0


def test_a_player_reads_only_his_own_plan(client, db, auth, league, workspace):
    me, other = league["players"][league["a"].id][:2]
    them = _login(db, workspace, me)
    client.post(f"/players/{me.steamid}/goals", json={"kpi": "adr", "target": 90}, headers=auth)
    mine = client.get(f"/players/{me.steamid}/goals", headers=them).json()
    assert len(mine["goals"]) == 1 and mine["suggestions"] == [] and mine["kpis"] == []
    assert client.get(f"/players/{other.steamid}/goals", headers=them).status_code == 404
    added = client.post(
        f"/players/{me.steamid}/goals", json={"kpi": "adr", "target": 1}, headers=them
    )
    assert added.status_code == 403


def test_his_scrims_count_toward_his_development(db, league, workspace):
    a, b, p = league["a"], league["b"], league["players"]
    star = p[a.id][0]
    scope.bind(db, workspace.id)
    with dbctx.using(db):
        before = development.measure(star, "adr", None)["maps"]
    _private(db, workspace, MatchKind.SCRIM, a, b, p, day=6)
    db.info["analysis_memo"] = {}
    scope.bind(db, workspace.id)
    with dbctx.using(db):
        assert development.measure(star, "adr", None)["maps"] == before + 1
        assert development.measure(star, "adr", dt.date(2027, 1, 1))["maps"] == 0


def test_a_goal_needs_a_known_kpi(client, auth, league):
    star = league["players"][league["a"].id][0]
    out = client.post(
        f"/players/{star.steamid}/goals", json={"kpi": "nope", "target": 1}, headers=auth
    )
    assert out.status_code == 400
