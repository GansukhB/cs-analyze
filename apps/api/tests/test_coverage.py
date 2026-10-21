# ruff: noqa: F811  (the Game Plan tests' fixtures, imported by name)
"""What the stored data covers (docs/plans/02 DATA-9)."""

from sqlalchemy import select

from app.models import MatchMap, TickDataset, WorkspaceTeam
from app.services.analysis_store import CURRENT_SCHEMA_VERSION
from tests.test_gameplan import league, memory_cache  # noqa: F401


def test_each_team_with_what_its_maps_lack_and_the_download_queue(
    client, db, auth, workspace, league
):
    a = league["a"]
    db.add(WorkspaceTeam(workspace_id=workspace.id, team_id=a.id))
    maps = db.scalars(select(MatchMap).order_by(MatchMap.id)).all()
    # One behind with Tick Data that has no Loadout: its Match downloads again.
    maps[0].schema_version = CURRENT_SCHEMA_VERSION - 2
    db.add(TickDataset(match_map_id=maps[0].id, tables=["ticks"], bundle=b"", derived_version=""))
    for m in maps[1:]:
        m.schema_version = CURRENT_SCHEMA_VERSION
    db.commit()
    body = client.get("/data/coverage", headers=auth).json()
    assert body["schema_version"] == CURRENT_SCHEMA_VERSION
    assert body["totals"]["maps"] == len(maps)
    assert body["totals"]["behind"] == 1 and body["totals"]["no_loadout"] == 1
    assert body["teams"][0]["id"] == a.id and body["teams"][0]["mine"]
    assert body["teams"][0]["by_map"] == [["de_mirage", body["teams"][0]["maps"]]]
    assert body["queued"] == 1 and body["queue"][0]["reason"] == "no_loadout"
    assert body["maps"] == [{"map": "de_mirage", "maps": len(maps), "teams": 3}]
