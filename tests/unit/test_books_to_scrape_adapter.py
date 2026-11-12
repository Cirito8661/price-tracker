"""Books to Scrape adapter parsing tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from price_tracker.scraper.adapters.books_to_scrape import (
    BooksToScrapeAdapter,
    parse_price_text,
)
from price_tracker.scraper.errors import (
    CurrencyParseError,
    InvalidPageError,
    InvalidPriceError,
    PriceNotFoundError,
    UnsupportedStoreError,
)
from tests.fakes import BOOKS_TO_SCRAPE_HTML

PRODUCT_URL = "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"


def test_adapter_extracts_product_fields() -> None:
    result = BooksToScrapeAdapter().parse(BOOKS_TO_SCRAPE_HTML, PRODUCT_URL)

    assert result.name == "A Light in the Attic"
    assert result.price == Decimal("51.77")
    assert result.currency == "GBP"
    assert result.url == PRODUCT_URL
    assert result.store == "books_toscrape"


def test_adapter_normalizes_name_whitespace() -> None:
    html = """
    <html><body>
      <h1>  A   Light
        in the Attic </h1>
      <p class="price_color">£10.00</p>
    </body></html>
    """

    result = BooksToScrapeAdapter().parse(html, PRODUCT_URL)

    assert result.name == "A Light in the Attic"


def test_missing_name_raises() -> None:
    html = '<html><body><p class="price_color">£10.00</p></body></html>'

    with pytest.raises(InvalidPageError):
        BooksToScrapeAdapter().parse(html, PRODUCT_URL)


def test_missing_price_raises() -> None:
    html = "<html><body><h1>Product</h1></body></html>"

    with pytest.raises(PriceNotFoundError):
        BooksToScrapeAdapter().parse(html, PRODUCT_URL)


def test_invalid_price_raises() -> None:
    html = '<html><body><h1>Product</h1><p class="price_color">£not-a-price</p></body></html>'

    with pytest.raises(InvalidPriceError):
        BooksToScrapeAdapter().parse(html, PRODUCT_URL)


def test_unknown_currency_raises() -> None:
    html = '<html><body><h1>Product</h1><p class="price_color">₹10.00</p></body></html>'

    with pytest.raises(CurrencyParseError):
        BooksToScrapeAdapter().parse(html, PRODUCT_URL)


def test_unsupported_url_raises() -> None:
    with pytest.raises(UnsupportedStoreError):
        BooksToScrapeAdapter().parse(
            BOOKS_TO_SCRAPE_HTML,
            "https://example.com/product",
        )


def test_price_with_thousands_separator() -> None:
    price, currency = parse_price_text("£1,000.00")

    assert price == Decimal("1000.00")
    assert currency == "GBP"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$12.50", (Decimal("12.50"), "USD")),
        ("€9.99", (Decimal("9.99"), "EUR")),
        ("¥100", (Decimal("100"), "JPY")),
    ],
)
def test_supported_currency_symbols(
    text: str,
    expected: tuple[Decimal, str],
) -> None:
    assert parse_price_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "£10.12345",
        "£10.00 extra",
        "10.00",
        "£",
    ],
)
def test_invalid_price_text(text: str) -> None:
    with pytest.raises((InvalidPriceError, CurrencyParseError)):
        parse_price_text(text)


def test_adapter_supports_approved_domains() -> None:
    adapter = BooksToScrapeAdapter()

    assert adapter.supports(PRODUCT_URL) is True
    assert adapter.supports("https://www.books.toscrape.com/") is True
    assert adapter.supports("https://example.com/") is False
