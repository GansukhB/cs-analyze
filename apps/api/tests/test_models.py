import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    AnalysisJob,
    Demo,
    JobKind,
    JobStatus,
    KillEvent,
    Match,
    MatchMap,
    Player,
    Round,
    Team,
    Tournament,
)


def test_unidentified_teams_cannot_share_a_name(db):
    db.add_all([Team(name="Spirit"), Team(name="Spirit")])
    with pytest.raises(IntegrityError):
        db.commit()


def test_identified_teams_can_share_a_name(db):
    db.add_all(
        [Team(name="Spirit", hltv_id=1), Team(name="Spirit", hltv_id=2), Team(name="Spirit")]
    )
    db.commit()


def test_team_becomes_identified_and_frees_its_name(db):
    team = Team(name="Spirit")
    db.add(team)
    db.commit()
    team.hltv_id = 7020
    db.commit()
    db.add(Team(name="Spirit"))
    db.commit()


def test_demo_cannot_be_processed_before_download(db):
    match = Match(hltv_id=1)
    db.add(Demo(match=match, is_processed=True))
    with pytest.raises(IntegrityError):
        db.commit()


def test_one_demo_row_per_match_and_map(db):
    match = Match(hltv_id=1)
    db.add_all([Demo(match=match, map="anubis"), Demo(match=match, map="anubis")])
    with pytest.raises(IntegrityError):
        db.commit()


def test_relationships_and_properties(db, user):
    vitality, spirit = Team(name="Vitality", hltv_id=9565, slug="vitality"), Team(name="Spirit")
    match = Match(
        hltv_id=2380000, team1=vitality, team2=spirit, tournament=Tournament(name="Major 2026")
    )
    archive = Demo(match=match, is_downloaded=True)
    map_demo = Demo(match=match, map="anubis", map_number=1, error="bad file")
    match_map = MatchMap(match=match, demo=map_demo, map_number=1, team1_score=13, team2_score=8)
    zywoo, donk = Player(steamid=1, name="ZywOo"), Player(steamid=2, name="donk")
    rnd = Round(
        match_map=match_map,
        number=1,
        start_tick=0,
        freeze_end_tick=10,
        end_tick=100,
        official_end_tick=120,
    )
    rnd.kills.append(KillEvent(tick=50, attacker=zywoo, victim=donk, weapon="awp"))
    job = AnalysisJob(my_team_name="Vitality", opponent_name="Spirit", requested_by=user)
    job.matches.append(match)
    db.add_all([match, archive, job])
    db.commit()
    db.expire_all()

    assert vitality.url == "/team/9565/vitality" and spirit.url == ""
    assert match.archive_demo.status == "downloaded" and match.map_demos[0].status == "failed"
    assert map_demo.analysis.scoreline == "13-8"
    assert zywoo.kills_made[0].victim.name == "donk"
    assert match.analysis_jobs == [job] and job.requested_by.username == "Bat"
    assert job.kind == JobKind.SCOUT and job.status == JobStatus.QUEUED and not job.is_finished
    assert job.label == "Vitality vs Spirit" and job.windows == "1/1/1"
    assert job.public_id is not None and job.created_at is not None
