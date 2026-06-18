"""Lead endpoints: inbound form webhook + scored lead inbox."""

import json
import secrets
from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth import require_admin
from api.ratelimit import RateLimiter
from marketing.config import get_settings
from marketing.database import session_scope
from marketing.lead_qualifier import qualify, scoring_rubric
from marketing.models import Lead, LeadCategory

router = APIRouter(prefix="/leads", tags=["leads"])


def db_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session


@lru_cache
def _webhook_limiter() -> RateLimiter:
    # Built once from settings. Tests that change the limit call cache_clear().
    return RateLimiter(get_settings().webhook_rate_limit_per_minute, 60.0)


async def webhook_guard(request: Request) -> None:
    """Protect the unauthenticated lead webhook: per-IP rate limit, body-size
    cap, and an optional shared secret. Runs before the payload is parsed."""
    settings = get_settings()

    # Rate limit by caller IP first — cheapest check, caps abuse volume.
    client = request.client.host if request.client else "unknown"
    if not _webhook_limiter().allow(client):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": "60"},
        )

    # Shared secret, when configured (open by default for demo / any provider).
    if settings.webhook_secret:
        provided = request.headers.get("x-webhook-secret")
        if provided is None or not secrets.compare_digest(provided, settings.webhook_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or missing webhook secret",
            )

    # Payload size cap. Trust the Content-Length header for a fast reject, then
    # confirm against the bytes actually received (the header can lie).
    cap = settings.webhook_max_bytes
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > cap:
        raise HTTPException(
            status_code=413,  # Content Too Large
            detail="payload too large",
        )
    body = await request.body()  # cached by Starlette, reused when the model parses
    if len(body) > cap:
        raise HTTPException(
            status_code=413,  # Content Too Large
            detail="payload too large",
        )


def _truthy(value: object) -> bool:
    """Read a consent flag from an arbitrary form provider: handles real bools
    and the usual string encodings (on/true/yes/1)."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


class LeadWebhook(BaseModel):
    """Inbound form payload. Extra fields are kept and stored verbatim, so any
    form provider works without a schema change."""

    model_config = ConfigDict(extra="allow")


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    name: str | None
    company: str | None
    email: str | None
    service_interest: str | None
    consent: bool
    score: int
    category: LeadCategory
    priority: int
    routed_to: str
    notes: str | None
    created_at: datetime


class NotesUpdate(BaseModel):
    notes: str = Field(max_length=2000)


@router.get("/scoring")
def get_scoring_rubric() -> dict:
    """How the lead score is calculated — drives the dashboard explainer."""
    return scoring_rubric()


@router.post(
    "/webhook",
    response_model=LeadOut,
    status_code=201,
    dependencies=[Depends(webhook_guard)],
)
def capture_lead(
    payload: LeadWebhook,
    session: Session = Depends(db_session),
) -> Lead:
    form = payload.model_dump()
    settings = get_settings()
    scored = qualify(form, settings)
    lead = Lead(
        source=form.get("source", "webhook"),
        raw_data=json.dumps(form, default=str),
        name=form.get("name"),
        company=form.get("company"),
        email=form.get("email"),
        service_interest=scored.service_interest,
        # GDPR consent: did the form carry an affirmative marketing-consent flag?
        consent=_truthy(form.get("consent")),
        score=scored.score,
        category=scored.category,
        priority=scored.priority,
        routed_to=scored.routed_to,
        notes=form.get("notes"),
    )
    session.add(lead)
    session.flush()
    return lead


@router.get("", response_model=list[LeadOut], dependencies=[Depends(require_admin)])
def list_leads(
    category: LeadCategory | None = None,
    session: Session = Depends(db_session),
) -> list[Lead]:
    stmt = select(Lead).order_by(Lead.priority, Lead.created_at.desc())
    if category is not None:
        stmt = stmt.where(Lead.category == category)
    return list(session.scalars(stmt))


@router.patch("/{lead_id}/notes", response_model=LeadOut, dependencies=[Depends(require_admin)])
def update_notes(
    lead_id: int,
    payload: NotesUpdate,
    session: Session = Depends(db_session),
) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    lead.notes = payload.notes.strip() or None
    return lead


@router.delete("/{lead_id}", status_code=204, dependencies=[Depends(require_admin)])
def erase_lead(
    lead_id: int,
    session: Session = Depends(db_session),
) -> None:
    """GDPR right to erasure: hard-delete a lead and its stored raw payload.

    Removes the row entirely (including the verbatim form data) rather than
    flagging it, so no personal data is retained after the request.
    """
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    session.delete(lead)
