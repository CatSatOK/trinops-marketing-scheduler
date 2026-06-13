"""Campaign endpoints: list, create, publish now, retry a failed platform."""

from collections.abc import Iterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from marketing.adapters.registry import available_platforms, get_adapters
from marketing.config import get_settings
from marketing.database import session_scope
from marketing.models import Campaign, CampaignStatus, PostResult, PostStatus
from marketing.publisher import publish_campaign, retry_platform

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


def db_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session


class PostResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform: str
    status: PostStatus
    platform_post_id: str | None
    error_message: str | None
    posted_at: datetime | None


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    media_url: str | None
    platforms: list[str]
    scheduled_at: datetime
    status: CampaignStatus
    results: list[PostResultOut]


class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    media_url: str | None = None
    platforms: list[str] = Field(min_length=1)
    scheduled_at: datetime | None = None

    @field_validator("platforms")
    @classmethod
    def known_platforms(cls, value: list[str]) -> list[str]:
        unknown = [p for p in value if p not in available_platforms()]
        if unknown:
            raise ValueError(f"unknown platform(s): {', '.join(unknown)}")
        return value


@router.get("", response_model=list[CampaignOut])
def list_campaigns(
    status: CampaignStatus | None = None,
    session: Session = Depends(db_session),
) -> list[Campaign]:
    stmt = select(Campaign).order_by(Campaign.scheduled_at)
    if status is not None:
        stmt = stmt.where(Campaign.status == status)
    return list(session.scalars(stmt))


@router.post("", response_model=CampaignOut, status_code=201)
def create_campaign(
    payload: CampaignCreate,
    session: Session = Depends(db_session),
) -> Campaign:
    campaign = Campaign(
        title=payload.title,
        content=payload.content,
        media_url=payload.media_url,
        scheduled_at=payload.scheduled_at or datetime.now(timezone.utc),
        status=CampaignStatus.QUEUED,
    )
    campaign.platforms = payload.platforms
    session.add(campaign)
    session.flush()
    return campaign


@router.post("/{campaign_id}/publish", response_model=CampaignOut)
def publish_now(
    campaign_id: int,
    session: Session = Depends(db_session),
) -> Campaign:
    campaign = _get_campaign(session, campaign_id)
    if campaign.status in (CampaignStatus.PUBLISHED, CampaignStatus.PUBLISHING):
        raise HTTPException(status_code=409, detail=f"campaign is {campaign.status}")
    adapters = get_adapters(get_settings())
    return publish_campaign(session, campaign, adapters)


@router.post("/{campaign_id}/retry/{platform}", response_model=CampaignOut)
def retry(
    campaign_id: int,
    platform: str,
    session: Session = Depends(db_session),
) -> Campaign:
    campaign = _get_campaign(session, campaign_id)
    existing = {r.platform: r for r in campaign.results}
    if existing.get(platform) and existing[platform].status == PostStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail=f"{platform} already published")
    adapters = get_adapters(get_settings())
    try:
        return retry_platform(session, campaign, platform, adapters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _get_campaign(session: Session, campaign_id: int) -> Campaign:
    campaign = session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return campaign
