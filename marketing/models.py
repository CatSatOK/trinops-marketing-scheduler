"""SQLAlchemy 2.0 models."""

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class CampaignStatus(enum.StrEnum):
    QUEUED = "QUEUED"            # waiting for its scheduled time
    PUBLISHING = "PUBLISHING"    # dispatcher is working through the adapters
    PUBLISHED = "PUBLISHED"      # every target platform succeeded
    PARTIAL = "PARTIAL"          # some platforms succeeded, some failed
    FAILED = "FAILED"            # every target platform failed


class PostStatus(enum.StrEnum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class LeadCategory(enum.StrEnum):
    HOT = "HOT"
    WARM = "WARM"
    COLD = "COLD"


class Campaign(Base):
    """A single piece of content scheduled to publish across one or more platforms."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(String(500))
    # Comma-joined platform names; see the `platforms` property for the list view.
    platforms_raw: Mapped[str] = mapped_column("platforms", String(300))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, native_enum=False, length=20),
        default=CampaignStatus.QUEUED,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    results: Mapped[list["PostResult"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )

    @property
    def platforms(self) -> list[str]:
        return [p for p in (self.platforms_raw or "").split(",") if p]

    @platforms.setter
    def platforms(self, values: list[str]) -> None:
        self.platforms_raw = ",".join(values)

    def __repr__(self) -> str:
        return f"<Campaign {self.id} {self.title!r} {self.status}>"


class PostResult(Base):
    """The outcome of publishing one campaign to one platform."""

    __tablename__ = "post_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    platform: Mapped[str] = mapped_column(String(50), index=True)

    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus, native_enum=False, length=20),
        default=PostStatus.PENDING,
    )
    platform_post_id: Mapped[str | None] = mapped_column(String(200))
    error_message: Mapped[str | None] = mapped_column(String(500))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign: Mapped[Campaign] = relationship(back_populates="results")

    def __repr__(self) -> str:
        return f"<PostResult c={self.campaign_id} {self.platform} {self.status}>"


class Lead(Base):
    """An inbound enquiry captured from a form webhook and scored by rules."""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(100), default="webhook")
    # The full submitted form payload, kept verbatim as JSON for auditability.
    raw_data: Mapped[str] = mapped_column(Text)

    name: Mapped[str | None] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    service_interest: Mapped[str | None] = mapped_column(String(100))

    score: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[LeadCategory] = mapped_column(
        Enum(LeadCategory, native_enum=False, length=10),
        default=LeadCategory.COLD,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=3, index=True)  # 1 = highest
    routed_to: Mapped[str] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def __repr__(self) -> str:
        return f"<Lead {self.id} {self.company!r} {self.category} p{self.priority}>"
