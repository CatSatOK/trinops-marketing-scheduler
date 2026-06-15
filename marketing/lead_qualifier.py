"""Rule-based lead scoring — no API calls.

Three structured signals from the submitted form drive the score:
budget, company size, and service interest. The total maps to a HOT / WARM /
COLD category and a 1-3 priority, and the service interest decides which
contact the lead is routed to. Free-text fields are ignored here by design —
see the README for where a Claude fallback would slot in for unstructured
enquiries.
"""

import re
from dataclasses import dataclass, field

from marketing.config import Settings
from marketing.logging_conf import get_logger
from marketing.models import LeadCategory

logger = get_logger(__name__)

# Score bands. Tuned for an SME services pipeline; adjust per client.
# (lower_bound_inclusive, points) — first matching band from the top wins.
BUDGET_BANDS = [(10_000, 40), (5_000, 30), (1_000, 20), (0, 5)]
SIZE_BANDS = [(200, 25), (50, 18), (10, 10), (0, 5)]
KNOWN_SERVICE_POINTS = 20
UNKNOWN_SERVICE_POINTS = 5

HOT_THRESHOLD = 65
WARM_THRESHOLD = 35


@dataclass
class QualifiedLead:
    score: int
    category: LeadCategory
    priority: int
    routed_to: str
    service_interest: str | None
    reasons: list[str] = field(default_factory=list)


def scoring_rubric() -> dict:
    """The scoring rules in a display-ready form — single source of truth for the
    dashboard explainer, so the UI can never drift from the actual logic."""
    return {
        "signals": [
            {
                "name": "Budget",
                "bands": [
                    {"label": "£10,000 or more", "points": BUDGET_BANDS[0][1]},
                    {"label": "£5,000 – £9,999", "points": BUDGET_BANDS[1][1]},
                    {"label": "£1,000 – £4,999", "points": BUDGET_BANDS[2][1]},
                    {"label": "under £1,000", "points": BUDGET_BANDS[3][1]},
                ],
            },
            {
                "name": "Company size",
                "bands": [
                    {"label": "200+ staff", "points": SIZE_BANDS[0][1]},
                    {"label": "50 – 199 staff", "points": SIZE_BANDS[1][1]},
                    {"label": "10 – 49 staff", "points": SIZE_BANDS[2][1]},
                    {"label": "under 10 staff", "points": SIZE_BANDS[3][1]},
                ],
            },
            {
                "name": "Service interest",
                "bands": [
                    {"label": "a service we offer", "points": KNOWN_SERVICE_POINTS},
                    {"label": "other / unspecified service", "points": UNKNOWN_SERVICE_POINTS},
                    {"label": "no service given", "points": 0},
                ],
            },
        ],
        "categories": [
            {"category": "HOT", "rule": f"score ≥ {HOT_THRESHOLD}", "priority": 1},
            {"category": "WARM", "rule": f"{WARM_THRESHOLD} ≤ score < {HOT_THRESHOLD}", "priority": 2},
            {"category": "COLD", "rule": f"score < {WARM_THRESHOLD}", "priority": 3},
        ],
        "max_score": BUDGET_BANDS[0][1] + SIZE_BANDS[0][1] + KNOWN_SERVICE_POINTS,
    }


def _max_number(value) -> float | None:
    """Pull the largest number out of a value like '£5,000-£10,000' or '200+'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    numbers = re.findall(r"\d[\d,]*(?:\.\d+)?", str(value))
    if not numbers:
        return None
    return max(float(n.replace(",", "")) for n in numbers)


def _band_points(value: float | None, bands: list[tuple[int, int]]) -> int:
    if value is None:
        return 0
    for lower, points in bands:
        if value >= lower:
            return points
    return 0


def _normalise_service(value) -> str | None:
    if not value:
        return None
    return str(value).strip().lower()


def qualify(form: dict, settings: Settings) -> QualifiedLead:
    reasons: list[str] = []

    budget = _max_number(form.get("budget"))
    budget_points = _band_points(budget, BUDGET_BANDS)
    if budget is not None:
        reasons.append(f"budget {budget:.0f} -> {budget_points}")

    size = _max_number(form.get("company_size"))
    size_points = _band_points(size, SIZE_BANDS)
    if size is not None:
        reasons.append(f"company size {size:.0f} -> {size_points}")

    service = _normalise_service(form.get("service_interest"))
    if service and service in settings.lead_routing:
        service_points = KNOWN_SERVICE_POINTS
        routed_to = settings.lead_routing[service]
    else:
        service_points = UNKNOWN_SERVICE_POINTS if service else 0
        routed_to = settings.lead_default_contact
    reasons.append(f"service {service or 'none'} -> {service_points}")

    score = budget_points + size_points + service_points

    if score >= HOT_THRESHOLD:
        category, priority = LeadCategory.HOT, 1
    elif score >= WARM_THRESHOLD:
        category, priority = LeadCategory.WARM, 2
    else:
        category, priority = LeadCategory.COLD, 3

    logger.info("lead scored %d -> %s (routed to %s)", score, category, routed_to)
    return QualifiedLead(
        score=score,
        category=category,
        priority=priority,
        routed_to=routed_to,
        service_interest=service,
        reasons=reasons,
    )
