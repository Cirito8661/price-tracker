"""Security header tests."""

from __future__ import annotations

import httpx


async def test_security_headers_on_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    headers = response.headers

    assert "default-src 'self'" in headers["content-security-policy"]
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in headers["permissions-policy"]
    assert headers["cross-origin-opener-policy"] == "same-origin"
    assert headers["cross-origin-resource-policy"] == "same-origin"


async def test_security_headers_on_error_response(client: httpx.AsyncClient) -> None:
    response = await client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "default-src 'self'" in response.headers["content-security-policy"]
