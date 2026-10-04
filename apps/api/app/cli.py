"""User management, and Tick Data upkeep.

Users can only be created here; there is no sign-up endpoint.

python -m app.cli create-user [username]
python -m app.cli deactivate-user [username]
python -m app.cli activate-user [username]
python -m app.cli import-tickdata [folder]   # parquet bundles on disk -> MySQL
python -m app.cli rebuild-tickdata           # Replays, walks, geometry from the stored bundles
python -m app.cli import-cstat [root]        # cstat's teams, matches and .dem files -> MySQL
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
from app.models import Demo, MatchMap, TickDataset, User
from app.security import hash_password

MIN_PASSWORD_LENGTH = 8


def create_user(username: str) -> None:
    if not username or username != username.strip() or len(username) > 64:
        sys.exit("Username must be 1-64 characters with no leading or trailing spaces.")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            sys.exit(f"User {username!r} already exists.")
        password = getpass.getpass("Password: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
        if password != getpass.getpass("Repeat password: "):
            sys.exit("Passwords do not match.")
        db.add(User(username=username, password_hash=hash_password(password)))
        db.commit()
    print(f"Created user {username!r}.")


def set_active(username: str, active: bool) -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            sys.exit(f"No user {username!r}.")
        user.is_active = active
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
    from app.services import tickdata

    with SessionLocal() as db:
        datasets = list(db.scalars(select(TickDataset).order_by(TickDataset.match_map_id)))
        for dataset in datasets:
            match_map = db.get(MatchMap, dataset.match_map_id)
            started = time.monotonic()
            tickdata.rebuild(db, match_map, dataset)
            db.commit()
            print(f"  ✓ map {match_map.id}: {time.monotonic() - started:.1f}s")
    print(f"Rebuilt {len(datasets)} maps (version {tickdata.derived_version()}).")


def import_cstat(root: Path, parse: bool) -> None:
    """cstat's teams, tournaments and matches, then every map demo it still has on disk."""
    from app.services import cstat_import

    with SessionLocal() as db:
        try:
            cstat_import.run(db, root, parse=parse, log=lambda line: print(line, flush=True))
        except FileNotFoundError as exc:
            sys.exit(str(exc))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("create-user", "deactivate-user", "activate-user"):
        sub.add_parser(name).add_argument("username", nargs="?", help="Prompted for if omitted.")
    sub.add_parser("import-tickdata").add_argument(
        "folder", nargs="?", help="Defaults to <HLTV_DATA_DIR>/parquet."
    )
    sub.add_parser("rebuild-tickdata")
    cstat = sub.add_parser("import-cstat")
    cstat.add_argument("root", nargs="?", help="The cstat checkout; defaults to ../cstat.")
    cstat.add_argument("--no-parse", action="store_true", help="Import the rows only.")
    args = parser.parse_args()
    if args.command == "import-cstat":
        import_cstat(
            Path(args.root) if args.root else REPO_ROOT.parent / "cstat", not args.no_parse
        )
        return
    if args.command == "import-tickdata":
        default = get_settings().hltv_data_dir / "parquet"
        import_tickdata(Path(args.folder) if args.folder else default)
        return
    if args.command == "rebuild-tickdata":
        rebuild_tickdata()
        return
    # `npm run user:create` without `-- <name>` passes no username; ask instead of failing.
    username = args.username if args.username is not None else input("Username: ")

    if args.command == "create-user":
        create_user(username)
    else:
        set_active(username, active=args.command == "activate-user")


if __name__ == "__main__":
    main()
