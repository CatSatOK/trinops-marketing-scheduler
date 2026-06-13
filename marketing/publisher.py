"""Cross-platform publish orchestration.

`publish_campaign` walks the campaign's target platforms, calls each adapter,
and records one PostResult per platform. A failure on one platform never aborts
the others — it is caught, logged as a FAILED result, and the campaign lands in
PARTIAL (some succeeded) or FAILED (none did). `retry_platform` re-runs a single
failed platform without touching the ones that already published.
"""

from sqlalchemy.orm import Session

from marketing.adapters.base import DraftPost, PlatformAdapter, PostError
from marketing.logging_conf import get_logger
from marketing.models import Campaign, CampaignStatus, PostResult, PostStatus, utcnow

logger = get_logger(__name__)


def _draft(campaign: Campaign) -> DraftPost:
    return DraftPost(title=campaign.title, content=campaign.content, media_url=campaign.media_url)


def _publish_one(
    campaign: Campaign, platform: str, adapter: PlatformAdapter | None
) -> PostResult:
    result = PostResult(campaign_id=campaign.id, platform=platform, status=PostStatus.PENDING)
    if adapter is None:
        result.status = PostStatus.FAILED
        result.error_message = f"no adapter registered for {platform!r}"
        logger.error("campaign %d: %s", campaign.id, result.error_message)
        return result
    try:
        receipt = adapter.post(_draft(campaign))
    except PostError as exc:
        result.status = PostStatus.FAILED
        result.error_message = str(exc)
        logger.warning("campaign %d failed on %s: %s", campaign.id, platform, exc)
    else:
        result.status = PostStatus.PUBLISHED
        result.platform_post_id = receipt.platform_post_id
        result.posted_at = utcnow()
        logger.info("campaign %d published on %s as %s", campaign.id, platform, receipt.platform_post_id)
    return result


def _recompute_status(campaign: Campaign) -> None:
    statuses = {r.platform: r.status for r in campaign.results}
    targets = campaign.platforms
    published = [p for p in targets if statuses.get(p) == PostStatus.PUBLISHED]
    if len(published) == len(targets):
        campaign.status = CampaignStatus.PUBLISHED
    elif published:
        campaign.status = CampaignStatus.PARTIAL
    else:
        campaign.status = CampaignStatus.FAILED


def publish_campaign(
    session: Session, campaign: Campaign, adapters: dict[str, PlatformAdapter]
) -> Campaign:
    """Publish every target platform that has not already succeeded."""
    campaign.status = CampaignStatus.PUBLISHING
    session.flush()

    already_done = {r.platform for r in campaign.results if r.status == PostStatus.PUBLISHED}
    for platform in campaign.platforms:
        if platform in already_done:
            continue
        # Drop any prior FAILED/PENDING attempt so there is one row per platform.
        # Removing from the relationship (delete-orphan cascade) keeps the
        # in-memory collection consistent, which session.delete alone would not.
        for stale in [r for r in campaign.results if r.platform == platform]:
            campaign.results.remove(stale)
        campaign.results.append(_publish_one(campaign, platform, adapters.get(platform)))

    session.flush()
    _recompute_status(campaign)
    logger.info("campaign %d -> %s", campaign.id, campaign.status)
    return campaign


def retry_platform(
    session: Session, campaign: Campaign, platform: str, adapters: dict[str, PlatformAdapter]
) -> Campaign:
    """Re-run a single platform that previously failed."""
    if platform not in campaign.platforms:
        raise ValueError(f"{platform!r} is not a target of campaign {campaign.id}")
    for stale in [r for r in campaign.results if r.platform == platform]:
        campaign.results.remove(stale)
    session.flush()
    campaign.results.append(_publish_one(campaign, platform, adapters.get(platform)))
    session.flush()
    _recompute_status(campaign)
    return campaign
