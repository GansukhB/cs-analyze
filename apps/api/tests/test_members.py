"""A Workspace's people: invites, resets, roles and the last Staff (WS-3)."""

from datetime import timedelta

from app.models import Invite, Player, User, Workspace
from app.security import create_access_token, hash_password
from tests.conftest import login


def _staff(db, workspace, name="Tuul"):
    other = User(username=name, password_hash=hash_password("x" * 12), workspace=workspace)
    db.add(other)
    db.commit()
    return other


def test_a_player_invite_makes_a_player_login_once(client, db, auth, workspace):
    player = Player(steamid=76561198000000001, name="Bart4k")
    db.add(player)
    db.commit()
    made = client.post(
        "/workspace/invites",
        json={"role": "player", "player_steamid": str(player.steamid)},
        headers=auth,
    )
    assert made.status_code == 201, made.text
    token = made.json()["token"]
    assert len(token) > 20 and db.query(Invite).one().token_hash != token

    seen = client.get(f"/invites/{token}").json()
    assert seen == {
        "workspace": workspace.name,
        "role": "player",
        "player": "Bart4k",
        "username": "",
    }
    short = client.post(f"/invites/{token}/accept", json={"username": "bart", "password": "short"})
    assert short.status_code == 400
    ok = client.post(f"/invites/{token}/accept", json={"username": "bart", "password": "x" * 10})
    assert ok.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {ok.json()['access_token']}"})
    assert me.json()["role"] == "player" and me.json()["player_id"] == player.id
    assert client.get(f"/invites/{token}").status_code == 404
    again = client.post(
        f"/invites/{token}/accept", json={"username": "bart2", "password": "x" * 10}
    )
    assert again.status_code == 400
    listed = client.get("/workspace/members", headers=auth).json()
    assert {m["username"] for m in listed["members"]} == {"Bat", "bart"} and listed["invites"] == []


def test_an_expired_invite_is_gone(client, db, auth):
    token = client.post("/workspace/invites", json={"role": "staff"}, headers=auth).json()["token"]
    row = db.query(Invite).one()
    row.expires_at -= timedelta(days=8)
    db.commit()
    assert client.get(f"/invites/{token}").status_code == 404


def test_a_reset_link_sets_a_new_password(client, db, auth, user):
    other = _staff(db, user.workspace)
    made = client.post("/workspace/invites", json={"user_id": other.id}, headers=auth).json()
    assert made["username"] == "Tuul"
    out = client.post(
        f"/invites/{made['token']}/accept", json={"username": "ignored", "password": "y" * 11}
    )
    assert out.status_code == 200
    assert login(client, "Tuul", "y" * 11).status_code == 200
    assert db.query(User).count() == 2


def test_the_last_staff_stays(client, db, auth, user):
    me = client.patch(f"/workspace/members/{user.id}", json={"is_active": False}, headers=auth)
    assert me.status_code == 400
    other = _staff(db, user.workspace)
    assert (
        client.patch(
            f"/workspace/members/{other.id}", json={"is_active": False}, headers=auth
        ).json()["is_active"]
        is False
    )
    # Bat is now the only active Staff: Tuul's own token can't take that away either.
    db.refresh(other)
    other.is_active = True
    db.commit()
    tuul = {"Authorization": f"Bearer {create_access_token(other.id)}"}
    client.patch(f"/workspace/members/{other.id}", json={"role": "player"}, headers=auth)
    assert (
        client.patch(
            f"/workspace/members/{user.id}", json={"role": "player"}, headers=tuul
        ).status_code
        == 403
    )


def test_another_workspaces_member_is_not_found(client, db, auth):
    other = Workspace(name="Other club")
    db.add(other)
    db.commit()
    stranger = _staff(db, other, name="Stranger")
    out = client.patch(f"/workspace/members/{stranger.id}", json={"is_active": False}, headers=auth)
    assert out.status_code == 404
    assert (
        client.post("/workspace/invites", json={"user_id": stranger.id}, headers=auth).status_code
        == 400
    )


def test_what_staff_did_is_in_the_audit_log_without_secrets(client, db, auth, workspace):
    """WS-7: an invite made and used, then the new login deactivated."""
    player = Player(steamid=76561198000000002, name="nin9")
    db.add(player)
    db.commit()
    made = client.post("/workspace/invites", headers=auth,
                       json={"role": "player", "player_steamid": str(player.steamid)})  # fmt: skip
    token = made.json()["token"]
    client.post(f"/invites/{token}/accept", json={"username": "nin9", "password": "x" * 10})
    member = db.query(User).filter_by(username="nin9").one()
    client.patch(f"/workspace/members/{member.id}", headers=auth, json={"is_active": False})
    log = client.get("/workspace/audit", headers=auth).json()
    assert [e["action"] for e in log] == ["member.change", "invite.accept", "invite.create"]
    assert log[0]["actor"] == "Bat" and log[0]["subject"] == "nin9"
    assert log[0]["detail"] == {"is_active": False}
    assert log[1]["actor"] == "nin9"
    assert token not in str(log)  # never a secret
    them = {"Authorization": f"Bearer {create_access_token(member.id)}"}
    assert client.get("/workspace/audit", headers=them).status_code in (401, 403)


def test_the_week_is_the_template_filled_from_the_workspace(client, db, auth, workspace):
    """RV-11: no my team, no week; with one, seven days and its latest Matches."""
    from app.models import Team, WorkspaceTeam

    assert client.get("/workspace/week", headers=auth).json()["team"] is None
    team = Team(name="Huns")
    db.add(team)
    db.flush()
    db.add(WorkspaceTeam(workspace_id=workspace.id, team_id=team.id))
    db.commit()
    week = client.get("/workspace/week", headers=auth).json()
    assert week["team"]["name"] == "Huns" and len(week["days"]) == 7
    assert week["days"][0]["blocks"] == ["review", "goals"] and week["days"][6]["blocks"] == []
    assert week["review"] == [] and week["goals"] == [] and week["prep"] == []
