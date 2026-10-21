"""A Demo fetched from a link Staff pasted (docs/plans/02 DATA-1: URL import).

A scrim server's demo page or a shared Drive file is often where a Scrim's Demo
lives; the worker fetches it itself, so the browser never carries hundreds of
megabytes and Cloudflare's request limit never applies.

The link is the outside world's, so it is held to a few rules: http or https
only; every address its host resolves to, at the start and after each redirect,
must be a public one (no loopback, private, link-local or reserved address: the
server must not be steered at itself or its neighbours); at most
:data:`REDIRECTS` redirects; :data:`TIMEOUT` seconds without a byte ends it; and
it stops past ``max_bytes``. The file's kind is read from its first bytes when
its name does not say. A Drive share link is turned into its download link.
The check resolves the host apart from the connection that follows, so a name
that changes its answer in between is not stopped; the route is Staff's only.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path

REDIRECTS = 5
TIMEOUT = 30
CHUNK = 1024 * 1024
AGENT = "cs-analyze demo import"
# The first bytes of each kind of file a Demo comes in.
MAGIC = (
    (b"PBDEMS2\x00", ".dem"),
    (b"HL2DEMO\x00", ".dem"),
    (b"PK\x03\x04", ".zip"),
    (b"Rar!\x1a\x07", ".rar"),
    (b"7z\xbc\xaf\x27\x1c", ".7z"),
    (b"\x1f\x8b", ".gz"),
    (b"BZh", ".bz2"),
    (b"\xfd7zXZ\x00", ".xz"),
)
KNOWN = {suffix for _magic, suffix in MAGIC} | {".tar", ".tgz"}
_DRIVE = re.compile(
    r"^https://drive\.google\.com/(?:file/d/([\w-]+)|open\?id=([\w-]+)|uc\?.*id=([\w-]+))"
)


class RemoteError(ValueError):
    """A link that cannot be fetched, worded for Staff."""


def direct(url: str) -> str:
    """The download link for a Drive share link; any other link as it is."""
    m = _DRIVE.match(url.strip())
    if not m:
        return url.strip()
    file_id = next(g for g in m.groups() if g)
    return f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"


def check(url: str, *, resolve=socket.getaddrinfo) -> str:
    """The link's host when it may be fetched; RemoteError otherwise."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise RemoteError("Линк http:// эсвэл https://-ээр эхлэх ёстой.")
    if parts.username or parts.password:
        raise RemoteError("Нэвтрэх нэр, нууц үгтэй линк хүлээн авахгүй.")
    try:
        infos = resolve(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except OSError:
        raise RemoteError(f"{parts.hostname} хаяг олдсонгүй.") from None
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global or address.is_multicast:
            raise RemoteError("Дотоод сүлжээний хаягаас татахгүй.")
    return parts.hostname


class _Guard(urllib.request.HTTPRedirectHandler):
    """Check every hop of a redirect like the link itself, and count them."""

    def __init__(self, resolve) -> None:
        self.resolve = resolve
        self.hops = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.hops += 1
        if self.hops > REDIRECTS:
            raise RemoteError("Хэт олон redirect.")
        check(newurl, resolve=self.resolve)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _name(url: str, headers: Message) -> str:
    """The file's name: what the server says, else the link's last part."""
    given = headers.get_filename() if hasattr(headers, "get_filename") else None
    if not given:
        given = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
    clean = re.sub(r"[^\w.\-]+", "_", given or "")[:200].strip("._")
    return clean or "demo"


def _kind(head: bytes) -> str | None:
    return next((suffix for magic, suffix in MAGIC if head.startswith(magic)), None)


def fetch(url: str, folder: Path, max_bytes: int, *, resolve=socket.getaddrinfo) -> Path:
    """Download ``url`` into ``folder``; the file, named for its kind."""
    url = direct(url)
    check(url, resolve=resolve)
    opener = urllib.request.build_opener(_Guard(resolve))
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            name = _name(response.geturl(), response.headers)
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > max_bytes:
                raise RemoteError(f"Файл {max_bytes // 2**20} MB-аас том.")
            target = folder / name
            got, head = 0, b""
            with target.open("wb") as out:
                while chunk := response.read(CHUNK):
                    got += len(chunk)
                    if got > max_bytes:
                        raise RemoteError(f"Файл {max_bytes // 2**20} MB-аас том.")
                    if len(head) < 16:
                        head += chunk[:16]
                    out.write(chunk)
    except RemoteError:
        raise
    except urllib.error.HTTPError as exc:
        raise RemoteError(f"Сервер {exc.code} хариулав.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RemoteError(f"Татаж чадсангүй ({getattr(exc, 'reason', exc)}).") from None
    if not got:
        raise RemoteError("Хоосон файл ирлээ.")
    kind = _kind(head)
    if kind is None and target.suffix.lower() not in KNOWN:
        raise RemoteError("Ирсэн файл .dem эсвэл archive биш (магадгүй нэвтрэх хуудас).")
    if (
        kind is not None
        and target.suffix.lower() != kind
        and not (kind == ".gz" and target.suffix.lower() == ".tgz")
    ):
        target = target.rename(target.with_name(f"{target.stem or 'demo'}{kind}"))
    return target
