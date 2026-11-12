"""DNS and SSRF protection tests."""

from __future__ import annotations

import pytest

from price_tracker.scraper.errors import UnsafeUrlError
from price_tracker.scraper.url_safety import (
    RequestGuard,
    UrlValidationError,
    ValidatedUrl,
    is_public_ip,
    normalize_product_url,
    validate_public_url,
)

PRODUCT_URL = "https://books.toscrape.com/catalogue/item.html"
PUBLIC_IP = "93.184.216.34"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("8.8.8.8", True),
        ("1.1.1.1", True),
        ("2001:4860:4860::8888", True),
        ("127.0.0.1", False),
        ("10.0.0.1", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("224.0.0.1", False),
        ("0.0.0.0", False),
        ("240.0.0.1", False),
        ("::1", False),
        ("fe80::1", False),
        ("::ffff:127.0.0.1", False),
        ("not-an-ip", False),
    ],
)
def test_is_public_ip(value: str, expected: bool) -> None:
    assert is_public_ip(value) is expected


def make_target() -> ValidatedUrl:
    return ValidatedUrl(
        url=PRODUCT_URL,
        scheme="https",
        host="books.toscrape.com",
        port=443,
        ips=frozenset({PUBLIC_IP}),
    )


async def test_validate_public_url_accepts_public_dns() -> None:
    result = await validate_public_url(PRODUCT_URL)

    assert result.host == "books.toscrape.com"
    assert result.port == 443
    assert result.ips == frozenset({PUBLIC_IP})


async def test_validate_public_url_rejects_private_dns(monkeypatch) -> None:
    async def private_resolve(host: str, port: int) -> frozenset[str]:
        return frozenset({"127.0.0.1"})

    monkeypatch.setattr(
        "price_tracker.scraper.url_safety.resolve_host_ips",
        private_resolve,
    )

    with pytest.raises(UnsafeUrlError, match="non-public"):
        await validate_public_url(PRODUCT_URL)


async def test_validate_public_url_rejects_mixed_dns(monkeypatch) -> None:
    async def mixed_resolve(host: str, port: int) -> frozenset[str]:
        return frozenset({PUBLIC_IP, "10.0.0.1"})

    monkeypatch.setattr(
        "price_tracker.scraper.url_safety.resolve_host_ips",
        mixed_resolve,
    )

    with pytest.raises(UnsafeUrlError, match="non-public"):
        await validate_public_url(PRODUCT_URL)


async def test_validate_public_url_rejects_disallowed_port() -> None:
    with pytest.raises(UnsafeUrlError, match="Port 8443"):
        await validate_public_url("https://books.toscrape.com:8443/catalogue/item.html")


async def test_validate_public_url_rejects_credentials() -> None:
    with pytest.raises(UrlValidationError):
        await validate_public_url("https://user:pass@books.toscrape.com/catalogue/item.html")


async def test_validate_public_url_rejects_dns_failure(monkeypatch) -> None:
    async def failing_resolve(host: str, port: int) -> frozenset[str]:
        raise UnsafeUrlError("Could not resolve the product hostname.")

    monkeypatch.setattr(
        "price_tracker.scraper.url_safety.resolve_host_ips",
        failing_resolve,
    )

    with pytest.raises(UnsafeUrlError, match="Could not resolve"):
        await validate_public_url(PRODUCT_URL)


async def test_request_guard_allows_unchanged_dns() -> None:
    guard = RequestGuard(
        make_target(),
        allowed_domains={"books.toscrape.com"},
    )

    await guard.validate("https://books.toscrape.com/catalogue/other.html")


async def test_request_guard_rejects_changed_dns(monkeypatch) -> None:
    async def changed_resolve(host: str, port: int) -> frozenset[str]:
        return frozenset({"93.184.216.35"})

    monkeypatch.setattr(
        "price_tracker.scraper.url_safety.resolve_host_ips",
        changed_resolve,
    )
    guard = RequestGuard(
        make_target(),
        allowed_domains={"books.toscrape.com"},
    )

    with pytest.raises(UnsafeUrlError, match="DNS result changed"):
        await guard.validate("https://books.toscrape.com/catalogue/other.html")


async def test_request_guard_rejects_disallowed_domain() -> None:
    guard = RequestGuard(
        make_target(),
        allowed_domains={"books.toscrape.com"},
    )

    with pytest.raises(UnsafeUrlError, match="Blocked a browser request"):
        await guard.validate("https://evil.example/tracker.js")


async def test_request_guard_rejects_non_http_scheme() -> None:
    guard = RequestGuard(
        make_target(),
        allowed_domains={"books.toscrape.com"},
    )

    with pytest.raises(UnsafeUrlError, match="non-HTTP"):
        await guard.validate("file:///etc/passwd")


async def test_request_guard_rejects_credentials() -> None:
    guard = RequestGuard(
        make_target(),
        allowed_domains={"books.toscrape.com"},
    )

    with pytest.raises(UnsafeUrlError, match="credentials"):
        await guard.validate("https://user:pass@books.toscrape.com/catalogue/item.html")


async def test_request_guard_rejects_private_dns(monkeypatch) -> None:
    async def private_resolve(host: str, port: int) -> frozenset[str]:
        return frozenset({"10.0.0.1"})

    monkeypatch.setattr(
        "price_tracker.scraper.url_safety.resolve_host_ips",
        private_resolve,
    )
    guard = RequestGuard(
        make_target(),
        allowed_domains={"books.toscrape.com"},
    )

    with pytest.raises(UnsafeUrlError, match="non-public"):
        await guard.validate("https://books.toscrape.com/catalogue/item.html")


async def test_request_guard_rejects_non_default_port() -> None:
    guard = RequestGuard(
        make_target(),
        allowed_domains={"books.toscrape.com"},
    )

    with pytest.raises(UnsafeUrlError, match="port 8443"):
        await guard.validate("https://books.toscrape.com:8443/catalogue/item.html")


async def test_request_guard_allows_declared_subresource_domain() -> None:
    guard = RequestGuard(
        make_target(),
        allowed_domains={
            "books.toscrape.com",
            "static.books.toscrape.com",
        },
    )

    await guard.validate("https://static.books.toscrape.com/app.css")


def test_normalization_rejects_private_ip_literal() -> None:
    with pytest.raises(UrlValidationError):
        normalize_product_url("http://127.0.0.1/item")


def test_normalization_rejects_bracketed_ipv4() -> None:
    with pytest.raises(UrlValidationError):
        normalize_product_url("https://[192.0.0.9]/item")


def test_normalization_rejects_malformed_ipv6() -> None:
    with pytest.raises(UrlValidationError):
        normalize_product_url("https://[::1/item")


async def test_request_guard_rejects_malformed_url() -> None:
    guard = RequestGuard(
        make_target(),
        allowed_domains={"books.toscrape.com"},
    )

    with pytest.raises(UnsafeUrlError, match="malformed"):
        await guard.validate("https://[192.0.0.9]/item")
