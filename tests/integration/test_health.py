"""Health and root endpoint tests."""

from __future__ import annotations

from pathlib import Path

import httpx

from price_tracker.config import Settings


async def test_health_endpoint(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "name": "Price Tracker",
        "version": "0.1.0",
    }


async def test_root_returns_dashboard(client: httpx.AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "Price Tracker" in response.text


async def test_unknown_path_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/does-not-exist")

    assert response.status_code == 404


async def test_log_file_is_created(
    client: httpx.AsyncClient,
    settings: Settings,
) -> None:
    await client.get("/health")

    log_path: Path = settings.log_dir / "app.log"
    assert log_path.exists()
