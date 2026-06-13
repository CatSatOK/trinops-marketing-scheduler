"""APScheduler job: publish campaigns whose scheduled time has arrived.

- dispatch_due_campaigns: the testable core — finds QUEUED campaigns due now and
  publishes each through the platform adapters.
- the scheduler runs it every DISPATCH_INTERVAL_MINUTES, and once at startup so
  the demo shows published results immediately.
"""

from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from marketing.adapters.base import PlatformAdapter
from marketing.adapters.registry import get_adapters
from marketing.config import Settings, get_settings
from marketing.database import session_scope
from marketing.logging_conf import get_logger
from marketing.models import Campaign, CampaignStatus
from marketing.publisher import publish_campaign

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def dispatch_due_campaigns(
    session: Session,
    settings: Settings,
    adapters: dict[str, PlatformAdapter],
    now: datetime | None = None,
) -> list[Campaign]:
    """Publish every QUEUED campaign whose scheduled_at has passed."""
    now = now or datetime.now(timezone.utc)
    stmt = (
        select(Campaign)
        .where(Campaign.status == CampaignStatus.QUEUED, Campaign.scheduled_at <= now)
        .order_by(Campaign.scheduled_at)
    )
    due = list(session.scalars(stmt))
    for campaign in due:
        publish_campaign(session, campaign, adapters)
    if due:
        logger.info("dispatched %d due campaign(s)", len(due))
    return due


def dispatch_job() -> None:
    settings = get_settings()
    adapters = get_adapters(settings)
    try:
        with session_scope() as session:
            dispatch_due_campaigns(session, settings, adapters)
    except Exception:
        logger.exception("campaign dispatch failed")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    settings = get_settings()
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        dispatch_job,
        trigger="interval",
        minutes=settings.dispatch_interval_minutes,
        id="dispatch_due_campaigns",
        coalesce=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info("scheduler started: dispatch every %d min", settings.dispatch_interval_minutes)
    # publish anything already due (and the seed campaigns in demo mode)
    dispatch_job()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
