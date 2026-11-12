"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

import price_tracker.models  # noqa: F401
from price_tracker.config import Settings
from price_tracker.database.base import Base
from price_tracker.database.engine import (
    create_engine_for_url,
    create_engine_from_settings,
)
from price_tracker.database.session import SessionFactory, create_session_factory
from price_tracker.logging_config import reset_logging
from price_tracker.main import create_app
from tests.fakes import FakeBrowserManager


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Provide isolated application settings for a test."""

    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        secret_key="test-secret-key",
        public_base_url="http://testserver",
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
        email_enabled=False,
        log_level="WARNING",
    )


@pytest.fixture
def initialized_settings(settings: Settings) -> Settings:
    """Create the database schema for the web application test database."""

    engine = create_engine_from_settings(settings)
    Base.metadata.create_all(engine)
    engine.dispose()
    return settings


@pytest.fixture
def fake_browser_manager() -> FakeBrowserManager:
    """Provide a browser manager that returns controlled Books to Scrape HTML."""

    return FakeBrowserManager()


@pytest.fixture
def app(initialized_settings: Settings, fake_browser_manager: FakeBrowserManager):
    """Provide an application instance with an initialized database."""

    return create_app(
        initialized_settings,
        browser_manager=fake_browser_manager,
    )


@pytest.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    """Provide an HTTP client with the application lifespan running."""

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as test_client,
    ):
        yield test_client


@pytest.fixture
def web_session_factory(
    initialized_settings: Settings,
) -> Iterator[SessionFactory]:
    """Provide a session factory for inspecting the web test database."""

    engine = create_engine_from_settings(initialized_settings)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


@pytest.fixture
def db_engine(tmp_path: Path) -> Iterator[Engine]:
    """Provide an isolated SQLite engine with the full schema."""

    database_path = tmp_path / "test.db"
    engine = create_engine_for_url(f"sqlite+pysqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(db_engine: Engine) -> SessionFactory:
    """Provide a session factory bound to the test database."""

    return create_session_factory(db_engine)


@pytest.fixture
def db_session(session_factory: SessionFactory) -> Iterator[Session]:
    """Provide a session that is rolled back and closed after a test."""

    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _mock_scraper_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep automated tests independent of live DNS and network access."""

    async def fake_resolve(host: str, port: int) -> frozenset[str]:
        return frozenset({"93.184.216.34"})

    monkeypatch.setattr(
        "price_tracker.scraper.url_safety.resolve_host_ips",
        fake_resolve,
    )


@pytest.fixture(autouse=True)
def _reset_logging_after_test() -> Iterator[None]:
    """Close logging handlers so temporary directories can be removed."""

    yield
    reset_logging()
