"""Demo adapter — stands in for any real platform when DEMO_MODE=true.

Instead of calling a platform API, it writes the rendered post to
`data/published/<platform>/` so the demo is fully inspectable without any
credentials. One platform (DEMO_FAIL_PLATFORM) is made to fail deterministically
so the partial-failure path — PARTIAL campaign status and the per-platform retry
button — is exercised end to end.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from marketing.adapters.base import DraftPost, PostError, PostReceipt
from marketing.config import Settings
from marketing.logging_conf import get_logger

logger = get_logger(__name__)


class DemoAdapter:
    def __init__(self, platform: str, settings: Settings) -> None:
        self.name = platform
        self._dir = Path(settings.published_dir) / platform
        self._fail = settings.demo_fail_platform == platform

    def validate_credentials(self) -> bool:
        return True

    def post(self, draft: DraftPost) -> PostReceipt:
        if self._fail:
            raise PostError(f"{self.name}: simulated publish failure (demo)")
        self._dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        post_id = f"{self.name}-{stamp}"
        path = self._dir / f"{stamp}.json"
        path.write_text(
            json.dumps(
                {
                    "platform": self.name,
                    "platform_post_id": post_id,
                    "title": draft.title,
                    "content": draft.content,
                    "media_url": draft.media_url,
                    "published_at": stamp,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info("demo: wrote %s for %s", path.name, self.name)
        return PostReceipt(platform_post_id=post_id)
