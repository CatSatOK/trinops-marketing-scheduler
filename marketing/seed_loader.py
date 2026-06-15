"""Demo seed: load campaigns and leads on first start.

Campaigns use an hour offset (`scheduled_offset_hours`) rather than fixed
timestamps so the demo always contains a realistic mix of already-due posts
(published at startup by the dispatcher) and future queued posts. Leads are
loaded as raw form payloads and run through the real qualifier.
"""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from marketing.config import Settings
from marketing.lead_qualifier import qualify
from marketing.logging_conf import get_logger
from marketing.models import Campaign, CampaignStatus, Lead

logger = get_logger(__name__)


def load_seed_campaigns(session: Session, settings: Settings) -> int:
    if not settings.demo_mode:
        return 0
    if session.scalar(select(Campaign).limit(1)) is not None:
        return 0

    try:
        records = json.loads(open(settings.seed_campaigns_file, encoding="utf-8").read())
    except FileNotFoundError:
        logger.warning("seed file %s not found", settings.seed_campaigns_file)
        return 0

    now = datetime.now(timezone.utc)
    for r in records:
        campaign = Campaign(
            title=r["title"],
            content=r["content"],
            media_url=r.get("media_url"),
            scheduled_at=now + timedelta(hours=r["scheduled_offset_hours"]),
            status=CampaignStatus.QUEUED,
        )
        campaign.platforms = r["platforms"]
        session.add(campaign)
    logger.info("seeded %d campaign(s)", len(records))
    return len(records)


def load_seed_leads(session: Session, settings: Settings) -> int:
    if not settings.demo_mode:
        return 0
    if session.scalar(select(Lead).limit(1)) is not None:
        return 0

    try:
        records = json.loads(open(settings.seed_leads_file, encoding="utf-8").read())
    except FileNotFoundError:
        logger.warning("seed file %s not found", settings.seed_leads_file)
        return 0

    for form in records:
        scored = qualify(form, settings)
        session.add(
            Lead(
                source=form.get("source", "webhook"),
                raw_data=json.dumps(form),
                name=form.get("name"),
                company=form.get("company"),
                email=form.get("email"),
                service_interest=scored.service_interest,
                score=scored.score,
                category=scored.category,
                priority=scored.priority,
                routed_to=scored.routed_to,
                notes=form.get("notes"),
            )
        )
    logger.info("seeded %d lead(s)", len(records))
    return len(records)
