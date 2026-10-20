"""Small platform guards: credentials never reach the page, wedged tools are cut off."""

import sys

import pytest

from app.routers.jobs import redact_url
from app.services import archive


@pytest.mark.parametrize(
    ("url", "shown"),
    [
        ("redis://cs2:s3cret@10.0.0.5:6379/10", "redis://***@10.0.0.5:6379/10"),
        ("redis://:s3cret@localhost:16379/0", "redis://***@localhost:16379/0"),
        ("redis://localhost:16379/0", "redis://localhost:16379/0"),
        ("rediss://user@cache.example:6380/1", "rediss://***@cache.example:6380/1"),
    ],
)
def test_the_broker_url_loses_its_credentials(url, shown):
    assert redact_url(url) == shown
    assert "s3cret" not in redact_url(url)


def test_a_wedged_extraction_is_killed():
    with pytest.raises(archive.ArchiveError, match="longer than"):
        archive._run_watched(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            lambda: None,
            every=0.1,
            timeout=0.5,
        )


def test_a_wedged_listing_is_killed(monkeypatch):
    monkeypatch.setattr(archive, "TAR", sys.executable)
    with pytest.raises(archive.ArchiveError, match="longer than"):
        archive._run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
