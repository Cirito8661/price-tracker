"""Trusted host middleware tests."""

from __future__ import annotations

import httpx


async def test_untrusted_host_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"Host": "evil.example"})

    assert response.status_code == 400


async def test_localhost_host_is_allowed(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"Host": "localhost"})

    assert response.status_code == 200
