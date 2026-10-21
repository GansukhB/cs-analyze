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
    # Celery's default queue, a plain Redis list on the broker DB: the Scouts.
    celery_queue: str = "celery"
    # Short work that must not wait behind a Scout (the Review refresh, docs/adr/0008).
    celery_light_queue: str = "light"
    # Parsing that isn't a Scout's (uploads): it shares the host's one heavy
    # permit with the Scouts' parse step (app/services/heavy.py, OPS-6). The worker
    # consumes all three queues, with a thread for each.
    celery_parse_queue: str = "parse"

    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    # See docs/adr/0001-jwt-in-localstorage.md before changing token lifetime or storage.
    # 12 hours (docs/plans WS-6): a token stolen through XSS works for half as long.
    access_token_expire_minutes: int = 60 * 12

    cors_origins: list[str] = ["http://localhost:5173"]
    # Swagger and the raw schema. Off in production (ansible/templates/api.env.j2):
    # they map every endpoint for anyone who finds the host.
    api_docs: bool = True
    # The commit a deploy shipped (ansible/deploy.yml), shown in the footer.
    deployed_commit: str = ""

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
    # A demo download must begin within this (Cloudflare can serve a page instead
    # of the file, and then none ever starts) and abort once no byte has arrived
    # for the stall limit. The transfer itself is unbounded: archives run 350-900 MB.
    hltv_download_start_timeout_ms: int = 120_000
    hltv_download_stall_seconds: int = 120
    hltv_user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    )

    # The a/b/c windows on the scout form.
    analysis_default_matches: int = 1
    analysis_max_matches: int = 5

    # The Assistant (app/services/assistant.py). Both halves are optional: with no
    # Claude key the chat says it isn't configured; with no ElevenLabs pair it
    # answers in text only and the mic is hidden.
    claude_api_key: SecretStr = SecretStr("")
    claude_model: str = "claude-sonnet-5-5"
    # A chat turn is a few tool calls and a short answer, not a long agentic task.
    claude_effort: str = "medium"
    # Thinking counts against this too; the reply itself is five paragraphs at most.
    claude_max_tokens: int = 16_000
    # Prior turns resent with each question: bounds the bill and the memory.
    claude_max_history_turns: int = 12
    # Per User and UTC day: past the cost cap the chat says so; past the speech
    # cap it answers in text (docs/plans AS-2).
    assistant_daily_usd: float = 5.0
    assistant_daily_tts_chars: int = 60_000
    elevenlabs_api_key: SecretStr = SecretStr("")
    elevenlabs_voice_id: str = ""
    # v4 is the first generation that supports Mongolian; turbo speaks about twice
    # as fast as v4 (1.4 s vs 3 s a paragraph) for nearly the same clarity.
    elevenlabs_model: str = "eleven_v4_turbo"
    elevenlabs_stt_model: str = "scribe_v2"
    # The Assistant's Users speak Mongolian; pinned so a short question isn't read as Russian.
    elevenlabs_stt_language: str = "mon"
    elevenlabs_timeout: int = 30
    # OPS-5: alerts go to this Telegram chat when both are set; otherwise only
    # the log has them. The thresholds `cli watch` checks every 5 minutes.
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""
    alert_disk_percent: float = 85.0
    alert_stage_minutes: int = 45
    alert_blocked_in_a_row: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
