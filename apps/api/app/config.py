from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "mysql+pymysql://cs:cs@mysql:3306/cs_analyze"

    # One Redis server, three logical databases.
    redis_broker_url: str = "redis://redis:6379/0"
    redis_result_url: str = "redis://redis:6379/1"
    redis_cache_url: str = "redis://redis:6379/2"
    # Celery's default queue, a plain Redis list on the broker DB.
    celery_queue: str = "celery"

    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    # See docs/adr/0001-jwt-in-localstorage.md before changing token lifetime or storage.
    access_token_expire_minutes: int = 60 * 24

    cors_origins: list[str] = ["http://localhost:5173"]

    # HLTV pipeline scratch. A job downloads, unpacks and parses one match at a time
    # under tmp/<job>/ and deletes it after (~1-2 GB at most); nothing here outlives
    # a run. What a parse produces is in MySQL (docs/adr/0002-tick-data-in-mysql.md).
    hltv_data_dir: Path = REPO_ROOT / "data"
    hltv_headless: bool = True
    # "chromium" (the full build) is mandatory: Cloudflare never clears Playwright's
    # default headless shell. See app/services/browser.py.
    hltv_browser_channel: str = "chromium"
    hltv_request_delay_ms: int = 1500
    hltv_timeout_ms: int = 60_000
    hltv_challenge_retries: int = 4
    hltv_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    )

    # The a/b/c windows on the scout form.
    analysis_default_matches: int = 1
    analysis_max_matches: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
