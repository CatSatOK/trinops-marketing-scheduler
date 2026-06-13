"""Dispatch + publish tests: due selection, partial failure, retry."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from marketing.adapters.registry import get_adapters
from marketing.models import Campaign, CampaignStatus, PostResult, PostStatus
from marketing.publisher import publish_campaign, retry_platform
from marketing.scheduler import dispatch_due_campaigns

NOW = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _campaign(platforms, offset_hours, status=CampaignStatus.QUEUED) -> Campaign:
    campaign = Campaign(
        title="Test post",
        content="Body",
        scheduled_at=NOW + timedelta(hours=offset_hours),
        status=status,
    )
    campaign.platforms = platforms
    return campaign


class TestDispatch:
    def test_publishes_due_leaves_future_queued(self, session, settings):
        due = _campaign(["linkedin", "twitter"], offset_hours=-1)
        future = _campaign(["linkedin"], offset_hours=5)
        session.add_all([due, future])
        session.flush()

        dispatched = dispatch_due_campaigns(session, settings, get_adapters(settings), now=NOW)

        assert dispatched == [due]
        assert due.status == CampaignStatus.PUBLISHED
        assert future.status == CampaignStatus.QUEUED

    def test_only_queued_campaigns_are_picked_up(self, session, settings):
        already = _campaign(["linkedin"], offset_hours=-2, status=CampaignStatus.PUBLISHED)
        session.add(already)
        session.flush()
        assert dispatch_due_campaigns(session, settings, get_adapters(settings), now=NOW) == []


class TestPublish:
    def test_all_success_is_published(self, session, settings):
        campaign = _campaign(["linkedin", "twitter"], offset_hours=-1)
        session.add(campaign)
        session.flush()

        publish_campaign(session, campaign, get_adapters(settings))

        assert campaign.status == CampaignStatus.PUBLISHED
        assert len(campaign.results) == 2
        assert all(r.status == PostStatus.PUBLISHED for r in campaign.results)
        assert all(r.platform_post_id for r in campaign.results)

    def test_one_failure_is_partial(self, session, settings):
        campaign = _campaign(["linkedin", "twitter", "facebook"], offset_hours=-1)
        session.add(campaign)
        session.flush()

        publish_campaign(session, campaign, get_adapters(settings))

        assert campaign.status == CampaignStatus.PARTIAL
        by_platform = {r.platform: r for r in campaign.results}
        assert by_platform["facebook"].status == PostStatus.FAILED
        assert by_platform["facebook"].error_message
        assert by_platform["linkedin"].status == PostStatus.PUBLISHED

    def test_all_failure_is_failed(self, session, settings):
        campaign = _campaign(["facebook"], offset_hours=-1)
        session.add(campaign)
        session.flush()
        publish_campaign(session, campaign, get_adapters(settings))
        assert campaign.status == CampaignStatus.FAILED

    def test_one_result_row_per_platform(self, session, settings):
        campaign = _campaign(["linkedin", "facebook"], offset_hours=-1)
        session.add(campaign)
        session.flush()
        publish_campaign(session, campaign, get_adapters(settings))
        publish_campaign(session, campaign, get_adapters(settings))  # re-run
        count = session.scalar(
            select(func.count()).select_from(PostResult).where(PostResult.campaign_id == campaign.id)
        )
        assert count == 2


class TestRetry:
    def test_successful_retry_promotes_to_published(self, session, settings):
        campaign = _campaign(["linkedin", "facebook"], offset_hours=-1)
        session.add(campaign)
        session.flush()
        publish_campaign(session, campaign, get_adapters(settings))
        assert campaign.status == CampaignStatus.PARTIAL

        # the facebook outage clears — retry now succeeds
        settings.demo_fail_platform = ""
        retry_platform(session, campaign, "facebook", get_adapters(settings))

        assert campaign.status == CampaignStatus.PUBLISHED
        fb = next(r for r in campaign.results if r.platform == "facebook")
        assert fb.status == PostStatus.PUBLISHED

    def test_retry_does_not_touch_published_platforms(self, session, settings):
        campaign = _campaign(["linkedin", "facebook"], offset_hours=-1)
        session.add(campaign)
        session.flush()
        publish_campaign(session, campaign, get_adapters(settings))
        linkedin_id = next(r for r in campaign.results if r.platform == "linkedin").platform_post_id

        settings.demo_fail_platform = ""
        retry_platform(session, campaign, "facebook", get_adapters(settings))

        # linkedin's original receipt is untouched
        assert (
            next(r for r in campaign.results if r.platform == "linkedin").platform_post_id
            == linkedin_id
        )
