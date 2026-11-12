"""Settings page tests."""

from __future__ import annotations

import httpx

from tests.web_helpers import extract_csrf_token


async def _token(client: httpx.AsyncClient) -> str:
    response = await client.get("/settings")
    assert response.status_code == 200
    return extract_csrf_token(response.text)


async def test_settings_page_renders(client: httpx.AsyncClient) -> None:
    response = await client.get("/settings")

    assert response.status_code == 200
    assert "Settings" in response.text
    assert "Configuration" in response.text
    assert "Database" in response.text
    assert "CSRF protection" in response.text
    assert "Local-only mode" in response.text
    assert "Not configured" in response.text
    assert "Scheduler" in response.text
    assert "Running" in response.text


async def test_settings_page_does_not_expose_secrets(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/settings")

    assert "test-secret-key" not in response.text
    assert "PT_SMTP_PASSWORD" not in response.text


async def test_update_settings_reschedules_scheduler(
    client: httpx.AsyncClient,
    app,
) -> None:
    token = await _token(client)

    response = await client.post(
        "/settings",
        data={
            "check_interval_seconds": "600",
            "smtp_port": "587",
            "smtp_security": "starttls",
            "smtp_timeout_seconds": "15",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/settings?saved=1"
    assert app.state.monitoring_scheduler.interval_seconds == 600
    assert app.state.runtime_settings.path.exists()

    page = await client.get("/settings?saved=1")
    assert "Settings saved successfully." in page.text
    assert "600 seconds" in page.text


async def test_update_settings_email_status(
    client: httpx.AsyncClient,
    app,
) -> None:
    token = await _token(client)

    response = await client.post(
        "/settings",
        data={
            "check_interval_seconds": "3600",
            "email_enabled": "on",
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_username": "",
            "smtp_password": "",
            "smtp_from": "tracker@example.com",
            "smtp_to": "owner@example.com",
            "smtp_security": "starttls",
            "smtp_timeout_seconds": "15",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    page = await client.get("/settings")
    assert "smtp.example.com" in page.text
    assert "Enabled" in page.text
    assert app.state.runtime_settings.effective_settings.effective_email_enabled is True


async def test_invalid_settings_are_rejected(
    client: httpx.AsyncClient,
    app,
) -> None:
    token = await _token(client)

    response = await client.post(
        "/settings",
        data={
            "check_interval_seconds": "10",
            "smtp_port": "587",
            "smtp_security": "starttls",
            "smtp_timeout_seconds": "15",
            "csrf_token": token,
        },
    )

    assert response.status_code == 422
    assert "at least 300" in response.text
    assert not app.state.runtime_settings.path.exists()
