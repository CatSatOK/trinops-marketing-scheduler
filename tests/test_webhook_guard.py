"""Lead webhook hardening: per-IP rate limit, body-size cap, shared secret.

The RateLimiter is exercised directly (deterministic via injected `now`); the
guard is exercised end to end through the real app with a TestClient.
"""

import pytest
from fastapi.testclient import TestClient

from api.ratelimit import RateLimiter


# --- RateLimiter unit tests -------------------------------------------------


def test_limiter_allows_up_to_max_then_blocks():
    limiter = RateLimiter(max_events=2, window_seconds=60)
    assert limiter.allow("ip", now=0.0) is True
    assert limiter.allow("ip", now=1.0) is True
    assert limiter.allow("ip", now=2.0) is False


def test_limiter_window_slides():
    limiter = RateLimiter(max_events=1, window_seconds=60)
    assert limiter.allow("ip", now=0.0) is True
    assert limiter.allow("ip", now=30.0) is False
    # once the first hit ages out of the window, room opens up again
    assert limiter.allow("ip", now=61.0) is True


def test_limiter_keys_are_independent():
    limiter = RateLimiter(max_events=1, window_seconds=60)
    assert limiter.allow("a", now=0.0) is True
    assert limiter.allow("b", now=0.0) is True


def test_limiter_zero_disables():
    limiter = RateLimiter(max_events=0, window_seconds=60)
    for _ in range(5):
        assert limiter.allow("ip", now=0.0) is True


# --- guard integration tests ------------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("PUBLISHED_DIR", str(tmp_path / "published"))
    monkeypatch.setenv("DISPATCH_INTERVAL_MINUTES", "60")
    # keep startup empty + predictable
    monkeypatch.setenv("SEED_CAMPAIGNS_FILE", str(tmp_path / "no-campaigns.json"))
    monkeypatch.setenv("SEED_LEADS_FILE", str(tmp_path / "no-leads.json"))

    def _reset():
        import api.routes.leads as leads
        import marketing.database as database
        from marketing.config import get_settings

        get_settings.cache_clear()
        leads._webhook_limiter.cache_clear()
        database._engine = None
        database._SessionLocal = None

    _reset()
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client

    _reset()


def test_webhook_open_by_default(client):
    resp = client.post("/leads/webhook", json={"name": "Ada", "company": "Acme"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "Ada"


def test_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setenv("WEBHOOK_RATE_LIMIT_PER_MINUTE", "2")
    from marketing.config import get_settings
    import api.routes.leads as leads

    get_settings.cache_clear()
    leads._webhook_limiter.cache_clear()

    assert client.post("/leads/webhook", json={"name": "a"}).status_code == 201
    assert client.post("/leads/webhook", json={"name": "b"}).status_code == 201
    blocked = client.post("/leads/webhook", json={"name": "c"})
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") == "60"


def test_payload_too_large_returns_413(client, monkeypatch):
    monkeypatch.setenv("WEBHOOK_MAX_BYTES", "64")
    from marketing.config import get_settings

    get_settings.cache_clear()

    resp = client.post("/leads/webhook", json={"notes": "x" * 500})
    assert resp.status_code == 413


def test_shared_secret_enforced_when_configured(client, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "topsecret")
    from marketing.config import get_settings

    get_settings.cache_clear()

    missing = client.post("/leads/webhook", json={"name": "a"})
    assert missing.status_code == 401

    wrong = client.post(
        "/leads/webhook", json={"name": "a"}, headers={"X-Webhook-Secret": "nope"}
    )
    assert wrong.status_code == 401

    ok = client.post(
        "/leads/webhook", json={"name": "a"}, headers={"X-Webhook-Secret": "topsecret"}
    )
    assert ok.status_code == 201
