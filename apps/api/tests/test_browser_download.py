"""Download progress through a real Chromium, against a throttled local server.

The pipeline tests fake the browser, so they cannot tell whether Chromium's
progress events reach us at all. They didn't once: the watcher listened for
events that only Playwright's own CDP session receives, and every real download
showed a clock instead of bytes. Skipped when Chromium is not installed.
"""

import http.server
import threading
import time

import pytest

from app.services import browser as browser_module
from app.services.browser import HltvBlocked, HltvBrowser, _DownloadWatch

SIZE = 2_000_000
CHUNK = 100_000
RATE = 2_000_000  # bytes a second, so a download takes about a second
STALL_SEC = 1.5


class _Server(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            body = b"<html><head><title>ok</title></head></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-rar-compressed")
        self.send_header("Content-Disposition", 'attachment; filename="demo.rar"')
        self.send_header("Content-Length", str(SIZE))
        self.end_headers()
        sent = 0
        try:
            while sent < SIZE:
                if self.path == "/stall.rar" and sent == SIZE // 2:
                    time.sleep(STALL_SEC)
                self.wfile.write(b"\0" * CHUNK)
                sent += CHUNK
                time.sleep(CHUNK / RATE)
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture(scope="module")
def browser():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(browser_module, "BASE_URL", f"http://127.0.0.1:{server.server_address[1]}")
        try:
            session = HltvBrowser(headless=True, retries=1).__enter__()
        except HltvBlocked as exc:
            server.shutdown()
            pytest.skip(f"Chromium is not available: {exc}")
        try:
            yield session
        finally:
            session.__exit__(None, None, None)
            server.shutdown()


def test_download_reports_bytes_while_they_arrive(browser, tmp_path):
    calls = []
    dest = browser.download(
        "/demo.rar", tmp_path / "demo.rar", on_progress=lambda *a: calls.append(a)
    )

    assert dest.stat().st_size == SIZE
    counted = [(received, total) for received, total, _ in calls if received is not None]
    assert any(0 < received < SIZE for received, _ in counted), calls
    assert all(total == SIZE for _, total in counted)
    assert counted[-1] == (SIZE, SIZE)


def test_a_stall_repeats_the_last_count(browser, tmp_path, monkeypatch):
    monkeypatch.setattr(_DownloadWatch, "HEARTBEAT_SEC", 0.4)
    calls = []
    browser.download("/stall.rar", tmp_path / "stall.rar", on_progress=lambda *a: calls.append(a))

    repeated = [
        now
        for before, now in zip(calls, calls[1:], strict=False)
        if now[0] == before[0] and 0 < now[0] < SIZE and now[2] > before[2]
    ]
    assert repeated, calls


def test_the_download_leaves_no_temp_copy(browser, tmp_path, monkeypatch):
    from playwright.sync_api import Download

    deleted = []
    delete = Download.delete
    monkeypatch.setattr(Download, "delete", lambda self: deleted.append(delete(self)))
    browser.download("/demo.rar", tmp_path / "demo.rar")
    assert len(deleted) == 1


def test_a_crashed_tab_is_replaced(browser):
    first = browser.page
    with pytest.raises(Exception, match="crash"):
        first.goto("chrome://crash")
    assert browser.recover_page() is True
    assert browser.page is not first and not browser.page.is_closed()
    assert browser.open("/").title() == "ok"
    assert browser.recover_page() is False
