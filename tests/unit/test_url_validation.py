"""Product URL and target price validation tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from price_tracker.services.url_validation import (
    UrlValidationError,
    normalize_product_url,
    parse_target_price,
    store_from_url,
)


def test_normalize_url_lowercases_host_and_removes_fragment() -> None:
    assert (
        normalize_product_url("HTTPS://Books.Toscrape.COM:443/catalogue/item.html#reviews")
        == "https://books.toscrape.com/catalogue/item.html"
    )


def test_normalize_url_removes_default_http_port_and_adds_path() -> None:
    assert normalize_product_url("http://example.com:80") == "http://example.com/"


def test_normalize_url_keeps_non_default_port_and_query() -> None:
    assert (
        normalize_product_url("https://example.com:8443/path?b=2&a=1")
        == "https://example.com:8443/path?b=2&a=1"
    )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.com/item",
        "https://user:pass@example.com/item",
        "http://localhost/item",
        "http://127.0.0.1/item",
        "http://10.0.0.1/item",
        "http://[::1]/item",
        "http://example.local/item",
        "https://example.com:bad/item",
        "https://example.com/a b",
        "https://" + "a" * 3000 + ".com/",
    ],
)
def test_invalid_urls_are_rejected(url: str) -> None:
    with pytest.raises(UrlValidationError):
        normalize_product_url(url)


def test_parse_target_price() -> None:
    assert parse_target_price("40.00") == Decimal("40.00")
    assert parse_target_price("0") == Decimal("0")
    assert parse_target_price("") is None
    assert parse_target_price(None) is None


@pytest.mark.parametrize("value", ["-1", "abc", "1.23456", "NaN"])
def test_invalid_target_prices_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        parse_target_price(value)


def test_store_from_url_uses_hostname() -> None:
    assert store_from_url("https://books.toscrape.com/catalogue/item.html") == "books.toscrape.com"
