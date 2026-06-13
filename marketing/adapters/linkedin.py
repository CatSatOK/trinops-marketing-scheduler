"""LinkedIn adapter — posts a UGC share to the configured author.

Used only when DEMO_MODE=false. Requires an OAuth access token with the
`w_member_social` scope and the author's person/organisation URN.
"""

import httpx

from marketing.adapters.base import DraftPost, PostError, PostReceipt
from marketing.config import Settings
from marketing.logging_conf import get_logger

logger = get_logger(__name__)

_API = "https://api.linkedin.com/v2/ugcPosts"


class LinkedInAdapter:
    name = "linkedin"

    def __init__(self, settings: Settings) -> None:
        self._token = settings.linkedin_access_token
        self._author = settings.linkedin_author_urn

    def validate_credentials(self) -> bool:
        return bool(self._token and self._author)

    def post(self, draft: DraftPost) -> PostReceipt:
        if not self.validate_credentials():
            raise PostError("linkedin: missing access token or author URN")
        body = {
            "author": self._author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": draft.content},
                    "shareMediaCategory": "ARTICLE" if draft.media_url else "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }
        if draft.media_url:
            body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
                {"status": "READY", "originalUrl": draft.media_url}
            ]
        headers = {
            "Authorization": f"Bearer {self._token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.post(_API, json=body, headers=headers, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise PostError(f"linkedin: {exc}") from exc
        post_id = resp.headers.get("x-restli-id") or resp.json().get("id", "")
        logger.info("linkedin: published %s", post_id)
        return PostReceipt(platform_post_id=post_id)
