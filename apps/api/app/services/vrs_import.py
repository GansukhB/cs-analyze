"""Valve Regional Standings into ``series_results`` and ``vrs_standings`` (DATA-2).

Valve publishes its standings every month on GitHub
(ValveSoftware/counter-strike_regional_standings): for each ranked roster, a
details page listing every series that counted, with its date, the opponent,
W/L, whether it was a LAN win and the five who played. That is a worldwide
results database for Ratings (docs/plans/03-ratings-forecast.md), free and
without Cloudflare. Its data is "provided by HLTV.org" and the repo carries no
licence, so it stays internal (docs/data-policy.md).

A series shows up once per ranked side within a snapshot, under one Match ID;
across snapshots the ids are new, so a series is keyed by its date, both names,
its winner and how many such series the two played that day. Re-importing is
idempotent. The repo is cloned into scratch and removed afterwards (ADR 0002).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SeriesResult, Team, TeamAlias, VrsStanding
from app.services import teamnames

logger = logging.getLogger(__name__)

REPO = "https://github.com/ValveSoftware/counter-strike_regional_standings.git"
# A name this close to a stored Team's is that Team; below it, only the name is kept.
RESOLVE_THRESHOLD = 0.95

_SNAPSHOT = re.compile(r"^(\d{4})_(\d{2})_(\d{2})$")
_HEADER = {
    "team": re.compile(r"^Team Name:\s*(.+?)\s*<br />", re.M),
    "roster": re.compile(r"^Roster:\s*(.+?)\s*<br />", re.M),
    "global": re.compile(r"^Global Rank:\s*\[(\d+)\]", re.M),
    "region": re.compile(r"^Region:\s*\[([^\]]+)\]", re.M),
    "regional": re.compile(r"^Regional Rank:\s*\[(\d+)\]", re.M),
    "points": re.compile(r"^Final Rank Value:\s*([\d.]+)", re.M),
}


@dataclass
class Details:
    team: str
    roster: list[str]
    global_rank: int
    region: str
    regional_rank: int | None
    points: float
    # (match id, date, opponent, won, lan win, roster)
    matches: list[tuple] = field(default_factory=list)


def parse_details(text: str) -> Details | None:
    """One roster's details page, or None when it isn't one."""
    found = {k: rx.search(text) for k, rx in _HEADER.items()}
    if not (found["team"] and found["global"] and found["points"]):
        return None
    roster = [p.strip() for p in (found["roster"].group(1) if found["roster"] else "").split(",")]
    out = Details(
        team=found["team"].group(1).strip(),
        roster=[p for p in roster if p],
        global_rank=int(found["global"].group(1)),
        region=found["region"].group(1).strip() if found["region"] else "",
        regional_rank=int(found["regional"].group(1)) if found["regional"] else None,
        points=float(found["points"].group(1)),
    )
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("| Match Played")), None)
    if start is None:
        return out
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 12 or not cells[1].isdigit():
            continue
        played = date.fromisoformat(cells[2])
        lan = cells[9] not in ("-", "")
        players = [p.strip() for p in cells[11].split(",") if p.strip()]
        out.matches.append((int(cells[1]), played, cells[3], cells[4] == "W", lan, players))
    return out


def snapshots(root: Path) -> list[tuple[date, Path]]:
    """Every monthly snapshot's details folder, oldest first."""
    out = []
    for folder in root.glob("live/*/details/*"):
        m = _SNAPSHOT.match(folder.name)
        if m and folder.is_dir():
            out.append((date(int(m[1]), int(m[2]), int(m[3])), folder))
    return sorted(out)


def fetch(dest: Path) -> Path:
    """A shallow clone of Valve's repo under ``dest`` (removed first if there)."""
    shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", REPO, str(dest)],
        check=True,
        timeout=600,
    )
    return dest


def _resolver(db: Session) -> Callable[[str], int | None]:
    """Name -> Team id, conservatively: exact (any case), an alias, or a near-certain match."""
    teams = list(db.scalars(select(Team).where(Team.name != "")))
    exact = {t.name.casefold(): t.id for t in teams}
    aliases = {
        name.casefold(): team_id
        for name, team_id in db.execute(select(TeamAlias.clan_name, TeamAlias.team_id))
        if team_id is not None
    }
    cache: dict[str, int | None] = {}

    def resolve(name: str) -> int | None:
        key = name.casefold()
        if key not in cache:
            found = exact.get(key) or aliases.get(key)
            if found is None:
                best = teamnames.resolve(name, teams, threshold=RESOLVE_THRESHOLD)
                found = best[0].id if best else None
            cache[key] = found
        return cache[key]

    return resolve


def import_root(db: Session, root: Path, log: Callable[[str], None] = print) -> dict:
    """Read every snapshot under ``root`` into the two tables. Idempotent."""
    resolve = _resolver(db)
    series: dict[str, dict] = {}
    standings = 0
    for snapshot, folder in snapshots(root):
        by_id: dict[int, dict] = defaultdict(dict)
        rows = []
        for path in sorted(folder.glob("*.md")):
            details = parse_details(path.read_text(encoding="utf-8"))
            if details is None:
                continue
            rows.append(details)
            for match_id, played, opponent, won, lan, players in details.matches:
                by_id[match_id]["date"] = played
                by_id[match_id].setdefault("opponent_of", {})[details.team] = opponent
                by_id[match_id].setdefault("sides", {})[details.team] = (won, lan, players)
        db.query(VrsStanding).filter(VrsStanding.snapshot == snapshot).delete()
        for d in rows:
            db.add(
                VrsStanding(
                    snapshot=snapshot,
                    global_rank=d.global_rank,
                    region=d.region,
                    regional_rank=d.regional_rank,
                    points=d.points,
                    team_name=d.team,
                    team_id=resolve(d.team),
                    roster=d.roster,
                )
            )
        standings += len(rows)

        # One series per Match ID, from whichever sides were ranked.
        seen_today: Counter = Counter()
        for match_id in sorted(by_id):
            m = by_id[match_id]
            (first, (won, lan, players)), *_ = m["sides"].items()
            other = m["opponent_of"][first]
            a, b = sorted((first, other), key=str.casefold)
            a_won = won if a == first else not won
            rosters = {first: players}
            lans = [lan and w for w, lan, _ in m["sides"].values()]
            for team, (_won, _lan, ps) in m["sides"].items():
                rosters[team] = ps
            base = f"{m['date'].isoformat()}|{a.casefold()}|{b.casefold()}|{int(a_won)}"
            seen_today[base] += 1
            key = f"{base}|{seen_today[base]}"[:190]
            known = series.get(key)
            row = {
                "played_on": m["date"],
                "team_a": a,
                "team_b": b,
                "a_won": a_won,
                "lan": True if any(lans) else None,
                "roster_a": rosters.get(a) or (known or {}).get("roster_a") or [],
                "roster_b": rosters.get(b) or (known or {}).get("roster_b") or [],
            }
            if known and known["lan"]:
                row["lan"] = True
            series[key] = row
        log(f"  {snapshot}: {len(rows)} rosters, {len(by_id)} series")

    existing = {
        s.key: s for s in db.scalars(select(SeriesResult).where(SeriesResult.source == "vrs"))
    }
    added = 0
    for key, row in series.items():
        found = existing.get(key)
        if found is None:
            found = SeriesResult(source="vrs", key=key)
            db.add(found)
            added += 1
        for attr, value in row.items():
            setattr(found, attr, value)
        found.team_a_id = resolve(row["team_a"])
        found.team_b_id = resolve(row["team_b"])
    db.commit()
    total = db.scalar(select(func.count(SeriesResult.id)))
    return {"standings": standings, "series": len(series), "added": added, "total": total}


def run(db: Session, scratch: Path, root: Path | None = None, log=print) -> dict:
    """Fetch Valve's repo (unless ``root`` is a checkout already) and import it."""
    if root is not None:
        return import_root(db, root, log)
    dest = scratch / "vrs"
    try:
        log(f"Cloning {REPO} ...")
        fetch(dest)
        return import_root(db, dest, log)
    finally:
        shutil.rmtree(dest, ignore_errors=True)
