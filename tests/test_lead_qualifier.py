"""Lead qualifier tests: scoring bands, categories, routing, value parsing."""

from marketing.lead_qualifier import _max_number, qualify, scoring_rubric
from marketing.models import LeadCategory


def test_max_number_parses_ranges():
    assert _max_number("£10,000-£20,000") == 20000.0
    assert _max_number("200+") == 200.0
    assert _max_number("under £500") == 500.0
    assert _max_number(7500) == 7500.0
    assert _max_number("no idea") is None
    assert _max_number(None) is None


def test_high_value_lead_is_hot_and_routed(settings):
    result = qualify(
        {"budget": "£15,000", "company_size": "300", "service_interest": "automation"},
        settings,
    )
    assert result.score == 85  # 40 + 25 + 20
    assert result.category == LeadCategory.HOT
    assert result.priority == 1
    assert result.routed_to == "automation@example.com"


def test_mid_value_lead_is_warm(settings):
    result = qualify(
        {"budget": "£6,000", "company_size": "80", "service_interest": "marketing"},
        settings,
    )
    # 30 (budget) + 18 (size) + 5 (unknown service) = 53
    assert result.score == 53
    assert result.category == LeadCategory.WARM
    assert result.priority == 2
    # unknown service routes to the default contact
    assert result.routed_to == settings.lead_default_contact


def test_low_value_lead_is_cold(settings):
    result = qualify(
        {"budget": "under £500", "company_size": "3", "service_interest": ""},
        settings,
    )
    # 5 (budget) + 5 (size) + 0 (no service) = 10
    assert result.score == 10
    assert result.category == LeadCategory.COLD
    assert result.priority == 3


def test_known_service_routes_regardless_of_score(settings):
    result = qualify({"service_interest": "transport"}, settings)
    assert result.routed_to == "transport@example.com"
    assert result.service_interest == "transport"


def test_empty_form_is_cold(settings):
    result = qualify({}, settings)
    assert result.score == 0
    assert result.category == LeadCategory.COLD
    assert result.routed_to == settings.lead_default_contact


def test_scoring_rubric_matches_a_max_score_lead(settings):
    rubric = scoring_rubric()
    # the top band of each signal should sum to the advertised max_score
    top = sum(s["bands"][0]["points"] for s in rubric["signals"])
    assert top == rubric["max_score"]
    # and an all-top-band lead should actually hit it and be HOT
    best = qualify(
        {"budget": "£50,000", "company_size": "999", "service_interest": "automation"},
        settings,
    )
    assert best.score == rubric["max_score"]
    assert best.category == LeadCategory.HOT
