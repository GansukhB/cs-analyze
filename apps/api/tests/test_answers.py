"""Stored answers and the warm-up (docs/adr/0014): pages answer at once."""

import dataclasses
import itertools
from datetime import timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.models import (
    AnalysisJob,
    JobKind,
    JobStatus,
    Match,
    MatchMap,
    StoredAnswer,
    Team,
    Workspace,
    WorkspaceTeam,
)
from app.models.base import utcnow
from app.services import answers, heavy, warmer
from tests.test_gameplan import league, memory_cache  # noqa: F401  (fixtures)

calls: list[dict] = []


@answers.kind("test.echo", 1)
def _echo(db, p: dict) -> dict:
    calls.append(p)
    return {"n": p["n"], "computed": len(calls)}


@pytest.fixture(autouse=True)
def _fresh_calls():
    calls.clear()
    team_calls.clear()


def _move_stamp(db):
    """Something a page reads changed (here: a Match stored)."""
    db.add(Match(hltv_id=9999))
    db.commit()


def test_an_answer_is_computed_once_then_read(db):
    first = answers.lookup(db, "test.echo", {"n": 1})
    assert first.computed and first.state == answers.FRESH and first.data["n"] == 1
    again = answers.lookup(db, "test.echo", {"n": 1})
    assert not again.computed and again.state == answers.FRESH and len(calls) == 1
    row = db.scalar(select(StoredAnswer))
    assert row.hits == 1 and row.spec == {"params": {"n": 1}, "scope": {"all": True}}
    # Each set of parameters is its own answer.
    answers.lookup(db, "test.echo", {"n": 2})
    assert len(calls) == 2


def test_after_a_change_the_last_answer_is_read_stale_and_wanted(db, answers_redis):
    answers.lookup(db, "test.echo", {"n": 1})
    _move_stamp(db)
    stale = answers.lookup(db, "test.echo", {"n": 1})
    assert stale.state == answers.STALE and not stale.computed and len(calls) == 1
    db.expire_all()
    row = db.scalar(select(StoredAnswer))
    assert row.wanted_at is not None
    assert answers_redis.store[answers.WAKE]  # the warm-up was woken
    # A Briefing never freezes a stale answer.
    current = answers.lookup(db, "test.echo", {"n": 1}, fresh=True)
    assert current.computed and current.state == answers.FRESH
    db.expire_all()
    assert db.scalar(select(StoredAnswer)).wanted_at is None


def test_the_response_says_whether_it_was_current(client, auth, league):  # noqa: F811
    a, b = league["a"].id, league["b"].id
    first = client.get(f"/gameplan/{a}/vs/{b}/s/maps", headers=auth)
    assert first.headers["X-Answer"] == "fresh" and first.json()["cached"] is False
    second = client.get(f"/gameplan/{a}/vs/{b}/s/maps", headers=auth)
    assert second.json()["cached"] is True and second.json()["data"] == first.json()["data"]
    assert second.headers["X-Answer-At"].endswith("Z")


def test_another_version_is_never_served_and_is_pruned(db, monkeypatch):
    answers.lookup(db, "test.echo", {"n": 1})
    # The page's wording changed: its kind's version moved with it.
    bumped = dataclasses.replace(answers.KINDS["test.echo"], version=2)
    monkeypatch.setitem(answers.KINDS, "test.echo", bumped)
    assert answers.lookup(db, "test.echo", {"n": 1}).computed  # a new key, a new answer
    assert answers.prune(db) == 1
    assert db.scalars(select(StoredAnswer.version)).all() == [2]


def test_answers_nobody_opens_are_forgotten_unless_planned(db):
    answers.lookup(db, "test.echo", {"n": 1})
    answers.lookup(db, "test.echo", {"n": 2})
    old = utcnow() - timedelta(days=answers.FORGET_DAYS + 1)
    db.execute(update(StoredAnswer).values(computed_at=old, last_hit_at=None))
    db.commit()
    keep = answers.hash_of(answers.key_of("test.echo", {"n": 1}, ":all"))
    assert answers.prune(db, {keep}) == 1
    assert db.scalars(select(StoredAnswer.key_hash)).all() == [keep]


def test_live_parts_are_read_on_every_request(client, auth, db, user, league):  # noqa: F811
    a = league["a"]
    db.add(WorkspaceTeam(workspace_id=user.workspace_id, team_id=a.id))
    db.commit()
    url = f"/v2/teams/{a.id}/overview"
    assert client.get(url, headers=auth).json()["jobs"] == []
    db.add(AnalysisJob(my_team_name="Alpha", opponent_name="Bravo", status=JobStatus.QUEUED))
    db.commit()
    again = client.get(url, headers=auth)
    assert again.headers["X-Answer"] == "fresh" and len(again.json()["jobs"]) == 1


# ---------------------------------------------------------------- warm-up ---
@pytest.fixture
def ours(db, user, league):  # noqa: F811
    db.add(WorkspaceTeam(workspace_id=user.workspace_id, team_id=league["a"].id))
    db.commit()
    return league


@pytest.fixture
def factory(db):
    return sessionmaker(bind=db.get_bind(), expire_on_commit=False)


def test_the_plan_puts_the_latest_scout_first(db, ours, monkeypatch):
    a, b, c = ours["a"], ours["b"], ours["c"]
    monkeypatch.setattr(warmer, "MIN_MAPS", 1)
    # Alpha met Bravo most recently; a Scout of Alpha against Charlie just ended.
    assert warmer.opponents(db, a.id, warmer.parsed_map_counts(db)) == [b.id, c.id]
    db.add(AnalysisJob(kind=JobKind.SCOUT, my_team_id=a.id, opponent_id=c.id,
                       status=JobStatus.SUCCESS, finished_at=utcnow()))  # fmt: skip
    db.commit()
    plan = warmer.build_plan(db)
    assert plan.fixtures == [(a.id, c.id), (a.id, b.id)]
    kinds = [it.kind for it in plan.items]
    assert kinds[0] == "v2.overview" and "team.page" in kinds and "gp.veto" in kinds
    # Each Team brings its own pages once, whichever fixtures it is in.
    assert "team.style" in kinds and "gp.heatmap" in kinds and "gp.style" not in kinds
    first_fixture = next(i for i, it in enumerate(plan.items) if it.fixture)
    assert plan.items[first_fixture].fixture == (a.id, c.id)
    assert len({it.digest for it in plan.items}) == len(plan.items)


def test_two_workspaces_with_one_my_team_share_its_fixtures(db, ours, monkeypatch):
    monkeypatch.setattr(warmer, "MIN_MAPS", 1)
    demo = Workspace(name="Demo")
    db.add(demo)
    db.flush()
    db.add(WorkspaceTeam(workspace_id=demo.id, team_id=ours["a"].id))
    db.commit()
    plan = warmer.build_plan(db)
    a, b, c = ours["a"].id, ours["b"].id, ours["c"].id
    assert sorted(plan.fixtures) == [(a, b), (a, c)]
    # Only the veto lab (it reads the Workspace's own Scrims) is computed for each.
    vetoes = [it for it in plan.items if it.kind == "gp.veto"]
    assert len(vetoes) == 4 and len({it.params["workspace_id"] for it in vetoes}) == 2
    assert sum(1 for it in plan.items if it.kind == "gp.header") == 2


def test_a_round_stores_every_planned_page_as_its_page_asks_for_it(
    client, auth, db, ours, factory, monkeypatch
):
    monkeypatch.setattr(warmer, "MIN_MAPS", 1)
    w = warmer.Warmer(factory)
    assert w.round() is True
    assert w.failed == {}
    plan = warmer.build_plan(db)
    stored = answers.stamps(db, [it.digest for it in plan.items])
    assert len(stored) == len(plan.items)
    # Every page then answers from what the warm-up stored, current.
    a, b = ours["a"].id, ours["b"].id
    for url in (
        f"/gameplan/{a}/vs/{b}",
        f"/gameplan/{a}/vs/{b}/s/todo",
        f"/gameplan/{a}/vs/{b}/playbook/de_mirage",
        f"/gameplan/{a}/vs/{b}/style/de_mirage",
        f"/gameplan/{a}/vs/{b}/between",
        f"/v2/teams/{a}/scouting/{b}",
        f"/v2/teams/{a}/overview",
        f"/v2/teams/{a}/owner",
        f"/v2/teams/{a}/self-scout",
        f"/teams/{b}",
    ):
        res = client.get(url, headers=auth)
        assert res.status_code == 200, (url, res.text)
        assert res.headers["X-Answer"] == "fresh", url
    body = {"format": "bo3", "we_start": True, "done": [], "adjust": {}}
    veto = client.post(f"/gameplan/{a}/vs/{b}/veto", headers=auth, json=body)
    assert veto.status_code == 200 and veto.headers["X-Answer"] == "fresh"
    before = db.scalar(select(StoredAnswer.computed_at).order_by(StoredAnswer.id.desc()))
    # Nothing moved: the next round has nothing to do.
    assert w.round() is False
    assert db.scalar(select(StoredAnswer.computed_at).order_by(StoredAnswer.id.desc())) == before
    status = warmer.status()
    assert status["state"] == "idle" and status["fixtures_ready"] == status["fixtures_total"] == 2
    assert warmer.readiness(db, a, [b, ours["c"].id]) == {b: "fresh", ours["c"].id: "fresh"}


def test_a_page_read_stale_is_computed_first(db, factory):
    answers.lookup(db, "test.echo", {"n": 1})
    answers.lookup(db, "test.echo", {"n": 2})
    _move_stamp(db)
    answers.lookup(db, "test.echo", {"n": 2})  # someone is looking at n=2
    w = warmer.Warmer(factory)
    assert w._wanted() is True
    assert [c["n"] for c in calls[2:]] == [2]
    db.expire_all()
    assert db.scalar(select(StoredAnswer).where(StoredAnswer.wanted_at.is_not(None))) is None


def test_the_warm_up_gives_the_permit_to_a_waiting_parse(db, factory, heavy_redis):
    answers.lookup(db, "test.echo", {"n": 1})
    _move_stamp(db)
    w = warmer.Warmer(factory)
    item = warmer.Item("test.echo", {"n": 1}, {"all": True}, "test")
    item.key = answers.key_of("test.echo", {"n": 1}, ":all")
    item.digest = answers.hash_of(item.key)
    heavy_redis.set(heavy.WAITING, "job:x")
    with factory() as s:
        assert w._compute(s, item) is True
    assert w.token is None and heavy_redis.get(heavy.KEY) is None
    # Held by a parse: the warm-up waits rather than compute beside it.
    heavy_redis.set(heavy.KEY, "job:x|t")
    w.stop.set()
    with factory() as s:
        assert w._compute(s, item) is False


def test_what_a_session_remembered_goes_when_the_data_moves(db, factory):
    w = warmer.Warmer(factory)
    item = warmer.Item("test.echo", {"n": 3}, {"all": True}, "test")
    item.key = answers.key_of("test.echo", {"n": 3}, ":all")
    item.digest = answers.hash_of(item.key)
    with factory() as s:
        assert w._compute(s, item) is True
        s.info["analysis_memo"] = {"report": "from before the parse"}
        _move_stamp(db)
        assert w._compute(s, item) is True
        assert "analysis_memo" not in s.info


# ------------------------------------------------- per-Team stamps (ADR 0015) ---
team_calls: list[dict] = []


@answers.kind("test.team", 1, deps=answers.teams("team"))
def _team_echo(db, p: dict) -> dict:
    team_calls.append(p)
    return {"team": p["team"], "computed": len(team_calls)}


_ticks = itertools.count(1)


def _parse_again(db, match_map):
    """The Match Map was parsed again (a Scout's re-parse, a new schema), a few
    seconds after the last: the Pool's stamp reads the second."""
    match_map.parsed_at = utcnow() + timedelta(seconds=5 * next(_ticks))
    db.commit()


def _map_between(db, home, away):
    return db.scalar(
        select(MatchMap).where(MatchMap.team1_id == home.id, MatchMap.team2_id == away.id)
    )


def test_a_parse_of_other_teams_leaves_an_answer_fresh(db, league):  # noqa: F811
    a, b, c = league["a"], league["b"], league["c"]
    answers.lookup(db, "test.team", {"team": a.id})
    pool_before = answers.pool_part(answers.stamp(db, "test.team", {"team": a.id}))
    # Bravo against Charlie: nothing Alpha's page reads, only the Pool moved.
    _parse_again(db, _map_between(db, b, c))
    kept = answers.lookup(db, "test.team", {"team": a.id})
    assert kept.state == answers.FRESH and not kept.computed
    now = answers.stamp(db, "test.team", {"team": a.id})
    assert answers.pool_part(now) != pool_before and answers.is_fresh(kept.stamp, now)
    # Alpha's own Match Map: stale, and wanted.
    _parse_again(db, _map_between(db, a, c))
    moved = answers.lookup(db, "test.team", {"team": a.id})
    assert moved.state == answers.STALE and len(team_calls) == 1


def test_the_game_plan_stamp_moves_with_its_two_teams_only(db, league):  # noqa: F811
    from app.routers.gameplan import fixture_stamp

    a, b, c = league["a"], league["b"], league["c"]
    before = fixture_stamp(db, a.id, c.id)
    _parse_again(db, _map_between(db, a, b))  # Charlie did not play: still Alpha's
    assert fixture_stamp(db, a.id, c.id) != before
    before = fixture_stamp(db, a.id, b.id)
    d, e = Team(name="Delta", hltv_id=40), Team(name="Echo", hltv_id=41)
    db.add_all([d, e])
    db.flush()
    db.add(Match(hltv_id=4000, team1_id=d.id, team2_id=e.id))
    db.commit()
    # A Briefing on Alpha vs Bravo is not refused for a Match of two other Teams.
    assert fixture_stamp(db, a.id, b.id) == before


def test_an_answer_computed_again_the_same_rewrites_its_stamp_only(db, monkeypatch):
    answers.lookup(db, "test.echo", {"n": 7})
    row = db.scalar(select(StoredAnswer))
    packed = []
    real = answers.gzip.compress
    monkeypatch.setattr(
        answers.gzip, "compress", lambda raw, lvl: packed.append(1) or real(raw, lvl)
    )
    calls.clear()  # test.echo says how many times it ran: make it say the same again
    key = answers.key_of("test.echo", {"n": 7}, ":all")
    answers.compute_and_store(db, "test.echo", {"n": 7}, key=key, stamp="new~pool")
    assert packed == []  # the payload was not written again
    db.expire_all()
    again = db.scalar(select(StoredAnswer))
    assert again.stamp == "new~pool" and again.digest == row.digest and again.id == row.id


def test_the_pools_turn_takes_the_oldest_and_none_too_young():
    def item(n):
        it = warmer.Item("test.echo", {"n": n}, {"all": True}, "test")
        it.digest = str(n)
        return it

    now = utcnow()
    old, young, stale_new, stale_old, new = item(1), item(2), item(3), item(4), item(5)
    current = {i.digest: "f~p2" for i in (old, young, stale_new, stale_old, new)}
    current[stale_new.digest] = current[stale_old.digest] = "g~p2"
    stored = {
        old.digest: ("f~p1", now - timedelta(days=2)),
        young.digest: ("f~p1", now - timedelta(minutes=5)),
        stale_new.digest: ("f~p1", now - timedelta(days=1)),
        stale_old.digest: ("f~p1", now - timedelta(days=1)),
    }
    changed = {stale_new.digest: now, stale_old.digest: now - timedelta(hours=3)}
    queue = warmer.order([old, young, stale_new, stale_old, new], [], stored, current, changed)
    # The latest change first, then what was never computed, then the Pool's oldest.
    assert [i.digest for i in queue] == ["3", "4", "5", "1"]
    assert [i.tier for i in queue] == ["stale", "stale", "missing", "pool"]


def test_answers_from_before_per_team_stamps_are_kept_while_their_teams_stand(db, league):  # noqa: F811
    a, b = league["a"], league["b"]
    answers.lookup(db, "test.team", {"team": a.id})
    answers.lookup(db, "test.team", {"team": b.id})
    # As the deploy finds them: the old, global stamp.
    db.execute(update(StoredAnswer).values(stamp="old-global-stamp"))
    db.commit()
    _parse_again(db, _map_between(db, b, league["c"]))  # Bravo moved since
    items = []
    for team in (a, b):
        it = warmer.Item("test.team", {"team": team.id}, {"all": True}, "test")
        it.key = answers.key_of("test.team", {"team": team.id}, ":all")
        it.digest = answers.hash_of(it.key)
        items.append(it)
    current, changed = {}, {}
    for it in items:
        current[it.digest] = answers.stamp(db, it.kind, it.params)
        changed[it.digest] = answers.changed_at(db, it.kind, it.params)
    stored = answers.stored(db, [it.digest for it in items])
    assert warmer.adopt_legacy(db, items, stored, current, changed) == 1
    assert answers.lookup(db, "test.team", {"team": a.id}).state == answers.FRESH
    assert answers.lookup(db, "test.team", {"team": b.id}).state == answers.STALE
