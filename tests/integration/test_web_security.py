"""CSRF, origin, and error handling tests."""

from __future__ import annotations

import httpx
import pytest

from price_tracker.config import Settings
from price_tracker.database.schema import DatabaseSchemaError
from price_tracker.main import create_app
from price_tracker.services.product_service import ProductService
from tests.web_helpers import extract_csrf_token


async def _token(client: httpx.AsyncClient) -> str:
    response = await client.get("/products")
    assert response.status_code == 200
    return extract_csrf_token(response.text)


async def test_missing_csrf_token_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/products",
        data={"url": "https://example.com/item"},
    )

    assert response.status_code == 403
    assert "CSRF token is missing" in response.text


async def test_invalid_csrf_token_is_rejected(client: httpx.AsyncClient) -> None:
    await _token(client)

    response = await client.post(
        "/products",
        data={
            "url": "https://example.com/item",
            "csrf_token": "invalid-token",
        },
    )

    assert response.status_code == 403
    assert "CSRF token is invalid" in response.text


async def test_untrusted_origin_is_rejected(client: httpx.AsyncClient) -> None:
    token = await _token(client)

    response = await client.post(
        "/products",
        data={
            "url": "https://example.com/item",
            "csrf_token": token,
        },
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert "Request origin is not allowed" in response.text


async def test_allowed_origin_is_accepted(client: httpx.AsyncClient) -> None:
    token = await _token(client)

    response = await client.post(
        "/products",
        data={
            "url": "https://books.toscrape.com/catalogue/allowed-origin.html",
            "csrf_token": token,
        },
        headers={"Origin": "http://testserver"},
        follow_redirects=False,
    )

    assert response.status_code == 303


async def test_csrf_cookie_is_httponly_and_lax(client: httpx.AsyncClient) -> None:
    response = await client.get("/products")
    cookie = response.headers["set-cookie"].lower()

    assert "pt_csrf=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie


async def test_htmx_csrf_error_returns_fragment(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/products",
        data={"url": "https://example.com/item"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 403
    assert 'class="alert alert-error"' in response.text
    assert "CSRF token is missing" in response.text


async def test_not_found_page(client: httpx.AsyncClient) -> None:
    response = await client.get("/does-not-exist")

    assert response.status_code == 404
    assert "Page not found" in response.text


async def test_unhandled_error_page(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(self: ProductService) -> list:
        raise RuntimeError("boom")

    monkeypatch.setattr(ProductService, "list_products", boom)

    response = await client.get("/products")

    assert response.status_code == 500
    assert "Something went wrong" in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


async def test_app_startup_requires_database_schema(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        secret_key="test-secret",
        allowed_hosts=["testserver"],
        email_enabled=False,
    )
    app = create_app(settings)

    with pytest.raises(DatabaseSchemaError, match="alembic upgrade head"):
        async with app.router.lifespan_context(app):
            pass


async def test_security_headers_on_products_page(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/products")

    assert response.status_code == 200
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY"
