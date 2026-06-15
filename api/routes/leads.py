"""Lead endpoints: inbound form webhook + scored lead inbox."""

import json
from collections.abc import Iterator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from sqlalchemy import select
from sqlalchemy.orm import Session

from marketing.config import get_settings
from marketing.database import session_scope
from marketing.lead_qualifier import qualify, scoring_rubric
from marketing.models import Lead, LeadCategory

router = APIRouter(prefix="/leads", tags=["leads"])


def db_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session


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


@router.post("/webhook", response_model=LeadOut, status_code=201)
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
        score=scored.score,
        category=scored.category,
        priority=scored.priority,
        routed_to=scored.routed_to,
        notes=form.get("notes"),
    )
    session.add(lead)
    session.flush()
    return lead


@router.get("", response_model=list[LeadOut])
def list_leads(
    category: LeadCategory | None = None,
    session: Session = Depends(db_session),
) -> list[Lead]:
    stmt = select(Lead).order_by(Lead.priority, Lead.created_at.desc())
    if category is not None:
        stmt = stmt.where(Lead.category == category)
    return list(session.scalars(stmt))


@router.patch("/{lead_id}/notes", response_model=LeadOut)
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
