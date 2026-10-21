"""Headless-Chromium access to HLTV.org.

HLTV sits behind a Cloudflare managed challenge. Two consequences shape this
module, both verified against the live site:

* Plain HTTP clients are refused. ``requests``/``urllib``/``curl`` get a 403
  "Just a moment..." interstitial on every path, regardless of headers, so all
  reading happens inside a real browser.
* The ``cf_clearance`` cookie the browser earns **cannot** be handed off to an
  HTTP client to do the heavy download. Cloudflare binds it to the TLS
  fingerprint of the client that earned it, so a copied cookie still yields 403.
  Demo downloads therefore also run inside the browser (:meth:`HltvBrowser.download`),
  which is why there is no ``requests`` dependency here.

The challenge can also re-fire mid-session on a page that worked a moment ago,
so :meth:`HltvBrowser.open` retries rather than treating one 403 as fatal.

.. important::
   Launch the **full Chromium build** (``channel="chromium"``), not Playwright's
   default "headless shell". Cloudflare fingerprints the shell and serves it an
   interactive challenge that never resolves -- measured against the live site,
   the shell was blocked on ``/search`` while the full build sailed through.
   ``playwright install chromium`` fetches both, so this costs no extra setup.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

from app.config import get_settings
from app.services import alerts

logger = logging.getLogger(__name__)

BASE_URL = "https://www.hltv.org"

# Titles/markers Cloudflare serves while it is challenging us.
_CHALLENGE_MARKERS = ("just a moment", "attention required", "checking your browser")


class HltvBlocked(RuntimeError):
    """Cloudflare would not let us through, even after retrying."""


def _is_challenge(status: int, title: str, url: str) -> bool:
    if status in (403, 429, 503):
        return True
    if any(m in (title or "").lower() for m in _CHALLENGE_MARKERS):
        return True
    return "__cf_chl" in (url or "")


class HltvBrowser:
    """A Chromium session that has cleared Cloudflare.

    Use as a context manager; a single page is reused for every navigation so
    the clearance cookie is kept warm::

        with HltvBrowser() as browser:
            page = browser.open("/results?team=9565")
    """

    def __init__(
        self,
        headless: bool | None = None,
        timeout_ms: int | None = None,
        retries: int | None = None,
        channel: str | None = None,
    ):
        settings = get_settings()
        self.headless = settings.hltv_headless if headless is None else headless
        self.timeout_ms = timeout_ms or settings.hltv_timeout_ms
        self.retries = settings.hltv_challenge_retries if retries is None else retries
        self.channel = channel or settings.hltv_browser_channel
        self.user_agent = settings.hltv_user_agent
        self.request_delay_ms = settings.hltv_request_delay_ms
        self._pw = self._browser = self._ctx = self._page = None
        self._crashed = False
        self._last_request = 0.0

    # -- lifecycle ---------------------------------------------------------
    def __enter__(self) -> HltvBrowser:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on install
            raise HltvBlocked("playwright is not installed. Run: npm run setup") from exc
        self._PlaywrightError = PlaywrightError

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(
                headless=self.headless,
                channel=self.channel or None,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    # A small VM's /dev/shm is often a few dozen MB; Chromium's
                    # default shared-memory usage for large transfers (a 100-500
                    # MB demo download counts) can exhaust it, which surfaces as
                    # net::ERR_INSUFFICIENT_RESOURCES rather than an OOM. This
                    # trades a little speed for spilling to /tmp instead.
                    "--disable-dev-shm-usage",
                ],
            )
        except Exception as exc:  # browser binary missing, etc.
            self._pw.stop()
            self.__exit__(None, None, None)
            raise HltvBlocked(
                f"Could not launch Chromium channel={self.channel!r} ({exc}). "
                "Run: uv run --directory apps/api playwright install chromium"
            ) from exc

        self._ctx = self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            accept_downloads=True,
        )
        self._ctx.set_default_timeout(self.timeout_ms)
        # Cheap de-automation: the headless flag Cloudflare reads most cheaply.
        self._ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        self._new_page()
        # Landing on the front page first is what earns the clearance cookie.
        self.open("/")
        return self

    def __exit__(self, *exc_info) -> None:
        for closer in (self._ctx, self._browser):
            try:
                if closer:
                    closer.close()
            except Exception:  # pragma: no cover - best-effort teardown
                logger.debug("error closing browser", exc_info=True)
        if self._pw:
            try:
                self._pw.stop()
            except Exception:  # pragma: no cover
                logger.debug("error stopping playwright", exc_info=True)

    @property
    def page(self):
        if self._page is None:
            raise RuntimeError("HltvBrowser must be used as a context manager")
        return self._page

    def _new_page(self) -> None:
        self._page = self._ctx.new_page()
        self._crashed = False
        self._page.on("crash", lambda _page: setattr(self, "_crashed", True))

    def _tab_alive(self) -> bool:
        # The "crash" event can arrive after the call that failed has already
        # raised, so ask the tab itself too: a dead one rejects at once.
        if self._crashed or self.page.is_closed():
            return False
        try:
            self.page.evaluate("1")
        except self._PlaywrightError:
            return False
        return True

    def recover_page(self) -> bool:
        """Swap a crashed or closed tab for a new one; True if it had to.

        A renderer crash (seen in production as ERR_INSUFFICIENT_RESOURCES, then
        "Page crashed") kills the tab, not the browser: the context and its
        clearance cookie live on, so a new tab carries on where the old one died.
        """
        if self._tab_alive():
            return False
        try:
            self.page.close()
        except Exception:  # pragma: no cover - the tab is already gone
            logger.debug("could not close the crashed tab", exc_info=True)
        self._new_page()
        logger.warning("the tab crashed; continuing in a new one")
        return True

    def is_connected(self) -> bool:
        """False once the underlying Chromium process is gone.

        The clearest real-world cause is the OS OOM-killer taking it out
        mid-session (seen in production: a `chrome` child under the celery
        worker's cgroup, killed while a fetch job had it open) -- at that
        point every further ``open()``/``download()`` call fails the same way
        and retrying per-call is retrying against a corpse. Callers use this
        to stop trying rather than burn the retry budget on every item still
        queued.
        """
        return bool(self._browser) and self._browser.is_connected()

    # -- navigation --------------------------------------------------------
    def open(self, path: str, settle_ms: int = 1200):
        """Navigate to ``path`` (absolute or site-relative), retrying challenges.

        Returns the live page. Raises :class:`HltvBlocked` if Cloudflare never
        lets us through.
        """
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        last = "unknown"
        self._pace()

        for attempt in range(1, self.retries + 1):
            try:
                response = self.page.goto(
                    url, wait_until="domcontentloaded", timeout=self.timeout_ms
                )
                status = response.status if response else 0
                title = self.page.title()
                if not _is_challenge(status, title, self.page.url):
                    # Let late client-side rendering finish before callers read DOM.
                    self.page.wait_for_timeout(settle_ms)
                    alerts.hltv_through()
                    return self.page

                last = f"status={status} title={title!r}"
                logger.info(
                    "cloudflare challenge on %s (%s), attempt %s/%s",
                    url,
                    last,
                    attempt,
                    self.retries,
                )
                # A managed challenge clears itself in a few seconds; give it time.
                self.page.wait_for_timeout(5000 + 2000 * attempt)
            except self._PlaywrightError as exc:
                # goto() itself can throw rather than return a response -- a
                # transient net-level failure (ERR_INSUFFICIENT_RESOURCES,
                # ERR_CONNECTION_RESET, a timeout) rather than a Cloudflare
                # challenge, or the tab can crash under any of these calls. Each
                # deserves the same retry-with-backoff rather than killing the
                # whole run on one flaky navigation.
                last = f"navigation error: {exc}"
                logger.warning(
                    "navigation failed for %s (%s), attempt %s/%s", url, last, attempt, self.retries
                )
                # Not page.wait_for_timeout(): the page may be the thing that died.
                self.recover_page()
                time.sleep((3000 + 2000 * attempt) / 1000)

        alerts.hltv_blocked()  # OPS-5: several in a row and someone is told
        raise HltvBlocked(
            f"could not reach {url} after {self.retries} attempts ({last}). "
            "Try again shortly, or set HLTV_HEADLESS=false to solve it interactively."
        )

    def _pace(self) -> None:
        """Keep a floor between requests: we are a guest on someone's server."""
        gap = self.request_delay_ms / 1000
        elapsed = time.monotonic() - self._last_request
        if self._last_request and elapsed < gap:
            time.sleep(gap - elapsed)
        self._last_request = time.monotonic()

    # -- downloading -------------------------------------------------------
    def download(
        self,
        url: str,
        dest: Path,
        timeout_ms: int = 120_000,
        on_progress: Callable | None = None,
        stall_seconds: float | None = None,
    ) -> Path:
        """Download ``url`` to ``dest`` using the browser itself.

        Returns the written path. ``timeout_ms`` bounds how long the download
        may take to *begin* (0 waits forever): when Cloudflare serves a page
        instead of the file, no download ever starts, and the only Scout slot
        must not wait on it. The transfer itself has no deadline, since a large
        archive takes minutes; ``stall_seconds`` instead aborts it once no byte
        has arrived for that long. The stall watch needs Chromium's progress
        events; without them the transfer runs unwatched, as it always did.

        ``on_progress(received, total, elapsed)`` is called perhaps once a second
        while the bytes arrive -- ``received``/``total`` are None when Chromium
        is not telling us (see :class:`_DownloadWatch`), leaving ``elapsed`` as
        the only honest thing to report. No arithmetic is done here: the caller
        owns how a rate or an estimate is worded.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        full = url if url.startswith("http") else f"{BASE_URL}{url}"

        watch = _DownloadWatch(self.page, on_progress) if on_progress or stall_seconds else None
        download = None
        try:
            with self.page.expect_download(timeout=timeout_ms) as info:
                # A plain goto() to a file URL aborts the navigation; assigning
                # location lets Chromium hand it to the download manager instead.
                self.page.evaluate("(u) => { window.location.href = u; }", full)
            download = info.value

            if stall_seconds and watch is not None and watch.attached:
                # save_as() and failure() block until the last byte, so the stall
                # is watched here instead: waiting on the page pumps the CDP
                # progress events the watch counts.
                while not watch.finished:
                    self.page.wait_for_timeout(500)
                    if watch.stalled_for() > stall_seconds:
                        download.cancel()
                        raise HltvBlocked(
                            f"Download of {full} stalled: no data for {stall_seconds:.0f} s"
                        )

            failure = download.failure()
            if failure:
                raise HltvBlocked(f"Download failed for {full}: {failure}")

            download.save_as(dest)
        except self._PlaywrightError as exc:
            # The tab died under the download. The caller skips this one item.
            self.recover_page()
            raise HltvBlocked(f"Download of {full} broke off ({exc})") from exc
        finally:
            if watch:
                watch.close()
            if download is not None:
                # save_as() copies; Chromium's own file stays in Playwright's temp
                # dir until the context closes. Kept, a 15-match run piles up
                # ~7 GB there, in RAM wherever /tmp is a tmpfs.
                try:
                    download.delete()
                except Exception:  # pragma: no cover - best-effort cleanup
                    logger.debug("could not delete the download's temp file", exc_info=True)
        return dest


class _DownloadWatch:
    """Byte-level progress for a download, read off Chromium rather than guessed.

    Playwright's ``Download`` object exposes no progress at all -- ``save_as()``
    blocks until the last byte -- but Chromium reports it over CDP. Which events
    reach *us* is the catch, measured against a throttled local server:

    * ``Browser.downloadProgress`` goes only to the CDP session that sent
      ``Browser.setDownloadBehavior`` with ``eventsEnabled``. That is Playwright's
      own root session (it does so for every context created with
      ``accept_downloads``), so a second browser session subscribing to the same
      events hears nothing at all.
    * ``Page.downloadProgress`` goes to any session on the page that has sent
      ``Page.enable``. CDP marks it deprecated in favour of the Browser event, but
      it is still emitted, and it needs nothing switched on that Playwright owns.

    So this listens on a page session of its own. Never send
    ``setDownloadBehavior`` from here to get the Browser events instead: Playwright
    owns that call, and overriding its behaviour or download path breaks
    ``expect_download`` outright.

    The heartbeat covers two silences. If no byte count has arrived a few seconds
    in (a future Chromium dropping the Page events), it reports elapsed time on
    its own -- a moving line with no numbers is honest; an invented percentage is
    not. And Chromium only reports when bytes arrive, so once they have, it
    repeats the last count while they stop, which is what lets a stall read as one.
    A server that sends no ``Content-Length`` yields counts without a total.
    """

    # A 500 MB archive fires thousands of progress events. The caller writes to a
    # database and a socket, so it hears from us on a human timescale instead.
    MIN_INTERVAL_SEC = 1.0
    MIN_STEP_PCT = 2.0
    # How long to wait for the first byte count before falling back to a clock.
    QUIET_BEFORE_HEARTBEAT_SEC = 4.0
    HEARTBEAT_SEC = 5.0

    def __init__(self, page, on_progress: Callable | None = None):
        self.on_progress = on_progress
        self.started = time.monotonic()
        self.guid: str | None = None
        self.received = self.total = 0
        self.saw_bytes = False
        # When the byte count last grew, and whether Chromium called it done
        # (completed or cancelled): what the stall watch in download() reads.
        self.grew_at = self.started
        self.finished = False
        self._last_at = 0.0
        self._last_pct = -100.0
        self._closed = threading.Event()
        # CDP events arrive on the Playwright thread, the heartbeat on its own;
        # the caller's session must only ever be used by one of them at a time.
        self._lock = threading.Lock()
        self._session = None

        try:
            self._session = page.context.new_cdp_session(page)
            self._session.on("Page.downloadWillBegin", self._will_begin)
            self._session.on("Page.downloadProgress", self._progress)
            self._session.send("Page.enable")
        except Exception:  # CDP is a nicety; a download must not fail without it
            logger.debug("could not attach a CDP download watcher", exc_info=True)
            self._session = None

        self._heartbeat = threading.Thread(target=self._tick, daemon=True)
        self._heartbeat.start()

    # -- CDP events (dispatched on the Playwright thread) ------------------
    def _will_begin(self, event) -> None:
        # The session sees only this page's downloads; ours is the first to
        # begin after we asked for it, and its guid keys the progress events.
        if self.guid is None:
            self.guid = event.get("guid")

    def _progress(self, event) -> None:
        if self.guid is not None and event.get("guid") != self.guid:
            return
        received = int(event.get("receivedBytes") or 0)
        if received > self.received:
            self.grew_at = time.monotonic()
        self.received = received
        self.total = int(event.get("totalBytes") or 0)
        self.saw_bytes = True
        state = event.get("state")
        if state in ("completed", "canceled"):
            self.finished = True
        if state == "completed":
            self._emit(force=True)
            return
        self._emit()

    @property
    def attached(self) -> bool:
        """Whether Chromium's progress events reach us at all."""
        return self._session is not None

    def stalled_for(self) -> float:
        """Seconds since the byte count last grew (or since the start, before any)."""
        return time.monotonic() - self.grew_at

    # -- the clock, for when the events say nothing ------------------------
    def _tick(self) -> None:
        while not self._closed.wait(self.HEARTBEAT_SEC):
            now = time.monotonic()
            if not self.saw_bytes:
                if now - self.started >= self.QUIET_BEFORE_HEARTBEAT_SEC:
                    self._call(None, None)
            elif now - self._last_at >= self.HEARTBEAT_SEC:
                self._call(self.received, self.total or None)

    def _emit(self, force: bool = False) -> None:
        now = time.monotonic()
        pct = 100.0 * self.received / self.total if self.total else 0.0
        if (
            not force
            and now - self._last_at < self.MIN_INTERVAL_SEC
            and pct - self._last_pct < self.MIN_STEP_PCT
        ):
            return
        self._last_at, self._last_pct = now, pct
        self._call(self.received, self.total or None)

    def _call(self, received, total) -> None:
        with self._lock:
            if self._closed.is_set() or self.on_progress is None:
                return
            try:
                self.on_progress(received, total, time.monotonic() - self.started)
            except Exception:  # a progress report must never kill a download
                logger.debug("download progress callback failed", exc_info=True)

    def close(self) -> None:
        self._closed.set()
        if self._session is not None:
            try:
                self._session.detach()
            except Exception:  # pragma: no cover - best-effort teardown
                logger.debug("could not detach the CDP download watcher", exc_info=True)
