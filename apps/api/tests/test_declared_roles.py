# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""Staff declare their Players' roles; the role picture takes them as the truth (PL-4)."""

from app.models import User, UserRole
from app.security import create_access_token, hash_password
from app.services import dbctx, mapstrategy, roles, scope
from tests.test_gameplan import _map, league, memory_cache  # noqa: F401


def test_a_declared_role_wins_and_keeps_the_inferred_one(client, db, auth, league, workspace):
    a = league["a"]
    star = league["players"][a.id][0]
    out = client.put(
        f"/players/{star.steamid}/roles", json={"side": "ct", "role": "anchor"}, headers=auth
    )
    assert out.status_code == 200, out.text
    assert [(r["side"], r["role"]) for r in out.json()["roles"]] == [("ct", "anchor")]
    assert {c["role"] for c in out.json()["choices"]["ct"]} >= {"anchor", "awper"}

    db.info.pop(scope.KEY, None)
    scope.bind(db, workspace.id)
    with dbctx.using(db):
        picture = roles.team_roles(a, mapstrategy.maps_in_window(a))
    mine = next(p for p in picture["players"] if p["player_id"] == star.id)
    ct = mine["roles"]["ct"]
    assert ct["role"] == "anchor" and ct["confidence"] == "declared" and "inferred" in ct
    assert sum(s["share"] for s in mine["roles"]["t"]["shares"]) <= 1.01

    cleared = client.put(
        f"/players/{star.steamid}/roles", json={"side": "ct", "role": ""}, headers=auth
    )
    assert cleared.json()["roles"] == []


def test_a_role_must_exist_on_its_side(client, auth, league):
    star = league["players"][league["a"].id][0]
    bad = client.put(
        f"/players/{star.steamid}/roles", json={"side": "ct", "role": "entry"}, headers=auth
    )
    assert bad.status_code == 400


def test_a_player_login_cannot_declare(client, db, league, workspace):
    star = league["players"][league["a"].id][0]
    login = User(username="A0", password_hash=hash_password("x" * 12), workspace=workspace,
                 role=UserRole.PLAYER, player_id=star.id)  # fmt: skip
    db.add(login)
    db.commit()
    them = {"Authorization": f"Bearer {create_access_token(login.id)}"}
    out = client.put(
        f"/players/{star.steamid}/roles", json={"side": "t", "role": "lurker"}, headers=them
    )
    assert out.status_code == 403
