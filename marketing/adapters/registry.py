"""Adapter factory — maps platform names to adapter instances.

`_REAL_ADAPTERS` is the single registration point: adding a platform means
writing one adapter file and adding one line here. In demo mode every platform
is served by `DemoAdapter`, so the dispatch path runs without credentials.
"""

from marketing.adapters.base import PlatformAdapter
from marketing.adapters.demo import DemoAdapter
from marketing.adapters.facebook import FacebookAdapter
from marketing.adapters.linkedin import LinkedInAdapter
from marketing.adapters.twitter import TwitterAdapter
from marketing.config import Settings
from marketing.logging_conf import get_logger

logger = get_logger(__name__)

_REAL_ADAPTERS = {
    "linkedin": LinkedInAdapter,
    "twitter": TwitterAdapter,
    "facebook": FacebookAdapter,
}


def available_platforms() -> list[str]:
    return sorted(_REAL_ADAPTERS)


def get_adapters(settings: Settings) -> dict[str, PlatformAdapter]:
    """Return one adapter per enabled platform, keyed by platform name."""
    adapters: dict[str, PlatformAdapter] = {}
    for platform in settings.enabled_platforms:
        if platform not in _REAL_ADAPTERS:
            logger.warning("unknown platform %r in ENABLED_PLATFORMS — skipping", platform)
            continue
        if settings.demo_mode:
            adapters[platform] = DemoAdapter(platform, settings)
        else:
            adapters[platform] = _REAL_ADAPTERS[platform](settings)
    return adapters
