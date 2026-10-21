"""A Demo fetched from a link (docs/plans/02 DATA-1: URL import)."""

import http.server
import threading
from contextlib import contextmanager

import pytest

from app.services import remote

PUBLIC = "93.184.216.34"


def _resolves_to(address):
    return lambda host, port: [(2, 1, 6, "", (address, port))]


@pytest.mark.parametrize(
    ("link", "file_id"),
    [
        ("https://drive.google.com/file/d/1AbC-x_9/view?usp=sharing", "1AbC-x_9"),
        ("https://drive.google.com/open?id=1AbC-x_9", "1AbC-x_9"),
        ("https://drive.google.com/uc?export=download&id=1AbC-x_9", "1AbC-x_9"),
    ],
)
def test_a_drive_share_link_becomes_its_download_link(link, file_id):
    assert remote.direct(link) == (
        f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
    )
    assert remote.direct("https://example.com/a.dem") == "https://example.com/a.dem"


@pytest.mark.parametrize(
    ("link", "address"),
    [
        ("http://example.com/a.dem", "127.0.0.1"),
        ("http://example.com/a.dem", "10.0.0.5"),
        ("http://example.com/a.dem", "169.254.169.254"),
        ("http://example.com/a.dem", "::1"),
        ("http://example.com/a.dem", "fe80::1%en0"),
        ("http://example.com/a.dem", "::ffff:127.0.0.1"),
        ("ftp://example.com/a.dem", PUBLIC),
        ("http://user:pw@example.com/a.dem", PUBLIC),
    ],
)
def test_a_link_into_the_servers_own_network_is_refused(link, address):
    with pytest.raises(remote.RemoteError):
        remote.check(link, resolve=_resolves_to(address))


def test_a_public_link_may_be_fetched():
    assert remote.check("https://example.com/a.dem", resolve=_resolves_to(PUBLIC)) == "example.com"


@contextmanager
def _serving(routes: dict[str, tuple[int, dict, bytes]]):
    """A local server; the fetch is told its host is public (only the guard is faked)."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            code, headers, body = routes.get(self.path, (404, {}, b""))
            self.send_response(code)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()


DEMO = b"PBDEMS2\x00" + b"\x01" * 100


def test_a_demo_is_fetched_and_named_for_its_kind(tmp_path):
    routes = {
        "/share": (302, {"Location": "/files/x"}, b""),
        "/files/x": (200, {}, DEMO),
    }
    with _serving(routes) as base:
        got = remote.fetch(base + "/share", tmp_path, 10_000, resolve=_resolves_to(PUBLIC))
    assert got.suffix == ".dem" and got.read_bytes() == DEMO


def test_a_redirect_into_the_network_a_login_page_or_too_much_is_refused(tmp_path):
    routes = {
        "/inside": (302, {"Location": "http://10.0.0.5/secret"}, b""),
        "/login": (200, {"Content-Type": "text/html"}, b"<html>sign in</html>"),
        "/big": (200, {}, DEMO),
    }
    public_then_private = {"n": 0}

    def resolve(host, port):
        if host == "10.0.0.5":
            return [(2, 1, 6, "", ("10.0.0.5", port))]
        public_then_private["n"] += 1
        return [(2, 1, 6, "", (PUBLIC, port))]

    with _serving(routes) as base:
        with pytest.raises(remote.RemoteError, match="Дотоод"):
            remote.fetch(base + "/inside", tmp_path, 10_000, resolve=resolve)
        with pytest.raises(remote.RemoteError, match="archive биш"):
            remote.fetch(base + "/login", tmp_path, 10_000, resolve=resolve)
        with pytest.raises(remote.RemoteError, match="MB"):
            remote.fetch(base + "/big", tmp_path, 50, resolve=resolve)
