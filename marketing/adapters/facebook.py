"""Facebook Pages adapter — publishes a feed post via the Graph API.

Used only when DEMO_MODE=false. Requires a Page id and a Page access token
with `pages_manage_posts`.
"""

import httpx

from marketing.adapters.base import DraftPost, PostError, PostReceipt
from marketing.config import Settings
from marketing.logging_conf import get_logger

logger = get_logger(__name__)

_GRAPH = "https://graph.facebook.com/v19.0"


class FacebookAdapter:
    name = "facebook"

    def __init__(self, settings: Settings) -> None:
        self._page_id = settings.facebook_page_id
        self._token = settings.facebook_page_access_token

    def validate_credentials(self) -> bool:
        return bool(self._page_id and self._token)

    def post(self, draft: DraftPost, attempt: int = 1) -> PostReceipt:
        if not self.validate_credentials():
            raise PostError("facebook: missing page id or access token")
        # Photo posts and plain feed posts use different endpoints.
        if draft.media_url:
            endpoint = f"{_GRAPH}/{self._page_id}/photos"
            payload = {"url": draft.media_url, "caption": draft.content}
        else:
            endpoint = f"{_GRAPH}/{self._page_id}/feed"
            payload = {"message": draft.content}
        payload["access_token"] = self._token
        try:
            resp = httpx.post(endpoint, data=payload, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise PostError(f"facebook: {exc}") from exc
        data = resp.json()
        post_id = data.get("post_id") or data.get("id", "")
        logger.info("facebook: published %s", post_id)
        return PostReceipt(platform_post_id=post_id)
