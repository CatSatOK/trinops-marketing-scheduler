"""Application settings.

Every company-specific or environment-specific value lives in `.env`
(see `.env.example`). Nothing client-identifying is hardcoded.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    demo_mode: bool = True

    # Protects staff/admin endpoints when demo_mode is false (sent as X-API-Key).
    admin_api_key: str = ""

    # Inbound lead webhook hardening. The webhook is unauthenticated by design
    # (any form provider can POST to it), so it gets its own guards:
    #  - rate limit per caller IP (per minute); 0 disables the limit
    #  - hard cap on request body size in bytes (reject anything larger)
    #  - optional shared secret: when set, callers must send it as the
    #    X-Webhook-Secret header. Empty (the demo default) leaves it open.
    webhook_rate_limit_per_minute: int = 60
    webhook_max_bytes: int = 16384
    webhook_secret: str = ""

    database_url: str = "sqlite:///./data/marketing.db"

    # How often the dispatcher checks the queue for campaigns whose time has come
    dispatch_interval_minutes: int = 5

    # Platforms the scheduler publishes to. Adding one is a new adapter file plus
    # its name here — nothing in the scheduler or publisher changes.
    enabled_platforms: list[str] = ["linkedin", "twitter", "facebook"]

    # In demo mode this platform's posts fail on the FIRST attempt only, then
    # succeed on retry — a simulated transient outage so the PARTIAL status and
    # the per-platform retry button can both be demonstrated end to end.
    demo_flaky_platform: str = "facebook"

    # Platform credentials — only read when demo_mode is false.
    linkedin_access_token: str = ""
    linkedin_author_urn: str = ""
    twitter_bearer_token: str = ""
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""
    facebook_page_id: str = ""
    facebook_page_access_token: str = ""

    # Lead routing — which contact owns a given service interest.
    lead_default_contact: str = "sales@example.com"
    lead_routing: dict[str, str] = {
        "automation": "automation@example.com",
        "transport": "transport@example.com",
        "consulting": "consulting@example.com",
    }

    published_dir: str = "data/published"
    seed_campaigns_file: str = "seed/campaigns.json"
    seed_leads_file: str = "seed/leads.json"

    def ensure_dirs(self) -> None:
        Path(self.published_dir).mkdir(parents=True, exist_ok=True)
        db_path = self.database_url.removeprefix("sqlite:///")
        if db_path != self.database_url:  # only for sqlite URLs
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
