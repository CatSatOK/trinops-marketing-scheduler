"""X (Twitter) adapter — posts a tweet via API v2.

Used only when DEMO_MODE=false. Requires OAuth 2.0 user-context credentials
with `tweet.write`. Content is truncated to the 280-character limit.
"""

import httpx

from marketing.adapters.base import DraftPost, PostError, PostReceipt
from marketing.config import Settings
from marketing.logging_conf import get_logger

logger = get_logger(__name__)

_API = "https://api.twitter.com/2/tweets"
_MAX_CHARS = 280


class TwitterAdapter:
    name = "twitter"

    def __init__(self, settings: Settings) -> None:
        self._token = settings.twitter_access_token or settings.twitter_bearer_token

    def validate_credentials(self) -> bool:
        return bool(self._token)

    def post(self, draft: DraftPost) -> PostReceipt:
        if not self.validate_credentials():
            raise PostError("twitter: missing access token")
        text = draft.content
        if len(text) > _MAX_CHARS:
            text = text[: _MAX_CHARS - 1].rstrip() + "…"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.post(_API, json={"text": text}, headers=headers, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise PostError(f"twitter: {exc}") from exc
        post_id = resp.json().get("data", {}).get("id", "")
        logger.info("twitter: published %s", post_id)
        return PostReceipt(platform_post_id=post_id)
