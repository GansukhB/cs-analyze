# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""A Player login's own page and what else it may open (WS-4)."""

import gzip
import json

import pytest
from sqlalchemy import select

from app.models import MatchMap, MatchMapReview, User, UserRole
from app.security import create_access_token, hash_password
from app.services import review
from tests.test_gameplan import _map, league, memory_cache  # noqa: F401


@pytest.fixture
def player_login(db, league, workspace):
    a = league["a"]
    me = league["players"][a.id][0]
    user = User(
        username="A0", password_hash=hash_password("x" * 12), workspace=workspace,
        role=UserRole.PLAYER, player_id=me.id,
    )  # fmt: skip
    db.add(user)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}, me


def _review(db, mm: MatchMap, sid: str):
    payload = {
        "players": [{"sid": sid, "name": "A0"}],
        "rounds": [{"n": 1, "sides": {sid: "ct"}, "swing": {sid: -0.1}}],
        "findings": [
            {"code": "untraded", "round": 1, "t": 30.0, "side": "ct", "sids": [sid],
             "swing": -0.25, "facts": {}},
            {"code": "entry", "round": 1, "t": 12.0, "side": "ct", "sids": [sid],
             "swing": 0.2, "facts": {}},
            {"code": "advantage_lost", "round": 1, "t": 50.0, "side": "ct", "sids": [sid, "9"],
             "swing": -0.9, "facts": {"deaths": [{"sid": sid, "swing": -0.05}]}},
            {"code": "time_out", "round": 1, "t": 115.0, "side": "ct", "sids": [sid],
             "swing": -0.5, "facts": {}},
        ],
    }  # fmt: skip
    db.add(
        MatchMapReview(
            match_map_id=mm.id,
            version=review.version(),
            payload=gzip.compress(json.dumps(payload).encode()),
        )
    )
    db.commit()


def test_my_page_has_my_maps_and_focus_points(client, db, league, player_login):
    auth, me = player_login
    played = db.scalars(select(MatchMap).order_by(MatchMap.id)).first()
    _review(db, played, str(me.steamid))
    out = client.get("/me/overview", headers=auth)
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["player"]["steamid"] == str(me.steamid)
    assert len(body["maps"]) == 2  # Alpha played two of the three Match Maps
    # The lost advantage costs this Player only their own death; the time-out is the Team's.
    assert [(f["code"], f["swing"]) for f in body["focus"]] == [
        ("untraded", -0.25), ("advantage_lost", -0.05),
    ]  # fmt: skip
    assert [f["code"] for f in body["keep"]] == ["entry"]
    assert body["focus"][0]["swing"] == -0.25


def test_a_player_opens_only_their_own(client, db, league, player_login):
    auth, me = player_login
    mine = {
        m.match_id
        for m in db.scalars(select(MatchMap))
        if league["a"].id in (m.team1_id, m.team2_id)
    }
    other = {m.match_id for m in db.scalars(select(MatchMap))} - mine
    assert client.get(f"/matches/{min(mine)}", headers=auth).status_code == 200
    assert client.get(f"/matches/{min(other)}", headers=auth).status_code == 404
    assert client.get(f"/players/{me.steamid}", headers=auth).status_code == 200
    stranger = league["players"][league["b"].id][0]
    assert client.get(f"/players/{stranger.steamid}", headers=auth).status_code == 404
    assert client.get("/teams", headers=auth).status_code == 403
    assert client.get("/gameplan/teams", headers=auth).status_code == 403


def test_staff_without_a_player_has_no_own_page(client, auth):
    assert client.get("/me/overview", headers=auth).status_code == 404
