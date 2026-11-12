"""BaseScraper interface tests."""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal

import pytest

from price_tracker.scraper.base import BaseScraper, ScrapedProduct


class DummyAdapter(BaseScraper):
    store_id = "dummy"
    store_name = "Dummy Store"
    domains = ("example.com",)

    def parse(self, html: str, url: str) -> ScrapedProduct:
        return ScrapedProduct(
            name="Dummy",
            price=Decimal("1.00"),
            currency="USD",
            url=url,
            store=self.store_id,
        )


def test_base_scraper_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseScraper()  # type: ignore[abstract]


def test_adapter_supports_exact_domains() -> None:
    adapter = DummyAdapter()

    assert adapter.supports("https://example.com/product") is True
    assert adapter.supports("https://www.example.com/product") is False
    assert adapter.supports("not a url") is False


def test_scraped_product_has_aware_timestamp() -> None:
    product = ScrapedProduct(
        name="Dummy",
        price=Decimal("1.00"),
        currency="USD",
        url="https://example.com/product",
        store="dummy",
    )

    assert product.retrieved_at.tzinfo is UTC


def test_dummy_adapter_returns_product() -> None:
    result = DummyAdapter().parse(
        "<html></html>",
        "https://example.com/product",
    )

    assert result.name == "Dummy"
    assert result.price == Decimal("1.00")
    assert result.store == "dummy"
