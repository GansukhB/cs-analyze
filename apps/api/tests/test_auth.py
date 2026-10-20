from tests.conftest import login


def test_login_and_me(client, user):
    response = login(client, "Bat", "correct-horse")
    assert response.status_code == 200
    token = response.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json() == {"id": user.id, "username": "Bat"}


def test_wrong_password(client, user):
    assert login(client, "Bat", "wrong-password").status_code == 401


def test_unknown_user(client):
    assert login(client, "nobody", "whatever").status_code == 401


def test_username_is_case_sensitive(client, user):
    assert login(client, "bat", "correct-horse").status_code == 401


def test_deactivated_user_cannot_login(client, db, user):
    user.is_active = False
    db.commit()
    assert login(client, "Bat", "correct-horse").status_code == 401


def test_deactivation_revokes_existing_token(client, db, user):
    token = login(client, "Bat", "correct-horse").json()["access_token"]
    user.is_active = False
    db.commit()

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 401


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401
    bad = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


def test_job_endpoints_require_token(client):
    job = "00000000-0000-0000-0000-000000000000"
    assert client.get("/home").status_code == 401
    assert client.get("/jobs").status_code == 401
    assert client.post("/jobs", json={}).status_code == 401
    assert client.get(f"/jobs/{job}").status_code == 401
    assert client.post(f"/jobs/{job}/cancel").status_code == 401
    assert client.get("/workers").status_code == 401


def test_failed_sign_ins_are_limited_per_username(client, user):
    from app.routers.auth import FAILURES_PER_USERNAME

    for _ in range(FAILURES_PER_USERNAME):
        assert login(client, "Bat", "wrong").status_code == 401
    # Even the right password waits out the window now.
    blocked = login(client, "Bat", "correct-horse")
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]


def test_a_good_sign_in_clears_the_count(client, user):
    from app.routers.auth import FAILURES_PER_USERNAME

    for _ in range(FAILURES_PER_USERNAME - 1):
        login(client, "Bat", "wrong")
    assert login(client, "Bat", "correct-horse").status_code == 200
    for _ in range(FAILURES_PER_USERNAME - 1):
        assert login(client, "Bat", "wrong").status_code == 401
