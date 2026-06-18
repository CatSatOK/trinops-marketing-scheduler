import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from marketing.config import Settings
from marketing.models import Base

REPO_ROOT = Path(__file__).resolve().parent.parent

# Seed files are loaded relative to the repo root
os.chdir(REPO_ROOT)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient on the real app, pointed at temp paths with an empty DB."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("PUBLISHED_DIR", str(tmp_path / "published"))
    monkeypatch.setenv("DISPATCH_INTERVAL_MINUTES", "60")
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


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        demo_mode=True,
        enabled_platforms=["linkedin", "twitter", "facebook"],
        demo_flaky_platform="facebook",
        published_dir=str(tmp_path / "published"),
        database_url=f"sqlite:///{tmp_path}/test.db",
    )


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
