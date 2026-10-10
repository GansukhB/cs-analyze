"""Reading the demo archives HLTV publishes.

One RAR per match, holding one ``.dem`` per map played and named
``<match-slug>-m<n>-<map>.dem`` -- verified against a real download:

    vitality-vs-inner-circle-m1-anubis.dem
    vitality-vs-inner-circle-m2-cache.dem

A Bo1 has no ``-m<n>`` (``magic-vs-the-mongolz-mirage.dem``), and a map whose
server was restarted mid-play comes as Demo parts, ``…-m2-inferno-p1.dem`` and
``…-p2.dem`` (CONTEXT.md, docs/adr/0009).

The archives are RAR5. libarchive reads that format as ``bsdtar``, which is
macOS's stock ``tar`` but is a separate ``libarchive-tools`` package on
Ubuntu (not installed by default), so
unpacking needs no ``rar`` binary but does need that package on a fresh
Ubuntu host. Only ``.dem`` members are ever extracted: the archives are
hundreds of MB and nothing else in them is wanted.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# bsdtar is the libarchive CLI; on macOS plain `tar` is the same binary, which
# is why a plain `shutil.which("tar")` fallback works there but not on Ubuntu,
# where `tar` is GNU tar and cannot read the RAR5 archives HLTV publishes
# (`libarchive-tools` is what installs bsdtar there). Prefer an explicit `bsdtar`
# binary; fall back to `tar` only when it is actually libarchive under the hood.
def _find_tar() -> str | None:
    bsdtar = shutil.which("bsdtar")
    if bsdtar:
        return bsdtar
    tar = shutil.which("tar")
    if tar:
        try:
            version = subprocess.run(
                [tar, "--version"], capture_output=True, text=True, check=False
            )
        except OSError:  # pragma: no cover - depends on the platform
            return tar
        if "bsdtar" in (version.stdout or "") or "libarchive" in (version.stdout or ""):
            return tar
    return None


TAR = _find_tar()

# "...-m1-anubis.dem" -> map number 1, map "anubis"; "...-m2-inferno-p1.dem" is
# part 1 of map 2; "...-mirage.dem" (a Bo1) is just the map.
_DEM_NAME = re.compile(r"-m(\d+)-([A-Za-z0-9_]+?)(?:-p(\d+))?\.dem$", re.IGNORECASE)
_BO1_NAME = re.compile(r"-([A-Za-z0-9_]+?)(?:-p(\d+))?\.dem$", re.IGNORECASE)
# demos.map is VARCHAR(40).
MAP_NAME_MAX = 40


class ArchiveError(RuntimeError):
    """The archive could not be read or unpacked."""


@dataclass(frozen=True)
class DemoEntry:
    """One ``.dem`` inside an archive."""

    name: str
    map: str
    map_number: int | None
    # 1, 2, ... for a Demo part; 0 for a map recorded whole.
    part: int = 0


def parse_demo_name(name: str) -> DemoEntry:
    """Pull the map, its order and its part out of a ``.dem`` filename.

    A Bo1's file has no map number. A name in some other layout falls back to
    its last word, or its bare stem, cut to fit the column, so it still yields a
    usable row instead of an exception.
    """
    base = Path(name).name
    match = _DEM_NAME.search(base)
    if match:
        return DemoEntry(
            name=name,
            map=_normalise_map(match.group(2)),
            map_number=int(match.group(1)),
            part=int(match.group(3) or 0),
        )
    match = _BO1_NAME.search(base)
    if match:
        return DemoEntry(
            name=name, map=_normalise_map(match.group(1)), map_number=None,
            part=int(match.group(2) or 0),
        )  # fmt: skip
    return DemoEntry(name=name, map=_normalise_map(Path(base).stem), map_number=None)


def _normalise_map(value: str) -> str:
    """``"De_Anubis"`` and ``"anubis"`` are the same map; store one spelling."""
    value = value.strip().lower()
    return (value[3:] if value.startswith("de_") else value)[:MAP_NAME_MAX]


def _run(args: list[str]) -> str:
    if not TAR:
        raise ArchiveError(
            "bsdtar (libarchive) not found; it is needed to read the RAR5 archives "
            "HLTV publishes -- GNU tar cannot read them. Install it: "
            "`apt install libarchive-tools` on Ubuntu, or it ships with macOS as the stock `tar`."
        )
    try:
        done = subprocess.run(args, capture_output=True, text=True, check=False)
    except OSError as exc:  # pragma: no cover - depends on the platform
        raise ArchiveError(f"could not run {args[0]}: {exc}") from exc
    if done.returncode != 0:
        raise ArchiveError((done.stderr or done.stdout or "unknown error").strip())
    return done.stdout


def _run_watched(args: list[str], watch: Callable, every: float = 1.0) -> None:
    """Run ``args`` and call ``watch`` while it works. Same errors as :func:`_run`."""
    if not TAR:
        raise ArchiveError(
            "bsdtar (libarchive) not found; it is needed to read the RAR5 archives "
            "HLTV publishes -- GNU tar cannot read them. Install it: "
            "`apt install libarchive-tools` on Ubuntu, or it ships with macOS as the stock `tar`."
        )
    # A temporary file rather than a pipe: nothing reads it until the process
    # ends, and a pipe that fills up while we are sleeping deadlocks bsdtar.
    with tempfile.TemporaryFile(mode="w+") as errors:
        try:
            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errors, text=True)
        except OSError as exc:  # pragma: no cover - depends on the platform
            raise ArchiveError(f"could not run {args[0]}: {exc}") from exc

        while proc.poll() is None:
            try:
                watch()
            except Exception:  # a progress report must never fail an extraction
                logger.debug("extraction progress callback failed", exc_info=True)
            time.sleep(every)

        if proc.returncode != 0:
            errors.seek(0)
            raise ArchiveError(errors.read().strip() or "unknown error")


def list_demos(archive: Path) -> list[DemoEntry]:
    """The ``.dem`` members of ``archive``, in archive order."""
    if not archive.exists():
        raise ArchiveError(f"archive is not on disk: {archive}")
    names = _run([TAR, "-tf", str(archive)]).splitlines()
    return [parse_demo_name(n) for n in (n.strip() for n in names) if n.lower().endswith(".dem")]


def extract(
    archive: Path, dest_dir: Path, entries: list[DemoEntry], on_progress: Callable | None = None
) -> list[Path]:
    """Unpack ``entries`` into ``dest_dir``; returns the paths actually written.

    ``on_progress(files_done, files_total, bytes_written)`` is called about once a
    second while bsdtar runs. It watches the destination rather than the archive
    because there is nothing to ask bsdtar: it prints nothing per member and
    exits once. Still one invocation for all the members, deliberately -- these
    archives are solid, so extracting a member at a time to get a progress line
    would re-read the whole thing per map.
    """
    if not entries:
        return []
    dest_dir.mkdir(parents=True, exist_ok=True)
    args = [TAR, "-x", "-f", str(archive), "-C", str(dest_dir), "--"] + [e.name for e in entries]
    wanted = [dest_dir / Path(e.name).name for e in entries]

    if on_progress is None:
        _run(args)
    else:
        _run_watched(args, lambda: on_progress(*_written_so_far(wanted)))

    missing = [p.name for p in wanted if not p.exists()]
    if missing:
        raise ArchiveError(f"extraction reported success but {', '.join(missing)} is not on disk")
    return wanted


def _written_so_far(wanted: list[Path]):
    """How much of the extraction has landed: files finished, total, bytes.

    bsdtar writes the members in archive order, which is the order of ``wanted``,
    so the newest file is the one still growing -- it is counted as started, not
    as done. That undercounts by one for the whole run, which is the honest
    direction to be wrong in.
    """
    sizes = [p.stat().st_size if p.exists() else 0 for p in wanted]
    started = sum(1 for size in sizes if size)
    return max(0, started - 1), len(wanted), sum(sizes)
