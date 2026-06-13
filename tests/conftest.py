import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from marketing.config import Settings
from marketing.models import Base

REPO_ROOT = Path(__file__).resolve().parent.parent

# Seed files are loaded relative to the repo root
os.chdir(REPO_ROOT)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        demo_mode=True,
        enabled_platforms=["linkedin", "twitter", "facebook"],
        demo_fail_platform="facebook",
        published_dir=str(tmp_path / "published"),
        database_url=f"sqlite:///{tmp_path}/test.db",
    )


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
