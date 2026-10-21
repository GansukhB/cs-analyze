"""Workspaces and Users, and Tick Data upkeep.

A Workspace and its first Staff are created here; there is no sign-up endpoint.

python -m app.cli create-workspace <name>
python -m app.cli add-my-team <workspace> <team> [--label main]
python -m app.cli create-user [username] [--workspace NAME] [--role staff|player] [--player STEAMID]
python -m app.cli deactivate-user [username]
python -m app.cli activate-user [username]
python -m app.cli import-tickdata [folder]   # parquet bundles on disk -> MySQL
python -m app.cli rebuild-tickdata           # Replays, walks, geometry from the stored bundles
python -m app.cli fit-winprob                # refit the Review's Win probability model
python -m app.cli assistant-eval [--yes]     # ask and score the Assistant's golden set
python -m app.cli hltv-canary                # check HLTV still reads the Scout's way
python -m app.cli watch                      # alert on what is wrong now (every 5 min)
python -m app.cli alert <key> <text>         # send one alert
python -m app.cli rebuild-reviews [--map ID] # cut every Match Map's Review again
python -m app.cli summary-thresholds         # the Patterns' 75th percentiles, measured again
python -m app.cli import-vrs [checkout]       # Valve Regional Standings -> series results
python -m app.cli forecast-backtest           # fit the Rating walk-forward (rating_params.json)
python -m app.cli import-cstat [root] [--match HLTV_ID] [--map NAME]
                                             # cstat's teams, matches and .dem files -> MySQL
"""

import argparse
import getpass
import sys
import time
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import joinedload

from app.config import REPO_ROOT, get_settings
from app.db import SessionLocal
from app.models import (
    Demo,
    MatchMap,
    Player,
    Team,
    TickDataset,
    User,
    UserRole,
    Workspace,
    WorkspaceTeam,
)
from app.security import hash_password
from app.services.members import MIN_PASSWORD_LENGTH


def _workspace(db, name: str | None) -> Workspace:
    """The named Workspace, or the only one there is."""
    if name:
        found = db.scalar(select(Workspace).where(Workspace.name == name))
        if found is None:
            sys.exit(f"No Workspace {name!r}. Create it with create-workspace.")
        return found
    every = db.scalars(select(Workspace)).all()
    if len(every) != 1:
        sys.exit(
            "Name the Workspace with --workspace."
            if every
            else "No Workspace yet. Create one with create-workspace first."
        )
    return every[0]


def create_workspace(name: str) -> None:
    name = name.strip()
    if not name or len(name) > 120:
        sys.exit("A Workspace name is 1-120 characters.")
    with SessionLocal() as db:
        if db.scalar(select(Workspace).where(Workspace.name == name)):
            sys.exit(f"Workspace {name!r} already exists.")
        db.add(Workspace(name=name))
        db.commit()
    print(f"Created Workspace {name!r}. Add its my team with add-my-team, then its first Staff.")


def add_my_team(workspace: str, team: str, label: str) -> None:
    with SessionLocal() as db:
        ws = _workspace(db, workspace)
        found = db.scalars(select(Team).where(Team.name == team)).all()
        if len(found) != 1:
            sys.exit(
                f"{len(found)} Teams are named {team!r}; run a Scout for it first."
                if not found
                else f"{len(found)} Teams are named {team!r}; pick one by id in the database."
            )
        if any(wt.team_id == found[0].id for wt in ws.teams):
            sys.exit(f"{team!r} is already a my team of {ws.name!r}.")
        ws.teams.append(WorkspaceTeam(team=found[0], label=label))
        db.commit()
    print(f"{team!r} is now a my team of {ws.name!r}.")


def create_user(
    username: str, workspace: str | None = None, role: str = "staff", steamid: int | None = None
) -> None:
    if not username or username != username.strip() or len(username) > 64:
        sys.exit("Username must be 1-64 characters with no leading or trailing spaces.")
    if role not in tuple(UserRole):
        sys.exit(f"A role is one of: {', '.join(UserRole)}.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            sys.exit(f"User {username!r} already exists.")
        ws = _workspace(db, workspace)
        player = None
        if steamid is not None:
            player = db.scalar(select(Player).where(Player.steamid == steamid))
            if player is None:
                sys.exit(f"No Player with Steam id {steamid}: parse one of their Match Maps first.")
        if role == UserRole.PLAYER and player is None:
            sys.exit("A Player login needs --player <steamid>.")
        password = getpass.getpass("Password: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        if password != getpass.getpass("Repeat password: "):
            sys.exit("Passwords do not match.")
        db.add(
            User(
                username=username,
                password_hash=hash_password(password),
                workspace=ws,
                role=role,
                player=player,
            )
        )
        db.commit()
    print(f"Created {role} {username!r} in {ws.name!r}.")


def set_active(username: str, active: bool) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            sys.exit(f"No user {username!r}.")
        user.is_active = active
        from app.services import audit_log

        audit_log.record(db, None, "member.change", username, workspace_id=user.workspace_id,
                         is_active=active)  # fmt: skip
        db.commit()
    print(f"User {username!r} is now {'active' if active else 'deactivated'}.")


def import_tickdata(folder: Path) -> None:
    """Move parquet bundles written before Tick Data lived in MySQL into it.

    A bundle is matched to its Match Map through the Demo it was parsed from
    (same file stem). Its flash/HE detonation tables, which those bundles lack,
    are refilled from ``grenade_throws``. Everything is then cut from it as an
    ingest would. Safe to run twice: a map's existing Tick Data is replaced.
    """
    from app.services import tickdata

    files = sorted(folder.glob("*.zip"))
    if not files:
        sys.exit(f"No .zip bundles in {folder}.")
    done = 0
    with SessionLocal() as db:
        for path in files:
            stem = path.stem
            match_map = db.scalar(
                select(MatchMap)
                .join(Demo, Demo.id == MatchMap.demo_id)
                .options(joinedload(MatchMap.game_map))
                .where(Demo.filename.in_([f"{stem}.dem", stem]))
            )
            if match_map is None:
                print(f"  ? {path.name}: no parsed map was read from a demo named {stem}.dem")
                continue
            started = time.monotonic()
            blob = tickdata.with_detonations(db, match_map, path.read_bytes())
            db.execute(delete(TickDataset).where(TickDataset.match_map_id == match_map.id))
            dataset = tickdata.store(db, match_map, blob, awpy_version=match_map.awpy_version)
            db.commit()
            rounds = len((dataset.replay or {}).get("rounds") or [])
            print(
                f"  ✓ {path.name} → map {match_map.id} ({match_map.game_map.name}): "
                f"{len(blob) / 1e6:.1f} MB, {rounds} replay rounds, "
                f"{time.monotonic() - started:.1f}s"
            )
            done += 1
    print(f"Imported {done} of {len(files)} bundles.")


def rebuild_tickdata() -> None:
    """Cut Replays, walks and geometry again from every stored bundle."""
    from app.services import heavy, tickdata

    def waiting(holder: str) -> None:
        print(f"  … waiting for {holder or 'another parse'} to finish (one heavy job at a time)")

    with SessionLocal() as db:
        datasets = list(db.scalars(select(TickDataset).order_by(TickDataset.match_map_id)))
        for dataset in datasets:
            match_map = db.get(MatchMap, dataset.match_map_id)
            started = time.monotonic()
            with heavy.permit("cli:data:rebuild", on_wait=waiting):
                tickdata.rebuild(db, match_map, dataset)
                db.commit()
            print(f"  ✓ map {match_map.id}: {time.monotonic() - started:.1f}s")
    print(f"Rebuilt {len(datasets)} maps (version {tickdata.derived_version()}).")


def fit_winprob(since: str | None = None, dry_run: bool = False) -> None:
    """Fit the Win probability model on every parsed Round and commit-ready write it.

    docs/adr/0007: the model only changes here, never on a parse. Its version
    moves with the data it was fitted on, which marks every stored Review stale.
    ``since`` fits on the Match Maps played from that day (a patch's, DATA-7);
    ``dry_run`` prints the metrics and writes nothing.
    """
    import hashlib
    import json
    from datetime import UTC, datetime

    from app.services import winprob

    day = datetime.fromisoformat(since) if since else None
    with SessionLocal() as db:
        # The states as the Review reads them, from the Tick Data (RV-4).
        samples = winprob.samples_from_reviews(
            db,
            progress=lambda i, n: print(f"\r  reading {i}/{n} maps", end="", flush=True),
            since=day,
        )
    print()
    if day is not None:
        print(f"Match Maps played since {since} only.")
    if not samples:
        print("No states to fit on.")
        return
    rounds = sum(1 for s in samples if s.state.seconds_left >= winprob.ROUND_SECONDS - 0.1)
    print(f"{len(samples)} states from {len({s.group for s in samples})} maps ({rounds} rounds).")
    before = winprob.fit(samples, version=1)
    spec = winprob.fit(samples)
    for phase in ("pre", "post"):
        old, new = before["metrics"][phase], spec["metrics"][phase]
        print(f"  {phase}: " + ", ".join(
            f"{k} {old.get(k)} -> {new.get(k)}" for k in ("cv_logloss", "brier", "auc", "ece")
        ))  # fmt: skip
    if dry_run:
        print("Dry run: nothing written.")
        return
    stamp = datetime.now(UTC)
    digest = hashlib.sha1(
        json.dumps([spec["pre"], spec["post"]], sort_keys=True).encode(), usedforsecurity=False
    ).hexdigest()[:8]
    spec = {
        "version": f"{stamp:%Y%m%d}.{digest}",
        "fitted_at": stamp.isoformat(timespec="seconds"),
        "match_maps": len({s.group for s in samples}),
        **({"since": since} if since else {}),
        **spec,
    }
    winprob.MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    winprob.MODEL_PATH.write_text(json.dumps(spec, indent=1, sort_keys=True) + "\n")
    for phase, metrics in spec["metrics"].items():
        print(f"  {phase}: {metrics['samples']} states, man count alone "
              f"{metrics['cv_logloss_man_count_only']}")  # fmt: skip
    print(f"Wrote {winprob.MODEL_PATH} (version {spec['version']}).")


def hltv_canary(team: str) -> None:
    """Read one known Team on HLTV the Scout's way; exit 1 naming what broke (OPS-9),
    and say so as an alert (OPS-5)."""
    from app.services import alerts, canary
    from app.services.browser import HltvBrowser
    from app.services.client import HltvClient

    with HltvBrowser() as browser:
        problems = canary.check(HltvClient(browser), team)
    if problems:
        for p in problems:
            print(f"BROKEN {p}")
        alerts.send("canary", "HLTV no longer reads the Scout's way: " + "; ".join(problems))
        raise SystemExit(1)
    print(f"HLTV reads as expected ({team}).")


def watch() -> None:
    """The every-5-minutes check (OPS-5): send an alert for each thing wrong."""
    from app.services import alerts

    with SessionLocal() as db:
        found = alerts.checks(db)
    for key, text in found:
        alerts.send(key, text)
    print(f"{len(found)} problem(s)" + (": " + "; ".join(t for _k, t in found) if found else "."))


def alert(key: str, text: str) -> None:
    """Send one alert, e.g. from a systemd unit's OnFailure (OPS-5)."""
    from app.services import alerts

    alerts.send(key, text)


def assistant_eval(limit: int | None = None, yes: bool = False) -> None:
    """Ask the Assistant its golden set and score it (AS-4). Every question is a
    paid turn: without ``yes`` this only says what it would cost."""
    import json
    from datetime import UTC, datetime

    from app.config import get_settings
    from app.services import assistant, assistant_eval

    items = assistant_eval.questions()[:limit] if limit else assistant_eval.questions()
    guess = len(items) * assistant_eval.COST_GUESS_USD
    if not assistant.is_configured():
        raise SystemExit("CLAUDE_API_KEY is not set.")
    if not yes:
        print(f"{len(items)} questions on {get_settings().claude_model}, about ${guess:.2f}.")
        print("Run again with --yes to ask them.")
        return
    results = []
    with SessionLocal() as db:
        for i, item in enumerate(items, 1):
            result = assistant_eval.ask(db, item)
            results.append(result)
            mark = "skip" if "skipped" in result else ("ok " if result["tool_ok"] else "TOOL")
            loose = ", ".join(result.get("unchecked", []))
            print(f"{i:>2} {mark} {item['q'][:60]}" + (f"  [check: {loose}]" if loose else ""))
    total = assistant_eval.summary(results)
    stamp = f"{datetime.now(UTC):%Y%m%d-%H%M}"
    out = Path(get_settings().hltv_data_dir) / "tmp" / f"assistant-eval-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": total, "results": results}, ensure_ascii=False, indent=1))
    print(json.dumps(total))
    print(f"Answers for reading: {out}")


def rebuild_reviews(match_map_id: int | None = None) -> None:
    """Cut the Review of every Match Map with Tick Data again (or of one)."""
    from app.services import review

    with SessionLocal() as db:
        query = select(TickDataset.match_map_id).order_by(TickDataset.match_map_id)
        if match_map_id is not None:
            query = query.where(TickDataset.match_map_id == match_map_id)
        ids = list(db.scalars(query))
        for mid in ids:
            match_map = db.get(MatchMap, mid)
            started = time.monotonic()
            built = review.rebuild(db, match_map)
            db.commit()
            found = len(built.get("findings", [])) if built else 0
            print(f"  ✓ map {mid}: {found} findings, {time.monotonic() - started:.1f}s")
    print(f"Rebuilt {len(ids)} Reviews (version {review.version()}).")


def summary_thresholds() -> None:
    """Print each Finding code's 75th-percentile rate per 24 Rounds over every
    current Review, to paste into ``review_summary.PATTERN_P75`` after a detector
    changes (RV-5)."""
    import gzip
    import json

    from app.models import MatchMapReview
    from app.services import review, review_summary

    with SessionLocal() as db:
        payloads = [
            json.loads(gzip.decompress(blob))
            for blob in db.scalars(
                select(MatchMapReview.payload).where(MatchMapReview.version == review.version())
            )
        ]
    print(f"{len(payloads)} Reviews at {review.version()} (REVIEW_SCHEMA {review.REVIEW_SCHEMA}):")
    for code, rate in review_summary.pattern_percentiles(payloads).items():
        print(f'    "{code}": {rate},')


def import_cstat(
    root: Path, parse: bool, match: int | None = None, map_name: str | None = None
) -> None:
    """cstat's teams, tournaments and matches, then every map demo it still has on disk."""
    from app.services import cstat_import

    with SessionLocal() as db:
        try:
            cstat_import.run(
                db,
                root,
                parse=parse,
                log=lambda line: print(line, flush=True),
                match_hltv_id=match,
                map_name=map_name,
            )
        except FileNotFoundError as exc:
            sys.exit(str(exc))


def import_vrs(root: Path | None) -> None:
    """Valve's monthly standings and every series they counted (DATA-2)."""
    from app.services import vrs_import

    scratch = get_settings().hltv_data_dir / "tmp"
    with SessionLocal() as db:
        out = vrs_import.run(db, scratch, root, log=lambda line: print(line, flush=True))
    print(
        f"{out['standings']} standings lines; {out['series']} series read, "
        f"{out['added']} new, {out['total']} stored."
    )
    from app.services import forecast_store

    with SessionLocal() as db:
        print(f"{forecast_store.grade(db)} Forecasts graded.")


def forecast_backtest() -> None:
    """Fit the Rating on series before 2026, score it on 2026 (FC-5), and commit it."""
    import json
    from datetime import date

    from app.services import dbctx, forecast, rating

    with SessionLocal() as db:
        series, vrs = rating.load_series(db), rating.load_vrs(db)
    if not series:
        sys.exit("No series results: run `npm run data:vrs` first.")
    out = rating.backtest(series, vrs, split=date(2026, 1, 1), burn_in=date(2024, 6, 1))
    out["params"]["version"] = date.today().strftime("%Y%m%d")
    out["series"] = len(series)
    rating.PARAMS_PATH.write_text(json.dumps(out, indent=2) + "\n")
    # The Map model on every stored Match Map, with the parameters just fitted.
    rating._params.cache_clear()
    forecast._load_committed.cache_clear()
    rating._region_offsets.cache_clear()
    with SessionLocal() as db, dbctx.using(db):
        out["maps"] = forecast.check_maps()
    rating.PARAMS_PATH.write_text(json.dumps(out, indent=2) + "\n")
    keys = ("params", "tune", "test", "baselines", "vs_vrs_points", "maps")
    print(json.dumps({k: out[k] for k in keys}, indent=2))
    print(f"Wrote {rating.PARAMS_PATH}; commit it.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create-workspace").add_argument("name")
    team = sub.add_parser("add-my-team")
    team.add_argument("workspace")
    team.add_argument("team", help="The Team's name, as stored.")
    team.add_argument("--label", default="main", help="main, academy, ...")
    for name in ("create-user", "deactivate-user", "activate-user"):
        command = sub.add_parser(name)
        command.add_argument("username", nargs="?", help="Prompted for if omitted.")
        if name == "create-user":
            command.add_argument("--workspace", help="Needed when there is more than one.")
            command.add_argument("--role", default="staff", choices=[r.value for r in UserRole])
            command.add_argument(
                "--player", type=int, help="The Player's Steam id (a Player login)."
            )
    sub.add_parser("import-tickdata").add_argument(
        "folder", nargs="?", help="Defaults to <HLTV_DATA_DIR>/parquet."
    )
    sub.add_parser("rebuild-tickdata")
    sub.add_parser("import-vrs").add_argument(
        "root", nargs="?", help="A checkout of the repo; cloned into scratch if omitted."
    )
    fit = sub.add_parser("fit-winprob")
    fit.add_argument("--since", help="Only Match Maps played on or after this day (YYYY-MM-DD).")
    fit.add_argument("--dry-run", action="store_true", help="Print the metrics, write nothing.")
    sub.add_parser("forecast-backtest")
    sub.add_parser("hltv-canary").add_argument(
        "--team", default="Vitality", help="A Team HLTV lists with recent demos."
    )
    sub.add_parser("watch")
    al = sub.add_parser("alert")
    al.add_argument("key", help="Alerts of one key are sent once an hour at most.")
    al.add_argument("text")
    ev = sub.add_parser("assistant-eval")
    ev.add_argument("--limit", type=int, help="Only the first N questions.")
    ev.add_argument("--yes", action="store_true", help="Ask them (each is a paid turn).")
    sub.add_parser("rebuild-reviews").add_argument("--map", type=int, help="One Match Map id.")
    sub.add_parser("summary-thresholds")
    cstat = sub.add_parser("import-cstat")
    cstat.add_argument("root", nargs="?", help="The cstat checkout; defaults to ../cstat.")
    cstat.add_argument("--no-parse", action="store_true", help="Import the rows only.")
    cstat.add_argument("--match", type=int, help="Parse only this HLTV match id.")
    cstat.add_argument("--map", help="Parse only this map of it (inferno or de_inferno).")
    args = parser.parse_args()
    if args.command == "create-workspace":
        create_workspace(args.name)
        return
    if args.command == "add-my-team":
        add_my_team(args.workspace, args.team, args.label)
        return
    if args.command == "import-cstat":
        import_cstat(
            Path(args.root) if args.root else REPO_ROOT.parent / "cstat",
            not args.no_parse,
            args.match,
            args.map,
        )
        return
    if args.command == "import-tickdata":
        default = get_settings().hltv_data_dir / "parquet"
        import_tickdata(Path(args.folder) if args.folder else default)
        return
    if args.command == "import-vrs":
        import_vrs(Path(args.root) if args.root else None)
        return
    if args.command == "rebuild-tickdata":
        rebuild_tickdata()
        return
    if args.command == "forecast-backtest":
        forecast_backtest()
        return
    if args.command == "watch":
        watch()
        return
    if args.command == "alert":
        alert(args.key, args.text)
        return
    if args.command == "hltv-canary":
        hltv_canary(args.team)
        return
    if args.command == "assistant-eval":
        assistant_eval(args.limit, args.yes)
        return
    if args.command == "fit-winprob":
        fit_winprob(args.since, args.dry_run)
        return
    if args.command == "rebuild-reviews":
        rebuild_reviews(args.map)
        return
    if args.command == "summary-thresholds":
        summary_thresholds()
        return
    # `npm run user:create` without `-- <name>` passes no username; ask instead of failing.
    username = args.username if args.username is not None else input("Username: ")

    if args.command == "create-user":
        create_user(username, args.workspace, args.role, args.player)
    else:
        set_active(username, active=args.command == "activate-user")


if __name__ == "__main__":
    main()
