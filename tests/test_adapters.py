"""Adapter tests: registry wiring, demo behaviour, the shared contract."""

from pathlib import Path

import pytest

from marketing.adapters.base import DraftPost, PlatformAdapter, PostError
from marketing.adapters.demo import DemoAdapter
from marketing.adapters.facebook import FacebookAdapter
from marketing.adapters.linkedin import LinkedInAdapter
from marketing.adapters.registry import available_platforms, get_adapters
from marketing.adapters.twitter import TwitterAdapter

DRAFT = DraftPost(title="Hello", content="A test post", media_url=None)


def test_available_platforms():
    assert available_platforms() == ["facebook", "linkedin", "twitter"]


def test_demo_mode_returns_demo_adapters_for_each_platform(settings):
    adapters = get_adapters(settings)
    assert set(adapters) == {"linkedin", "twitter", "facebook"}
    assert all(isinstance(a, DemoAdapter) for a in adapters.values())


def test_live_mode_returns_real_adapters(settings):
    settings.demo_mode = False
    adapters = get_adapters(settings)
    assert isinstance(adapters["linkedin"], LinkedInAdapter)
    assert isinstance(adapters["twitter"], TwitterAdapter)
    assert isinstance(adapters["facebook"], FacebookAdapter)


def test_unknown_platform_is_skipped(settings):
    settings.enabled_platforms = ["linkedin", "myspace"]
    adapters = get_adapters(settings)
    assert set(adapters) == {"linkedin"}


def test_all_adapters_satisfy_the_protocol(settings):
    for adapter in get_adapters(settings).values():
        assert isinstance(adapter, PlatformAdapter)


def test_demo_post_writes_file_and_returns_receipt(settings):
    adapter = DemoAdapter("linkedin", settings)
    receipt = adapter.post(DRAFT)
    assert receipt.platform_post_id.startswith("linkedin-")
    files = list((Path(settings.published_dir) / "linkedin").glob("*.json"))
    assert len(files) == 1


def test_flaky_platform_fails_first_attempt_then_succeeds(settings):
    adapter = DemoAdapter("facebook", settings)  # demo_flaky_platform == facebook
    with pytest.raises(PostError):
        adapter.post(DRAFT, attempt=1)
    receipt = adapter.post(DRAFT, attempt=2)  # retry recovers
    assert receipt.platform_post_id.startswith("facebook-")


def test_non_flaky_platform_succeeds_on_first_attempt(settings):
    adapter = DemoAdapter("linkedin", settings)
    assert adapter.post(DRAFT, attempt=1).platform_post_id.startswith("linkedin-")


def test_real_adapters_report_missing_credentials(settings):
    settings.demo_mode = False
    for adapter in get_adapters(settings).values():
        assert adapter.validate_credentials() is False
        with pytest.raises(PostError):
            adapter.post(DRAFT)
